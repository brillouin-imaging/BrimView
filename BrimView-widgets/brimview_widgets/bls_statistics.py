from __future__ import annotations

from brimview_widgets.utils import catch_and_notify
from .bls_data_visualizer import BlsDataVisualizer
from .logging import logger
from .bls_types import bls_param

import panel as pn
import panel_material_ui as pmui
from .widgets import CustomPMuiCard
from .utils import loading_spinner

from panel.widgets.base import WidgetBase
from panel.custom import PyComponent
from bokeh.models.widgets.tables import ScientificFormatter
from brimfile.data import Data

import param
import holoviews as hv
import numpy as np
import xarray as xr
import pandas as pd

from numpy.typing import NDArray


ZYXPoints = list[tuple[int, int, int]]


class BlsStatistics(WidgetBase, PyComponent):
    """
    Widget to compute and display basic statistics of selected regions in BLS data.
    """

    # === References to external objects ===
    bls_data = param.ClassSelector(
        class_=bls_param,
        default=None,
        precedence=-1,
        doc="The current selected BLS file/data",
        allow_refs=True,
    )

    img_mask = param.Parameter(
        default=None,
        precedence=-1,
        doc="Selection mask from the data visualizer",
        allow_refs=True,
    )

    # Information to go from displayed mask to bls data coordinates
    img_axis_1 = param.Selector(
        default="x", objects=["x", "y", "z"], label="Horizontal axis", allow_refs=True
    )
    img_axis_2 = param.Selector(
        default="y", objects=["x", "y", "z"], label="Vertical axis", allow_refs=True
    )
    img_axis_3 = param.Selector(default="z", objects=["x", "y", "z"], allow_refs=True)
    img_axis_3_slice = param.Integer(
        default=0, label="3rd axis slice selector", allow_refs=True
    )

    # === Internal state ===
    selected_points = param.List(
        default=[],
        precedence=-1,
        doc="List of selected points (z, y, x ) in data coordinates",
    )

    def __init__(self, result_plot: BlsDataVisualizer, **params):
        self.spinner = pmui.CircularProgress(
                    value=False, size=20, label="Idle", visible=True
                )
        params["name"] = "Group Statistics"        
        super().__init__(**params)

        self.tooltip = "Use the **Lasso Select** tool to select a region in the image. This widget will compute the average spectrum and other quantities for the selected region."

        # === Linking to other widgets ===
        # TODO: update result_plot to use this new class
        self.bls_data: bls_param = bls_param(
            file=result_plot.param.bls_file,
            data=result_plot.param.bls_data,
            analysis=result_plot.param.bls_analysis,
        )

        self.img_mask = result_plot.param.mask
        self.img_axis_1 = result_plot.param.img_axis_1
        self.img_axis_2 = result_plot.param.img_axis_2
        self.img_axis_3 = result_plot.param.img_axis_3
        self.img_axis_3_slice = result_plot.param.img_axis_3_slice

        # === Some panel setup ===
        self.spectrum_plot_widget = pn.ui.HoloViews(
            None,
            sizing_mode="stretch_width",
        )
        self.statistic_tabulator_widget = self.statistic_tabulator()

        self.tqdm = pn.ui.Tqdm(visible=False)

        # === Typing hints ===
        self.bls_data: bls_param
        self.img_mask: xr.DataArray
        self.selected_points: list[tuple[int, int, int]]

    @pn.depends("img_mask")
    def mask_status(self):
        if self.img_mask is None:
            return "No selection in the image. Use the lasso tool to select a region."
        else:
            num_selected = np.count_nonzero(self.img_mask)
            total_pixels = self.img_mask.size
            pct_selected = 100 * num_selected / total_pixels
            return f"Selected pixels: {num_selected} ({pct_selected:.2f}%)"

    @pn.depends("img_mask", watch=True)
    def update_selected_points(self):
        """Update the list of selected points based on the current image mask."""
        if self.img_mask is None:
            self.selected_points = []
        else:
            self.selected_points = self.mask_to_list(self.img_mask)

    def mask_to_list(self, mask: xr.DataArray) -> list[tuple[int, int, int]]:
        """Convert a 2D mask DataArray to a list of selected points (z, y, x)."""
        selected_points = []
        mask_indices = np.argwhere(mask.values)
        for idx in mask_indices:
            y_displayed, x_displayed = idx
            # Assuming single z slice for simplicity; extend as needed

            # TODO: Maybe it's time now to create a proper coordinate mapper class?
            # Initialize coordinates and map each logical axis exactly once
            x = y = z = None
            axis_mappings = [
                (self.img_axis_1, x_displayed, None),
                (self.img_axis_2, y_displayed, None),
                (self.img_axis_3, None, self.img_axis_3_slice),
            ]
            for axis_name, displayed_val, slice_val in axis_mappings:
                value = displayed_val if displayed_val is not None else slice_val
                if axis_name == "x":
                    x = value
                elif axis_name == "y":
                    y = value
                elif axis_name == "z":
                    z = value

            selected_points.append((z, y, x))
        return selected_points

    @pn.depends("selected_points")
    def selected_points_widget(self):
        """
        Display the list of selected points in a DataFrame.
        Should only be used for debugging due to potential performance issues.
        """
        if not self.selected_points:
            return pn.ui.Markdown("No points selected.")
        else:
            df = pd.DataFrame(self.selected_points, columns=["z", "y", "x"])
            return pn.widgets.DataFrame(df, autosize_mode="fit_columns", height=200)

    # === Average spectrum computation and visualization ===

    def fetch_data_from_points(self, selected_points: ZYXPoints) -> tuple[list[tuple[NDArray, NDArray, str, str]], list[dict]]:
        """
        Fetch data from the selected points.
        Returns:
            all_spectra: list of tuples (PSD, frequency, PSD_units, frequency_units)
            all_quantities: list of dicts {quantity_name: {peak_name: bls.Metadata.Item(value, units)}}
        """
        if not selected_points or self.bls_data is None:
            logger.debug(
                "No points selected or no BLS data loaded for average spectrum"
            )
            return (
                None,
                None,
            )
        else:
            all_spectra = []
            all_quantities = []
            # The data group may not have any analysis results: only the spectra are available then
            has_analysis = self.bls_data.analysis is not None
            for z, y, x in self.tqdm(
                selected_points, desc="Fetching data from points", leave=False
            ):
                if has_analysis:
                    spectrum, quantities = (
                        self.bls_data.data.get_spectrum_and_all_quantities_in_image(
                            ar=self.bls_data.analysis, coor=(z, y, x)
                        )
                    )
                else:
                    spectrum = self.bls_data.data.get_spectrum_in_image((z, y, x))
                    quantities = {}
                if spectrum[0] is None:
                    # No spectrum at this pixel (possible for sparse data)
                    continue
                all_spectra.append(spectrum)
                all_quantities.append(quantities)
            return all_spectra, all_quantities

    @pn.depends("selected_points", watch=True)
    @catch_and_notify(prefix="<b>Processing ROI: </b>")
    def update_widget(self):
        if (
            self.bls_data is None
            # (the analysis results are not required: without them only the spectrum is shown)
            or not self.bls_data.is_loaded(require_analysis=False)
            or not self.selected_points
        ):
            logger.debug(
                "No data or no points selected, skipping statistics widget update"
            )
            with pn.io.hold():
                self.spectrum_plot_widget.object = None
                self.statistic_tabulator_widget.value = self.placeholder_dataframe()
                self.statistic_tabulator_widget.visible = False
            return

        self.loading = True
        self.tqdm.visible = True

        logger.info("Updating statistics widget")

        spectra, quantities = self.fetch_data_from_points(self.selected_points)
        if not spectra:
            logger.debug("No spectra in the selected region, clearing statistics widget")
            with pn.io.hold():
                self.spectrum_plot_widget.object = None
                self.statistic_tabulator_widget.value = self.placeholder_dataframe()
                self.statistic_tabulator_widget.visible = False
                self.tqdm.visible = False
                self.loading = False
            return

        # spectra: (PSD, frequency, PSD_units, frequency_units)
        (common_freq, mean_spectrum, std_spectrum, PSD_units, frequency_units) = (
            self.compute_average_spectrum(spectra)
        )
        curve = self.plot_average_spectrum(
            common_freq, mean_spectrum, std_spectrum, PSD_units, frequency_units
        )
        self.spectrum_plot_widget.object = curve

        # quantities: result[quantity.name][peak.name] = bls.Metadata.Item(value, units)
        # There are none to show if the data group has no analysis results
        has_quantities = self.bls_data.analysis is not None
        df_quantities = (
            self.compute_average_quantities(quantities) if has_quantities else None
        )

        with pn.io.hold():
            if has_quantities:
                self.statistic_tabulator_widget.value = df_quantities
            self.statistic_tabulator_widget.visible = has_quantities
            self.tqdm.visible = False
            self.loading = False

    def compute_average_spectrum(
        self, spectra
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, str, str]:
        if spectra is None or len(spectra) == 0:
            raise ValueError("No spectra provided for averaging")
        PSDs, frequencies, PSD_units, frequency_units = zip(*spectra)
        retrieved_PSD = np.stack(PSDs)
        retrieved_frequency = np.stack(frequencies)

        with self.tqdm(total=1, desc="Interpolating spectra", leave=False) as progress:
            interpolated_psd, common_freq = Data.interpolate_spectra(
                retrieved_PSD, retrieved_frequency
            )
            progress.update(1)

        mean_spectrum = np.mean(interpolated_psd, axis=0) 
        std_spectrum = np.nanstd(interpolated_psd, axis=0)
        return (common_freq, mean_spectrum, std_spectrum, PSD_units[-1], frequency_units[-1])

    def compute_average_quantities(self, quantities) -> pd.DataFrame:
        """
        Assuming quantities: result[quantity.name][peak.name] = bls.Metadata.Item(value, units)
        """
        if quantities is None or len(quantities) == 0:
            raise ValueError("No quantities provided for averaging")

        df_rows = []
        for quantity_name in self.tqdm(
            quantities[0].keys(), desc="Averaging quantities", leave=False
        ):
            for peak_name in self.tqdm(
                quantities[0][quantity_name].keys(),
                desc=f"Averaging peaks for {quantity_name}",
                leave=False,
            ):
                values = [
                    quantities[i][quantity_name][peak_name].value
                    for i in range(len(quantities))
                ]
                mean_value = np.mean(values)
                median_value = np.median(values)
                std_value = np.std(values)
                logger.debug(
                    f"Average {quantity_name} ({peak_name}): {mean_value:.3f} ± {std_value:.3f}"
                )
                new_row = {
                    "Peak": peak_name,
                    "Quantity": quantity_name,
                    "Mean": mean_value,
                    "Median": median_value,
                    "Std": std_value,
                    "Units": quantities[0][quantity_name][peak_name].units,
                }
                df_rows.append(new_row)
        df = pd.DataFrame(df_rows)
        return df

    # === Panel display method / GUI logic===

    @pn.depends("loading", watch=True)
    def _on_loading(self):
        loading_spinner(self)  # Call the function from utils.py

    def placeholder_dataframe(
        self,
    ) -> pd.DataFrame:  # TODO: should this be it's own class?
        return pd.DataFrame(
            {
                "Peak": ["Peak placeholder"],
                "Quantity": ["Quantity placeholder"],
                "Mean": [0.0],
                "Median": [0.0],
                "Std": [1.0],
                "Units": ["Units placeholder"],
            }
        )

    def statistic_tabulator(self) -> pn.widgets.Tabulator:
        tab = pn.ui.Tabulator(
            self.placeholder_dataframe(),
            show_index=False,
            disabled=True,
            groupby=["Peak"],
            hidden_columns=["Peak"],
            configuration={
                "groupStartOpen": True
            },
            formatters={
                "Mean": ScientificFormatter(precision=3),
                "Median": ScientificFormatter(precision=3),
                "Std": ScientificFormatter(precision=3),
            },
            layout="fit_columns",
            sizing_mode="stretch_width",
        )
        return tab

    def plot_average_spectrum(
        self, common_freq, mean_spectrum, std_spectrum, PSD_units, frequency_units
    ) -> hv.Curve:
        curve = hv.Curve(
            (common_freq, mean_spectrum),
            hv.Dimension("Frequency", unit=frequency_units),
            hv.Dimension("PSD", unit=PSD_units),
            label=f"Average Spectra",
        ).opts(
            tools=["hover"],
            title="Average Spectrum of Selected Region",
        )
        spread = hv.Spread((common_freq, mean_spectrum, std_spectrum), label="Std Dev")
        plot = curve * spread
        return plot

    def __panel__(self):
        """Create Panel layout for the statistics widget."""
        card = CustomPMuiCard(
            self.mask_status,
            self.tqdm,
            self.spectrum_plot_widget,
            self.statistic_tabulator_widget,
            title="BLS Statistics",
            spinner=self.spinner,
            tooltip=self.tooltip,
            sizing_mode="stretch_width",
        )
        return card

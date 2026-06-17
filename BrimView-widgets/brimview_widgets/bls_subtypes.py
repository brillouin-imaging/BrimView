import param
import numpy as np

from panel.widgets.base import WidgetBase
from panel.custom import PyComponent
import panel as pn
import holoviews as hv
import xarray as xr

from .logging import logger
from .utils import only_on_change, catch_and_notify

from brimfile.subtypes import single_point_VIPA
from brimfile.subtypes import SubType
from .bls_data_visualizer import BlsDataVisualizer
from .bls_types import bls_param

class BlsRawDataVisualizer(WidgetBase, PyComponent):

    # === **Internal Param**
    #   we need to pass some signals, but we don't want them to
    #   be displayed on the UI. Putting precedence=-1 seems to do the trick
    # ===
    # This allows to have Param triggers, to automatically call the correct functions
    bls_data = param.ClassSelector(
        class_=bls_param,
        default=None,
        precedence=-1,
        doc="The current selected BLS file/data",
        allow_refs=True,
    )

    # coordinates of the click on the Brillouin image, in the order (z,y,x)
    dataset_zyx_coord = param.NumericTuple(
        default=None, length=3, allow_refs=True, doc=""
    )

    def __init__(self, result_plot: BlsDataVisualizer, **params):

        params["name"] = "Raw data"

        #by default the widget is not visible, it will become visible when a file containing raw data is loaded
        super().__init__(visible=False, **params)

        # Explicit annotation, because param and type hinting is not working properly
        self.bls_data: bls_param = bls_param(
            file=result_plot.param.bls_file,
            data=result_plot.param.bls_data,
            analysis=result_plot.param.bls_analysis,
        )
        self.dataset_zyx_coord: param.NumericTuple = result_plot.param.dataset_zyx_click

        self.calibration_group = None

        self._enable_switch = pn.widgets.Switch(name='Enabled', value=False)

        # Because we're not a pn.Viewer anymore, by default we lost the "card" display
        # so despite us returning a card from __panel__, the shown card didn't match
        # the card display (background color, shadows)
        self.css_classes.append("card")

    def _enabled(self) -> bool:
        return self.visible and self._enable_switch.value
    
    @param.depends("bls_data.file", watch=True)
    def _toggle_visibility(self):
        if self.bls_data.file is not None:
            if self.bls_data.file.subtype == SubType.SinglePoint_VIPA_v0_1:
                self.visible = True
                return
        self.visible = False
    
    def _get_raw_camera_image(self) -> tuple[np.ndarray, tuple[float, float, float, float] | None, float] | None:
        if self.bls_data.data is None or self.dataset_zyx_coord is None:
            return None
        # TODO: implement the possibility of loading the spectral line from the analysis results group
        raw_spectrum, spectral_line, linewidth = single_point_VIPA.get_raw_spectrum_in_image(self.bls_data.data, self.dataset_zyx_coord)
        return raw_spectrum, spectral_line, linewidth
    
    @param.depends(
        "dataset_zyx_coord",
    )
    @only_on_change(
        "dataset_zyx_coord"
    )
    @catch_and_notify(prefix="<b>BlsRawDataVisualizer._plot_data: </b>")
    def _plot_data(self):
        if not self._enabled():
            return None
        logger.debug("BlsRawDataVisualizer._plot_data")

        self.loading = True

        raw_data = self._get_raw_camera_image()
        if raw_data is None:
            self.loading = False
            return None

        raw_spectrum, spectral_line, linewidth = raw_data
        height, width = raw_spectrum.shape
        raw_spectrum_da = xr.DataArray(
            raw_spectrum,
            dims=["y", "x"],
            coords={
                "x": np.arange(width),
                "y": np.arange(height),
            },
            name="value",
        )

        # Use explicit coordinates to match how image coordinates are handled elsewhere in the app.
        img = hv.Image(raw_spectrum_da)
        img = img.opts(cmap="gray")

        def _draw_line():
            y_start, x_start, y_end, x_end = spectral_line
            dx = x_end - x_start
            dy = y_end - y_start
            length = np.hypot(dx, dy)

            if length > 0 and linewidth > 0:
                # Draw the line as a thin polygon to keep width in image data coordinates.
                half_width = linewidth / 2.0
                nx = -dy / length
                ny = dx / length
                line_polygon = [
                    (x_start + nx * half_width, y_start + ny * half_width),
                    (x_end + nx * half_width, y_end + ny * half_width),
                    (x_end - nx * half_width, y_end - ny * half_width),
                    (x_start - nx * half_width, y_start - ny * half_width),
                ]
                line_shape = hv.Polygons([line_polygon])
                return line_shape.opts(color='red', alpha=0.2, line_alpha=0)
            return None

        # Overlay spectral line on the image
        if spectral_line is not None:
            line_shape = _draw_line()
            if line_shape is not None:
                img = img * line_shape

        z, y, x = self.dataset_zyx_coord 
        img = img.opts(
            aspect="equal",
            data_aspect=1,
            title=f"Raw data for the spectrum at (z={z}, y={y}, x={x})",
            # padding=0.2,
            # responsive is not exactly working as expected, and breaks a bit the whole thing
            # See for example: https://github.com/holoviz/panel/issues/5054
            responsive=True,
        )

        self.loading = False
        return img
    
    def __panel__(self):
        return pn.Card(
            self._enable_switch,
            pn.pane.HoloViews(self._plot_data, sizing_mode="stretch_width"),
            title=self.name,
            sizing_mode="stretch_width",
            collapsed = True,
        )
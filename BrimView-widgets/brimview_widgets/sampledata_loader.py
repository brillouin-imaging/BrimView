import panel as pn
import panel_material_ui as pmui

from .utils import catch_and_notify
from .logging import logger
from .widgets import CustomPMuiCard, PathSelectorMixin

class SampledataLoader(PathSelectorMixin, pn.viewable.Viewer):

    _sampledata = {
    "Drosophila - LSBM": "https://livingobjects.ebi.ac.uk/bioimaging-integrator-data/S-BIAD3424/drosophila_LSBM.brim.zarr",
    "Zebrafish eye - confocal": "https://livingobjects.ebi.ac.uk/bioimaging-integrator-data/S-BIAD3424/zebrafish_eye_confocal.brim.zarr",
    "Zebrafish ECM - SBS": "https://livingobjects.ebi.ac.uk/bioimaging-integrator-data/S-BIAD3424/zebrafish_ECM_SBS.brim.zarr",
    "Oil beads - FTBM": "https://livingobjects.ebi.ac.uk/bioimaging-integrator-data/S-BIAD3424/oil_beads_FTBM.brim.zarr"
    }
    def __init__(self, **params):
        super().__init__(**params)

        # Sample dataset picker
        self.sampledata_load_button = pmui.Button(
            label="Load sample", color="primary", sizing_mode="stretch_width"
        )
        self.sampledata_load_button.on_click(self._load_sample_data)
        self.dataset_select = pmui.Select(
            label='Dataset',
            options=list(self._sampledata.keys()),
            sizing_mode="stretch_width")

    @catch_and_notify(prefix="<b>Load sample dataset: </b>")
    def _load_sample_data(self, event):
        sample_path = self._sampledata[self.dataset_select.value]
        if sample_path:
            logger.info(f"Selected sample dataset: {sample_path}")
            self._after_path_select(sample_path)
        else:
            logger.info("No sample dataset selected.")

    def __panel__(self):
        return CustomPMuiCard(
            pmui.FlexBox(self.dataset_select, self.sampledata_load_button),
            title="Sample data",
            collapsed=True,
            collapsible=True,
            sizing_mode="stretch_width",
            margin=5
        )
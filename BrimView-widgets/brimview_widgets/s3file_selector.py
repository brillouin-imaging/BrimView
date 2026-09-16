import panel as pn
import panel_material_ui as pmui

from .utils import catch_and_notify
from .logging import logger
from .widgets import PathSelectorMixin

class S3FileSelector(PathSelectorMixin, pn.viewable.Viewer):

    def __init__(self, **params):
        super().__init__(**params)
        
        # S3 link input
        self.s3_load_button = pmui.Button(
            label="Load S3 file", color="primary", sizing_mode="stretch_width"
        )
        self.s3_load_button.on_click(self._load_s3_file)
        self.s3_link = pmui.TextInput(
            label="S3 Link",
            placeholder="Enter S3 link to a file",
            sizing_mode="stretch_width",
        )
        self.s3_link.param.watch(
            self._load_s3_file, ["enter_pressed"], onlychanged=False
        )

    @catch_and_notify(prefix="<b>Load S3 file: </b>")
    def _load_s3_file(self, event):
        s3_path = self.s3_link.value
        if s3_path:
            logger.info(f"Selected file: {s3_path}")
            self._after_path_select(s3_path)
        else:
            logger.info("No file selected.")

    def __panel__(self):
        return pmui.FlexBox(self.s3_link, self.s3_load_button)
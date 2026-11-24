from pathlib import Path

import panel as pn

from .environment import is_running_from_docker
from .logging import logger
from .s3file_selector import S3FileSelector
from .widgets import CustomPMuiCard, PathSelectorMixin

_running_from_docker = is_running_from_docker()


class TinkerFileSelector(PathSelectorMixin, pn.viewable.Viewer):
    """
    Select files and directories on the Panel server or load data from S3.
    """

    def __init__(self, **params):
        super().__init__(**params)

        if not _running_from_docker:
            home = Path.home()
            self.file_selector = pn.widgets.FileSelector(
                directory=str(home),
                root_directory=home.anchor,
                only_files=False,
                sizing_mode="stretch_width",
            )
            self.load_button = pn.ui.Button(
                label="Load selected path", color="primary", sizing_mode="stretch_width",
            )
            self.load_button.on_click(self._load_selected_path)
            self.selection_alert = pn.ui.Alert(
                object="Select exactly one file or directory.",
                severity="warning",
                visible=False,
                sizing_mode="stretch_width",
            )
            self.file_dialog = pn.ui.Dialog(
                self.file_selector,
                self.selection_alert,
                self.load_button,
                title="Select local data",
                width_option="md",
                close_on_click=True,
                show_close_button=True,
                width=0,
                height=0,
                sizing_mode="fixed",
            )
            self.select_button = pn.ui.Button(
                label="Select local data", color="primary", sizing_mode="stretch_width",
            )
            self.select_button.on_click(self._show_file_dialog)

        # S3 link input
        self.s3FileSelector = S3FileSelector()

    def input_and_load_s3_file(self, s3_url: str):
        """
            This function takes the url to an s3 file and load it as the current image
        """
        self.s3FileSelector.s3_link.value = s3_url
        async def _trigger_S3_loading():
            # trigger the click of the button
            # https://discourse.holoviz.org/t/how-to-trigger-on-click-event-of-the-button-widget/1996/3
            self.s3FileSelector.s3_load_button.clicks +=1
        pn.state.onload(_trigger_S3_loading)

    def _show_file_dialog(self, event):
        self.selection_alert.visible = False
        self.file_dialog.open = True

    def _load_selected_path(self, event):
        browser = self.file_selector._selector
        highlighted = browser._lists[False].value
        if highlighted:
            paths = [browser.options.get(label) for label in highlighted]
        else:
            paths = self.file_selector.value
        if len(paths) != 1 or paths[0] in (None, ".."):
            self.selection_alert.visible = True
            logger.info("Select exactly one file or directory.")
            return
        logger.info(f"Selected path: {paths[0]}")
        self.selection_alert.visible = False
        self.file_dialog.open = False
        self._after_path_select(paths[0])

    def set_update_function(self, func):
        """
        Set the function to be called when a file is selected.
        This function should accept a single argument, which is the path to the selected file.
        """
        super().set_update_function(func)
        self.s3FileSelector.set_update_function(func)

    def __panel__(self):
        if not _running_from_docker:
            local_data_widget = CustomPMuiCard(
                    pn.ui.Column(
                        self.select_button,
                        self.file_dialog,
                        sizing_mode="stretch_width",
                    ),
                    title="Local data",
                    sizing_mode="stretch_width",
                    margin=5

                )
        else:
            local_data_widget = CustomPMuiCard(
                    pn.ui.HTML("<a href='./local/index.html'>Load in-browser version</a>"),
                    title="Local data",
                    margin=5,
                    sizing_mode="stretch_width",
                    collapsed = True
                )

        return pn.ui.Column(
            local_data_widget,
            self.s3FileSelector
        )

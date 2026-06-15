import param

from panel.widgets.base import WidgetBase
from panel.custom import PyComponent
import panel as pn

import brimfile as bls
from brimfile.subtypes import SubType
from .bls_file_input import BlsFileInput

class BlsRawDataVisualizer(WidgetBase, PyComponent):

    # === **Internal Param**
    #   we need then to pass some signals, but we don't want them to
    #   be diplayed on the UI. Puting precedence=-1 seems to do the trick
    # ===
    # This allows to have Param triggers, to automatically call the correct functions
    bls_data = param.ClassSelector(class_=bls.Data, default=None, allow_refs=True)
    bls_file = param.ClassSelector(class_=bls.File, default=None, allow_refs=True)

    def __init__(self, file: BlsFileInput, **params):

        params["name"] = "Raw data"

        #by default the widget is not visible, it will become visible when a file containing raw data is loaded
        super().__init__(visible=False, **params)

        # Explicit annotation, because param and type hinting is not working properly
        self.bls_file: bls.File = file.param.bls_file
        self.bls_data: bls.Data = file.param.data

    
    @param.depends("bls_file", watch=True)
    def _toggle_visibility(self):
        if self.bls_file is not None:
            if self.bls_file.subtype == SubType.SinglePoint_VIPA_v0_1:
                self.visible = True
                return
        self.visible = False
    
    def __panel__(self):
        return pn.Card(
            pn.pane.HoloViews(sizing_mode="stretch_width"),
            title=self.name,
            margin=5,
            sizing_mode="stretch_width",
            collapsed = True,
        )
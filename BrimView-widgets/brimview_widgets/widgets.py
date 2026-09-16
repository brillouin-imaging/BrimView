import panel as pn
import panel_material_ui as pmui
import param

from .utils import catch_and_notify


class PathSelectorMixin:
    """
    Shared plumbing for widgets that let the user pick a file/dataset path (S3 link,
    local file dialog, sample dataset, ...) and forward it to a caller-supplied callback.

    Mix this in *before* the Viewer base class, e.g. ``class Foo(PathSelectorMixin,
    pn.viewable.Viewer)``, so its cooperative ``super().__init__()`` chain reaches
    ``Viewer.__init__`` correctly.

    A subclass is responsible for calling ``self._after_path_select(path)`` once a path
    has actually been chosen (from a button click, drag-and-drop, file dialog, etc.) -
    this class only owns the "where does the chosen path go" plumbing.
    """

    def __init__(self, **params):
        super().__init__(**params)
        self.process_path_fn = None

    def set_update_function(self, func):
        """
        Set the function to be called when a file is selected.
        This function should accept a single argument, which is the path to the selected file.
        """
        self.process_path_fn = func

    @catch_and_notify(prefix="<b>Open file: </b>")
    def _after_path_select(self, file_path: str):
        if self.process_path_fn is not None:
            self.process_path_fn(file_path)


def CustomPMuiCard(*objects, spinner=None, tooltip=None, title=None, **params):
    title_typography = pmui.Typography(title or "", variant="h6")
    header = pn.Row(
        title_typography,
        pn.Spacer(),
        sizing_mode="stretch_width",
        align="center",
    )
    if tooltip is not None:
        header.append(pn.widgets.TooltipIcon(value=tooltip))
    if spinner is not None:
        header.append(spinner)
    card = pmui.Card(*objects, header=header, **params)
    
    # Add a method to set the title of the card dynamically
    card.set_title = lambda title: setattr(title_typography, "object", title)

    return card

class SwitchWithLabels(pn.viewable.Viewer):
    label_true = param.String(default="On", doc="Label when switch is True")
    label_false = param.String(default="Off", doc="Label when switch is False")
    value = param.Boolean(default=False, doc="Switch value")
    
    def __init__(self, **params):
        super().__init__(**params)

        self._switch = pn.widgets.Switch.from_param(self.param.value)
        # Hide the label of the switch itself
        self._switch.name = ""
        self._switch.align = "center"
        self._layout = pn.Row(self.label_false, self._switch, self.label_true)

    @pn.depends("label_true", watch=True)
    def _update_label_true(self):
        self._label_true.object = self.label_true

    @pn.depends("label_false", watch=True)
    def _update_label_false(self):
        self._label_false.object = self.label_false

    def __panel__(self):
        return self._layout

    

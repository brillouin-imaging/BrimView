# pyright: reportAssignmentType=false
"""
Loading a Zarr dataset that sits in the user's browser (a ``.zip`` file or a ``.zarr`` folder).

Only meant for the Pyodide build, where Python runs in a Web Worker while the page, and therefore
the file dialog, lives on the main thread. The whole round trip is one message each way:

    main thread (browser_file_picker.js)               Pyodide worker
    ------------------------------------               --------------
    user clicks a button
      -> <input type="file">.click()
         (must be synchronous JS: browsers only open
          a file dialog from inside a real click)
      -> worker.postMessage({type: "load_file",
                             target, files})  ------->  handleLoadFile()          (src/zarr_wrapper.js)
                                                          -> on_files_picked()    (this module)
                                                               -> open_browser_zarr(files) -> bls.File
                                                               -> loader.process_path_fn(bls_file)

Nothing is exchanged through a shared Bokeh property and no module-level global carries the
loaded file around: the result of each step is simply the argument of the next one.
"""
import uuid
import weakref
from pathlib import Path

import panel as pn
import param
from panel.custom import Child, JSComponent

from .utils import catch_and_notify
from .widgets import CustomPMuiCard, PathSelectorMixin

_DOC_LINK = (
    'See <a href="https://brillouin-imaging.github.io/brimfile/brimfile.html#store-types" '
    'target="_blank" rel="noopener noreferrer">documentation</a> for supported formats.'
)

# The worker only knows a loader by the id it was given in `target`. Weak, so a loader that is
# garbage-collected simply disappears from the registry.
_loaders: "weakref.WeakValueDictionary[str, CustomJSFileInput]" = weakref.WeakValueDictionary()


def open_browser_zarr(sources):
    """
    Open, as a ``brimfile.File``, a Zarr store that the browser can reach. Pyodide only.

    `sources` is whatever ``init_file`` (brimfile's zarr_file.js) accepts: a JS array holding one
    ``.zip`` File, the Files of a picked folder, or a list with a single URL (e.g. ``[s3_url]``).
    """
    import brimfile as bls
    from brimfile.file_abstraction import _zarrFile  # private, but brimfile has no public hook for JS-backed stores
    from js import initZarrFile  # defined in src/zarr_wrapper.js

    js_zarr = initZarrFile(sources)
    return bls.File(_zarrFile(js_zarr.zarr_file_js, filename=js_zarr.filename))


@catch_and_notify(prefix="<b>Loading file: </b>")
def on_files_picked(target, files):
    """
    Entry point called from the worker (``handleLoadFile`` in src/zarr_wrapper.js) with the Files the
    user picked. `target` is the id of the `CustomJSFileInput` that owns the buttons.
    """
    loader = _loaders.get(target)
    if loader is None:
        raise RuntimeError(f"No file input is registered under the id {target!r}")
    loader._after_path_select(open_browser_zarr(files))


class BrowserFilePicker(JSComponent):
    """
    Two buttons wired to hidden ``<input type="file">`` elements, see browser_file_picker.js.
    This class only declares what the JS needs; the logic lives in `CustomJSFileInput`.
    """

    uid = param.String(doc="Id sent along with the picked files, so the worker can find the owning loader")
    zip_button = Child()
    folder_button = Child()

    _esm = Path(__file__).with_name("browser_file_picker.js")

    @catch_and_notify(prefix="<b>Loading file: </b>")
    def _handle_msg(self, msg):
        # `model.send_msg({error: "..."})` from the JS lands here. (Not `send_event`: that one runs its
        # argument through a DOM-event serializer, which drops custom keys.)
        if "error" in msg:
            raise RuntimeError(msg["error"])


class CustomJSFileInput(PathSelectorMixin, pn.viewable.Viewer):
    """
    Card with two buttons to load a ``.zip`` file or a ``.zarr`` folder from the user's disk.

    Register the callback with ``set_update_function(func)``: it is called with the opened
    ``brimfile.File`` (not with a path, unlike the other selectors).
    """

    def __init__(self, **params):
        super().__init__(**params)
        self._uid = uuid.uuid4().hex
        _loaders[self._uid] = self
        self._picker = BrowserFilePicker(
            uid=self._uid,
            zip_button=pn.ui.Button(label="Load a .zip file", color="primary", sizing_mode="stretch_width"),
            folder_button=pn.ui.Button(label="Load a .zarr folder", color="primary", sizing_mode="stretch_width"),
            sizing_mode="stretch_width",
        )
        self._card = CustomPMuiCard( pn.ui.Column(pn.ui.HTML(_DOC_LINK), self._picker), 
                                    collapsed=True,
                                    collapsible=True,
                                    sizing_mode="stretch_width",
                                    title="Local data", 
                                    margin=5)

    def __panel__(self):
        return self._card

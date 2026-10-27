// Main-thread half of `CustomJSFileInput` (see browser_file_selectors.py for the big picture).
//
// Why this is JS and not a Python callback: a browser only opens a file dialog from inside a real
// user click, so the click handler has to be synchronous JS. The picked File objects then go
// straight to the Pyodide worker with postMessage (they can't travel through Bokeh).
//
// The two buttons are ordinary pmui buttons passed in as `Child`ren by Python. We never look them up
// by id or through Bokeh internals: `model.get_child()` hands us their elements directly.

export function render({ model, el }) {
  const zipButton = model.get_child("zip_button");
  const folderButton = model.get_child("folder_button");

  // Hidden <input type="file"> elements that live and die with this component. They are created
  // once (not per click), so listeners can't pile up when a dialog is cancelled.
  const zipInput = makeInput({ accept: ".zip" });
  const folderInput = makeInput({ multiple: true });
  folderInput.webkitdirectory = true;

  // style of a pn.ui.Column
  el.style.cssText = "display: flex; flex-direction: column; width: 100%;";
  el.append(zipButton, folderButton);

  // `click` is a native, composed event: it reaches the host element of a pmui button from inside
  // its shadow DOM, still within the user gesture that browsers require to open a file dialog.
  zipButton.addEventListener("click", () => zipInput.click());
  folderButton.addEventListener("click", () => folderInput.click());
  zipInput.addEventListener("change", () => send(zipInput));
  folderInput.addEventListener("change", () => send(folderInput));

  // Errors that happen in the worker *before* Python takes over (Python-side errors are notified from
  // Python itself). Forwarded to Python so that they end up as a regular toast.
  const worker = findWorker();
  const onWorkerMessage = ({ data }) => {
    if (data?.type === "file_load_error" && data.target === model.uid) {
      model.send_msg({ error: data.message });
    }
  };
  worker?.addEventListener("message", onWorkerMessage);
  model.on("remove", () => worker?.removeEventListener("message", onWorkerMessage));

  function makeInput(attributes) {
    const input = Object.assign(document.createElement("input"), { type: "file", hidden: true }, attributes);
    el.appendChild(input);
    return input;
  }

  function send(input) {
    const files = Array.from(input.files);
    // Reset, otherwise picking the same file/folder a second time fires no `change` event.
    // (`files` is a copy, so the File objects stay valid.)
    input.value = "";
    if (files.length === 0) return;

    const currentWorker = findWorker();
    if (!currentWorker) {
      model.send_msg({ error: "No Pyodide worker found: local files can only be loaded in the browser (Pyodide) build." });
      return;
    }
    // Picked up by `handleLoadFile` in src/zarr_wrapper.js, which calls
    // brimview_widgets.browser_file_selectors.on_files_picked(target, files) in Python.
    currentWorker.postMessage({ type: "load_file", target: model.uid, files });
  }
}

function findWorker() {
  // Panel's generated page declares `const pyodideWorker = new Worker(...)` in a classic <script>.
  // A top-level `const` is visible by bare name to every script and module, but it is NOT a
  // property of `window`. build_webapp.py also publishes it as `window.pyodideWorker`, which is
  // the contract we rely on; the bare name is a fallback for pages built without that patch.
  if (globalThis.pyodideWorker) return globalThis.pyodideWorker;
  return typeof pyodideWorker !== "undefined" ? pyodideWorker : undefined;
}

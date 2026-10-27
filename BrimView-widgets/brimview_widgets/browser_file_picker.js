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

  // add a link to the brimfile docs for supported file types
  const _DOC_LINK = 'See <a href="https://brillouin-imaging.github.io/brimfile/brimfile.html#store-types" target="_blank">brimfile docs</a> for supported file types.';
  const docLink = document.createElement("div");
  docLink.innerHTML = _DOC_LINK;
  docLink.style.cssText = "margin: 0.5em 0; color: var(--pmui-text-secondary);";
  el.appendChild(docLink);

  // drag-and-drop hint: icon and text above a horizontal row with the two buttons

  // define the icon inline
  const ICON_SVG = `
            <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 32 32"
                width="32"
                height="32"
                fill="currentColor"
                aria-hidden="true"
            >
                <path d="M19.35 10.04A7.49 7.49 0 0 0 5 9
                    a5.5 5.5 0 0 0 .5 11h13a4.5 4.5 0 0 0
                    .85-9.96ZM13 16v-4h3l-4-4-4 4h3v4Z"/>
            </svg>
        `;  
  const dropIcon = document.createElement("span");
  dropIcon.innerHTML = ICON_SVG;
  dropIcon.style.color = "var(--mui-palette-primary-main, #1976d2)";
  dropIcon.style.display = "inline-flex";
  dropIcon.style.alignItems = "center";
  // define the hint div with the icon and text
  const hint = document.createElement("div");
  hint.innerHTML = "<b>Drag&Drop here</b></br>or load";
  hint.style.cssText = "text-align: center;";
  const iconBox = document.createElement("div");
  iconBox.style.cssText = "display: flex; justify-content: center;";
  iconBox.append(dropIcon);
  // add the buttons
  const buttonRow = document.createElement("div");
  buttonRow.style.cssText = "display: flex; flex-direction: row; gap: 0.5em; width: 100%;";
  zipButton.style.flex = folderButton.style.flex = "1";
  buttonRow.append(zipButton, folderButton);
  el.append(iconBox, hint, buttonRow);

  // `click` is a native, composed event: it reaches the host element of a pmui button from inside
  // its shadow DOM, still within the user gesture that browsers require to open a file dialog.
  zipButton.addEventListener("click", () => zipInput.click());
  folderButton.addEventListener("click", () => folderInput.click());
  zipInput.addEventListener("change", () => send(zipInput));
  folderInput.addEventListener("change", () => send(folderInput));

  // Drag and drop of a .zip file or a folder onto the component.
  let dragDepth = 0;
  const setHighlight = (on) => { el.style.outline = on ? "2px dashed currentColor" : ""; };
  el.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth++; setHighlight(true); });
  el.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "link"; });
  el.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; setHighlight(false); } });
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    setHighlight(false);
    // Entries must be taken synchronously: the DataTransfer is emptied after the handler returns.
    const entries = Array.from(e.dataTransfer.items)
      .map((item) => item.webkitGetAsEntry?.())
      .filter(Boolean);
    collectDropped(entries).then(({ files, paths }) => post(files, paths));
  });

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
    post(files);
  }

  // `paths` (dropped folders only) holds each file's path relative to the drop, because expando
  // properties on a File do not survive postMessage; the worker re-attaches them.
  function post(files, paths) {
    if (files.length === 0) return;

    const currentWorker = findWorker();
    if (!currentWorker) {
      model.send_msg({ error: "No Pyodide worker found: local files can only be loaded in the browser (Pyodide) build." });
      return;
    }
    // Picked up by `handleLoadFile` in src/zarr_wrapper.js, which calls
    // brimview_widgets.browser_file_selectors.on_files_picked(target, files) in Python.
    currentWorker.postMessage({ type: "load_file", target: model.uid, files, paths });
  }
}

async function collectDropped(entries) {
  const files = [];
  const paths = [];
  const readAll = (reader) => new Promise((resolve, reject) => {
    const all = [];
    const next = () => reader.readEntries((batch) => {
      if (batch.length === 0) resolve(all);
      else { all.push(...batch); next(); }
    }, reject);
    next();
  });
  const walk = async (entry) => {
    if (entry.isFile) {
      files.push(await new Promise((resolve, reject) => entry.file(resolve, reject)));
      paths.push(entry.fullPath.replace(/^\/+/, ""));
    } else if (entry.isDirectory) {
      for (const child of await readAll(entry.createReader())) await walk(child);
    }
  };
  for (const entry of entries) await walk(entry);

  // A single dropped file is passed as is (e.g. a .zip); only folders need relative paths.
  const isFolder = entries.some((entry) => entry.isDirectory);
  return { files, paths: isFolder ? paths : undefined };
}

function findWorker() {
  // Panel's generated page declares `const pyodideWorker = new Worker(...)` in a classic <script>.
  // A top-level `const` is visible by bare name to every script and module, but it is NOT a
  // property of `window`. build_webapp.py also publishes it as `window.pyodideWorker`, which is
  // the contract we rely on; the bare name is a fallback for pages built without that patch.
  if (globalThis.pyodideWorker) return globalThis.pyodideWorker;
  return typeof pyodideWorker !== "undefined" ? pyodideWorker : undefined;
}

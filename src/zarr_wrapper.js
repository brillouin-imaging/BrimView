// Loads a browser-selected file/folder/URL into a real `zarr`-backed
// `brimfile.File`, running through Pyodide's own JS interop and
// `pyodide.http.pyfetch` - no separate JS Zarr client is needed any more:
// brimfile's Pyodide `_zarrFile` now uses the real `zarr` package directly,
// the same one used server-side, via a small `Store` adapter picked for
// whichever kind of browser input was given (see
// brimfile.file_abstraction: _BrowserFolderStore, _BrowserFetchStore,
// _read_whole_js_file + zarr.storage.ZipStore). Requires Pyodide >= 314.0.1
// (the first release with a working zarr 3.x + numcodecs pair - see
// brimfile's tests/test_file_abstraction_pyodide.py for details).

/**
 * Initializes a Zarr-backed Brillouin file in Pyodide from the selected browser files.
 *
 * Builds the corresponding `brimfile.File` directly from the browser input
 * (via `brimview_widgets.load_browser_file`) and stores it through
 * `CustomJSFileInput` for later use.
 *
 * @param {FileList|File[]|string[]} file_list Non-empty browser file input:
 * a single `.zip` File, a folder file list/array (each entry with
 * `webkitRelativePath` so the folder hierarchy can be reconstructed), or a
 * single-element array containing a URL string (e.g. an S3 bucket link).
 * @returns {boolean} Returns `true` after the Pyodide-side file object has been created.
 */
async function loadZarrFile(file_list) {
    let source, store_type_name;

    if (file_list.length === 1 && file_list[0] instanceof File && file_list[0].name.endsWith('.zip')) {
        source = file_list[0];
        store_type_name = 'ZIP';
    } else if (file_list.length === 1 && typeof file_list[0] === 'string') {
        // If it's a string, we assume it's a URL
        source = file_list[0];
        store_type_name = 'S3';
    } else if (
        file_list
        && typeof file_list.length === 'number'
        && file_list.length > 0
        && typeof file_list[0]?.arrayBuffer === 'function'
    ) {
        // Normalize to a real JS Array first, for reliable indexing/length
        // access from Python regardless of pyodide version (a FileList isn't
        // guaranteed to get the same subscripting support a plain Array does).
        source = Array.from(file_list);
        store_type_name = 'FOLDER';
    } else {
        throw new Error("'file' needs to be either a File object, a folder file list, or a url");
    }

    const load_browser_file = pyodide.pyimport("brimview_widgets").load_browser_file;
    // `source` is passed straight through: pyodide wraps it as a JsProxy
    // automatically, and `load_browser_file` (brimview_widgets) hands it
    // directly to `brimfile.File(...)`, which builds the real zarr Store for
    // it - no separate pyodide.toPy()/runPython() string is needed any more.
    await load_browser_file(source, store_type_name);
    return true;
}
// make sure loadZarrFile is in the global scope
self.loadZarrFile = loadZarrFile;

import { ZarrFile, init_file } from "https://cdn.jsdelivr.net/gh/brillouin-imaging/brimfile@main/src/js/zarr_file.js";

// This file is appended to the Pyodide worker script by build_webapp.py.

/**
 * Creates the JS-side Zarr wrapper that `brimfile` reads from.
 *
 * Called from Python (`from js import initZarrFile`, see `open_browser_zarr` in
 * brimview_widgets/browser_file_selectors.py). Accepts what `init_file()` accepts:
 * - a list with one `.zip` File;
 * - the Files of a folder picker, each with `webkitRelativePath`/`relativePath` so the hierarchy can
 *   be rebuilt (the first path segment is the dataset name);
 * - a list with a single URL string (e.g. an S3 link).
 * @returns {{zarr_file_js: ZarrFile, filename: string}}
 */
self.initZarrFile = init_file;

/**
 * Handles `{type: "load_file", target, files}` posted by the file picker on the main thread
 * (brimview_widgets/browser_file_picker.js). build_webapp.py routes that message type here.
 */
self.handleLoadFile = async ({ target, files, paths }) => {
    // Dropped folders: File objects lose their relative path when cloned, so it is sent separately.
    if (paths) {
        files.forEach((file, i) => Object.defineProperty(file, "relativePath", { value: paths[i] }));
    }
    const locals = pyodide.toPy({ target, files });
    try {
        // runPythonAsync provides the promising Python entry point needed by run_sync (JSPI).
        // Python errors are notified from Python (`catch_and_notify`); this catch is for the rest.
        await pyodide.runPythonAsync(`
from brimview_widgets.browser_file_selectors import on_files_picked
on_files_picked(target, files)
`, { locals });
    } catch (error) {
        console.error("[worker] load_file failed:", error);
        self.postMessage({ type: "file_load_error", target, message: String(error) });
    } finally {
        locals.destroy();
    }
};

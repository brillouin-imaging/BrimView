"""Python-side tests for the browser file loader (no browser, no Pyodide needed)."""
import gc
import sys
import types

import panel as pn
import pytest

from brimview_widgets import browser_file_selectors as bfs


@pytest.fixture
def notifications(monkeypatch):
    """Capture the toasts that `catch_and_notify` would show."""
    class Spy:
        errors: list[str] = []
        def error(self, msg, duration=None):
            self.errors.append(msg)
    spy = Spy()
    spy.errors = []
    monkeypatch.setattr(type(pn.state), "notifications", property(lambda self: spy))
    return spy


@pytest.fixture
def fake_zarr(monkeypatch):
    opened = []
    monkeypatch.setattr(bfs, "open_browser_zarr", lambda files: opened.append(files) or f"bls_file({files})")
    return opened


def test_picked_files_reach_the_update_function(fake_zarr):
    received = []
    loader = bfs.CustomJSFileInput()
    loader.set_update_function(received.append)

    bfs.on_files_picked(loader._uid, ["a.zip"])

    assert fake_zarr == [["a.zip"]]
    assert received == ["bls_file(['a.zip'])"]


def test_each_loader_gets_its_own_files(fake_zarr):
    first, second = bfs.CustomJSFileInput(), bfs.CustomJSFileInput()
    got = {"first": [], "second": []}
    first.set_update_function(got["first"].append)
    second.set_update_function(got["second"].append)

    bfs.on_files_picked(second._uid, ["b.zip"])

    assert got == {"first": [], "second": ["bls_file(['b.zip'])"]}


def test_unknown_target_is_notified_not_raised(notifications):
    bfs.on_files_picked("nope", [])
    assert len(notifications.errors) == 1 and "nope" in notifications.errors[0]


def test_error_in_update_function_is_notified(fake_zarr, notifications):
    loader = bfs.CustomJSFileInput()
    loader.set_update_function(lambda f: 1 / 0)
    bfs.on_files_picked(loader._uid, ["a.zip"])
    assert "ZeroDivisionError" in notifications.errors[0]


def test_js_reported_error_becomes_a_notification(notifications):
    picker = bfs.CustomJSFileInput()._picker
    picker._handle_msg({"error": "worker exploded"})
    assert "worker exploded" in notifications.errors[0]


def test_loader_registry_does_not_keep_loaders_alive():
    loader = bfs.CustomJSFileInput()
    uid = loader._uid
    del loader
    gc.collect()
    assert uid not in bfs._loaders


def test_open_browser_zarr_builds_a_brimfile_from_the_js_object(monkeypatch):
    calls = {}
    js = types.ModuleType("js")
    js.initZarrFile = lambda sources: types.SimpleNamespace(zarr_file_js="JS_ZARR", filename="x.zip")
    monkeypatch.setitem(sys.modules, "js", js)

    import brimfile
    from brimfile import file_abstraction
    monkeypatch.setattr(file_abstraction, "_zarrFile", lambda zf, filename: calls.update(zf=zf, filename=filename) or "ZF", raising=False)
    monkeypatch.setattr(brimfile, "File", lambda zf: ("bls.File", zf))

    assert bfs.open_browser_zarr(["x.zip"]) == ("bls.File", "ZF")
    assert calls == {"zf": "JS_ZARR", "filename": "x.zip"}

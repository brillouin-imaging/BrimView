from pathlib import Path

import pytest

from brimview_widgets import local_file_selectors


@pytest.fixture
def selector(monkeypatch, tmp_path):
    monkeypatch.setattr(local_file_selectors, "_running_from_docker", False)
    monkeypatch.setattr(local_file_selectors.Path, "home", classmethod(lambda cls: tmp_path))
    return local_file_selectors.TinkerFileSelector()


def test_selector_can_browse_outside_home(selector, tmp_path):
    assert selector.file_selector.directory == str(tmp_path)
    assert selector.file_selector.root_directory == str(Path(tmp_path.anchor))


def test_file_dialog_does_not_expand_sidebar(selector):
    assert selector.file_dialog.width == 0
    assert selector.file_dialog.height == 0
    assert not selector.file_dialog.open

    selector.select_button.clicks += 1

    assert selector.file_dialog.open


@pytest.mark.parametrize("is_directory", [False, True])
def test_selected_file_or_directory_is_forwarded(selector, tmp_path, is_directory):
    path = tmp_path / ("dataset.zarr" if is_directory else "dataset.bls.zip")
    if is_directory:
        path.mkdir()
    else:
        path.touch()
    selector.file_selector._update_files()
    received = []
    selector.set_update_function(received.append)

    selector.select_button.clicks += 1
    selector.file_selector._selector.value = [str(path)]
    selector.load_button.clicks += 1

    assert received == [str(path)]
    assert not selector.file_dialog.open


@pytest.mark.parametrize("is_directory", [False, True])
def test_highlighted_file_or_directory_is_forwarded(selector, tmp_path, is_directory):
    path = tmp_path / ("dataset with spaces.zarr" if is_directory else "dataset with spaces.zip")
    if is_directory:
        path.mkdir()
    else:
        path.touch()
    selector.file_selector._update_files()
    browser = selector.file_selector._selector
    label = next(label for label, value in browser.options.items() if value == str(path))
    received = []
    selector.set_update_function(received.append)

    selector.select_button.clicks += 1
    browser._lists[False].value = [label]
    assert selector.file_selector.value == []
    selector.load_button.clicks += 1

    assert received == [str(path)]
    assert not selector.file_dialog.open


def test_empty_or_multiple_selection_is_not_forwarded(selector, tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    first.touch()
    second.touch()
    selector.file_selector._update_files()
    received = []
    selector.set_update_function(received.append)

    selector.select_button.clicks += 1
    selector.load_button.clicks += 1
    assert selector.selection_alert.visible
    selector.file_selector._selector.value = [str(first), str(second)]
    selector.load_button.clicks += 1

    assert received == []
    assert selector.file_dialog.open


def test_parent_directory_entry_is_not_loaded(selector):
    received = []
    selector.set_update_function(received.append)
    browser = selector.file_selector._selector
    parent_label = next(label for label, value in browser.options.items() if value == "..")

    selector.select_button.clicks += 1
    browser._lists[False].value = [parent_label]
    selector.load_button.clicks += 1

    assert received == []
    assert selector.file_dialog.open
    assert selector.selection_alert.visible


def test_docker_does_not_create_local_file_selector(monkeypatch):
    monkeypatch.setattr(local_file_selectors, "_running_from_docker", True)

    def unexpected_selector(**kwargs):
        raise AssertionError("Docker should not browse the server filesystem")

    monkeypatch.setattr(local_file_selectors.pn.widgets, "FileSelector", unexpected_selector)
    selector = local_file_selectors.TinkerFileSelector()

    assert selector.__panel__() is not None
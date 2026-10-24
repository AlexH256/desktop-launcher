import os
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from desktop_launcher.core.search import AppEntry
from desktop_launcher.core.search_config import SearchConfigStore
from desktop_launcher.main import _activate_entry, _launch_entry

ENTRY = AppEntry("App", Path("C:/Tools/App.lnk"))


def make_store(tmp_path: Path) -> SearchConfigStore:
    store = SearchConfigStore(tmp_path / "search-config.json")
    store.load()
    return store


def test_success_launches_and_hides_window(monkeypatch) -> None:
    startfile = Mock()
    monkeypatch.setattr(os, "startfile", startfile, raising=False)
    window = Mock()

    assert _launch_entry(window, ENTRY) is True
    startfile.assert_called_once_with(str(ENTRY.path))
    window.hide_launcher.assert_called_once_with()


def test_failure_shows_warning_and_keeps_window(monkeypatch) -> None:
    def fail(_path: str) -> None:
        raise OSError("boom")

    warning = Mock()
    monkeypatch.setattr(os, "startfile", fail, raising=False)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    window = Mock()

    assert _launch_entry(window, ENTRY) is False
    warning.assert_called_once()
    window.hide_launcher.assert_not_called()


def test_activate_entry_records_weight(tmp_path: Path, monkeypatch) -> None:
    startfile = Mock()
    monkeypatch.setattr(os, "startfile", startfile, raising=False)
    store = make_store(tmp_path)
    window = Mock()

    _activate_entry(window, ENTRY, store)

    assert store.weight_for(ENTRY.path) == 1
    window.set_search_config.assert_called_once_with(store.snapshot())
    window.hide_launcher.assert_called_once_with()


def test_activate_entry_failure_does_not_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail(_path: str) -> None:
        raise OSError("boom")

    warning = Mock()
    monkeypatch.setattr(os, "startfile", fail, raising=False)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    store = make_store(tmp_path)
    window = Mock()

    _activate_entry(window, ENTRY, store)

    assert store.weight_for(ENTRY.path) == 0
    window.set_search_config.assert_not_called()
    window.hide_launcher.assert_not_called()

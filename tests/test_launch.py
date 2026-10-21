import os
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from desktop_launcher.core.search import AppEntry
from desktop_launcher.main import _launch_entry

ENTRY = AppEntry("App", Path("C:/Tools/App.lnk"))


def test_success_launches_and_hides_window(monkeypatch) -> None:
    startfile = Mock()
    monkeypatch.setattr(os, "startfile", startfile, raising=False)
    window = Mock()

    _launch_entry(window, ENTRY)

    startfile.assert_called_once_with(str(ENTRY.path))
    window.hide_launcher.assert_called_once_with()


def test_failure_shows_warning_and_keeps_window(monkeypatch) -> None:
    def fail(_path: str) -> None:
        raise OSError("boom")

    warning = Mock()
    monkeypatch.setattr(os, "startfile", fail, raising=False)
    monkeypatch.setattr(QMessageBox, "warning", warning)
    window = Mock()

    _launch_entry(window, ENTRY)

    warning.assert_called_once()
    window.hide_launcher.assert_not_called()

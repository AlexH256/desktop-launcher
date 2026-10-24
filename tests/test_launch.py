import os
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtWidgets import QMessageBox

from desktop_launcher.core.search import AppEntry
from desktop_launcher.core.search_config import SearchConfigStore
from desktop_launcher.main import LaunchController, _LaunchTask

ENTRY = AppEntry("App", Path("C:/Tools/App.lnk"))


class SyncThreadPool:
    def start(self, task) -> None:
        task.run()


def make_store(tmp_path: Path) -> SearchConfigStore:
    store = SearchConfigStore(tmp_path / "search-config.json")
    store.load()
    return store


def test_launch_task_emits_success(monkeypatch) -> None:
    startfile = Mock()
    monkeypatch.setattr(os, "startfile", startfile, raising=False)
    signals = Mock()

    _LaunchTask(ENTRY, signals).run()

    startfile.assert_called_once_with(str(ENTRY.path))
    signals.succeeded.emit.assert_called_once_with(ENTRY)
    signals.failed.emit.assert_not_called()


def test_launch_task_emits_failure(monkeypatch) -> None:
    def fail(_path: str) -> None:
        raise OSError("boom")

    monkeypatch.setattr(os, "startfile", fail, raising=False)
    signals = Mock()

    _LaunchTask(ENTRY, signals).run()

    signals.failed.emit.assert_called_once_with(ENTRY, "boom")
    signals.succeeded.emit.assert_not_called()


def test_controller_hides_before_launch_and_records_weight(
    tmp_path: Path,
    monkeypatch,
    qapp,
) -> None:
    calls: list[tuple[str, str]] = []

    def startfile(path: str) -> None:
        calls.append(("startfile", path))

    monkeypatch.setattr(os, "startfile", startfile, raising=False)
    store = make_store(tmp_path)
    window = Mock()
    window.hide_launcher.side_effect = lambda: calls.append(("hide", ""))
    controller = LaunchController(window, store, thread_pool=SyncThreadPool())

    controller.launch(ENTRY)

    assert calls == [("hide", ""), ("startfile", str(ENTRY.path))]
    assert store.weight_for(ENTRY.path) == 0

    qapp.processEvents()

    assert store.weight_for(ENTRY.path) == 1
    window.set_search_config.assert_called_once_with(store.snapshot())


def test_controller_restores_window_and_warns_on_failure(
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
    controller = LaunchController(window, store, thread_pool=SyncThreadPool())

    controller.launch(ENTRY)

    window.hide_launcher.assert_called_once_with()
    window.show_and_focus.assert_called_once_with()
    warning.assert_called_once()
    assert store.weight_for(ENTRY.path) == 0
    window.set_search_config.assert_not_called()


def test_controller_ignores_duplicate_launch_while_active(
    tmp_path: Path,
    monkeypatch,
    qapp,
) -> None:
    class PendingThreadPool:
        def __init__(self) -> None:
            self.tasks = []

        def start(self, task) -> None:
            self.tasks.append(task)

    startfile = Mock()
    monkeypatch.setattr(os, "startfile", startfile, raising=False)
    store = make_store(tmp_path)
    window = Mock()
    pool = PendingThreadPool()
    controller = LaunchController(window, store, thread_pool=pool)

    controller.launch(ENTRY)
    controller.launch(ENTRY)

    assert len(pool.tasks) == 1
    window.hide_launcher.assert_called_once_with()

    pool.tasks[0].run()
    qapp.processEvents()
    controller.launch(ENTRY)

    assert len(pool.tasks) == 2

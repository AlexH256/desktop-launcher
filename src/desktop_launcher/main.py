import os
import sys
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from desktop_launcher.core.app_icon import load_app_icon
from desktop_launcher.core.autostart import sync_autostart
from desktop_launcher.core.config import load_config
from desktop_launcher.core.hotkey import GlobalHotkey
from desktop_launcher.core.search import AppEntry, LinkIndex
from desktop_launcher.core.search_config import SearchConfigStore
from desktop_launcher.core.style import load_stylesheet
from desktop_launcher.core.visibility import VisibilityDialog
from desktop_launcher.core.window import LauncherWindow


class _LaunchSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(object, str)


class _LaunchTask(QRunnable):
    def __init__(self, entry: AppEntry, signals: _LaunchSignals) -> None:
        super().__init__()
        self._entry = entry
        self._signals = signals

    def run(self) -> None:
        try:
            os.startfile(str(self._entry.path))
        except OSError as exc:
            self._signals.failed.emit(self._entry, str(exc))
        else:
            self._signals.succeeded.emit(self._entry)


class LaunchController(QObject):
    def __init__(
        self,
        window: LauncherWindow,
        store: SearchConfigStore,
        parent: QObject | None = None,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__(parent)
        self._window = window
        self._store = store
        self._thread_pool = thread_pool or QThreadPool(self)
        self._active = False
        self._signals = _LaunchSignals(self)
        self._signals.succeeded.connect(self._on_succeeded)
        self._signals.failed.connect(self._on_failed)

    def launch(self, entry: AppEntry) -> None:
        if self._active:
            return
        self._active = True
        self._window.hide_launcher()
        self._thread_pool.start(_LaunchTask(entry, self._signals))

    def _on_succeeded(self, entry: AppEntry) -> None:
        self._active = False
        QTimer.singleShot(0, lambda: self._record_success(entry))

    def _on_failed(self, entry: AppEntry, message: str) -> None:
        self._active = False
        self._window.show_and_focus()
        QMessageBox.warning(
            self._window,
            "启动失败",
            f"无法启动 {entry.name}\n{entry.path}\n\n{message}",
        )

    def _record_success(self, entry: AppEntry) -> None:
        if not self._store.record_launch(entry.path):
            detail = self._store.warnings[-1] if self._store.warnings else "未知错误"
            print(detail, file=sys.stderr)
        self._window.set_search_config(self._store.snapshot())


def _create_tray_icon(
    window: LauncherWindow,
    app: QApplication,
    icon: QIcon,
    show_launcher: Callable[[], None],
    show_visibility: Callable[[], None],
) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Desktop Launcher")

    menu = QMenu(window)
    show_action = QAction("显示", menu)
    show_action.triggered.connect(lambda: show_launcher())
    visibility_action = QAction("可见性配置", menu)
    visibility_action.triggered.connect(lambda: show_visibility())
    quit_action = QAction("退出", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addAction(visibility_action)
    menu.addSeparator()
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: show_launcher()
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick
        else None
    )
    tray.show()
    return tray


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Desktop Launcher")
    app.setQuitOnLastWindowClosed(False)

    result = load_config()
    config = result.config
    autostart_warning = sync_autostart(config.autostart)
    style = load_stylesheet()
    app_icon = load_app_icon()

    store = SearchConfigStore()
    store.load()

    window = LauncherWindow(style.stylesheet)
    window.set_search_config(store.snapshot())
    launch_controller = LaunchController(window, store, parent=app)
    index = LinkIndex(
        config.search.paths,
        config.search.max_depth,
        parent=app,
    )
    hotkey = GlobalHotkey(config.hotkey.modifiers, config.hotkey.key)

    def show_launcher() -> None:
        window.show_and_focus()
        index.refresh()

    visibility_dialog: VisibilityDialog | None = None

    def show_visibility() -> None:
        nonlocal visibility_dialog
        if visibility_dialog is not None:
            visibility_dialog.show()
            visibility_dialog.raise_()
            visibility_dialog.activateWindow()
            return

        dialog = VisibilityDialog(
            index.entries,
            store,
            window_icon=app_icon,
        )
        dialog.changed.connect(
            lambda: window.set_search_config(store.snapshot())
        )

        def clear_dialog(*_args) -> None:
            nonlocal visibility_dialog
            visibility_dialog = None

        dialog.finished.connect(clear_dialog)
        visibility_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    hotkey.activated.connect(show_launcher)
    window.entryActivated.connect(launch_controller.launch)

    registered = hotkey.register()

    notices = list(result.warnings) + list(style.warnings) + list(store.warnings)
    if autostart_warning:
        notices.append(autostart_warning)
    if not registered:
        notices.append(
            f"全局快捷键 {config.hotkey.text} 注册失败，可能已被其他程序占用"
        )
    for notice in notices:
        print(notice, file=sys.stderr)

    tray = _create_tray_icon(
        window,
        app,
        app_icon,
        show_launcher,
        show_visibility,
    )

    def on_scan_started() -> None:
        window.set_scanning(True)

    def on_scan_updated(entries) -> None:
        warning_count = len(store.warnings)
        changed = store.sync_entries(
            (entry.path for entry in entries),
            config.search.paths,
        )
        if changed:
            window.set_search_config(store.snapshot())
        window.set_entries(entries)
        for warning in store.warnings[warning_count:]:
            print(warning, file=sys.stderr)

    def on_scan_failed(message: str) -> None:
        print(f"扫描快捷方式失败：{message}", file=sys.stderr)
        window.set_error(message)
        tray.showMessage(
            "Desktop Launcher",
            f"扫描快捷方式失败：{message}",
            QSystemTrayIcon.MessageIcon.Warning,
        )

    index.started.connect(on_scan_started)
    index.updated.connect(on_scan_updated)
    index.failed.connect(on_scan_failed)
    index.refresh(force=True)

    if notices:
        tray.showMessage(
            "Desktop Launcher",
            "\n".join(notices),
            QSystemTrayIcon.MessageIcon.Warning,
        )

    app.aboutToQuit.connect(hotkey.unregister)
    return app.exec()

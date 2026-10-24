import os
import sys
from collections.abc import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QStyle,
    QSystemTrayIcon,
)

from desktop_launcher.core.config import load_config
from desktop_launcher.core.hotkey import GlobalHotkey
from desktop_launcher.core.search import AppEntry, LinkIndex
from desktop_launcher.core.search_config import SearchConfigStore
from desktop_launcher.core.style import load_stylesheet
from desktop_launcher.core.visibility import VisibilityDialog
from desktop_launcher.core.window import LauncherWindow


def _launch_entry(window: LauncherWindow, entry: AppEntry) -> bool:
    try:
        os.startfile(str(entry.path))
    except OSError as exc:
        QMessageBox.warning(
            window,
            "启动失败",
            f"无法启动 {entry.name}\n{entry.path}\n\n{exc}",
        )
        return False
    window.hide_launcher()
    return True


def _activate_entry(
    window: LauncherWindow,
    entry: AppEntry,
    store: SearchConfigStore,
) -> None:
    if not _launch_entry(window, entry):
        return
    if not store.record_launch(entry.path):
        detail = store.warnings[-1] if store.warnings else "未知错误"
        print(detail, file=sys.stderr)
    window.set_search_config(store.snapshot())


def _create_tray_icon(
    window: LauncherWindow,
    app: QApplication,
    show_launcher: Callable[[], None],
    show_visibility: Callable[[], None],
) -> QSystemTrayIcon:
    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
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
    style = load_stylesheet()

    store = SearchConfigStore()
    store.load()

    window = LauncherWindow(style.stylesheet)
    window.set_search_config(store.snapshot())
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

        dialog = VisibilityDialog(index.entries, store)
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
    window.entryActivated.connect(
        lambda entry: _activate_entry(window, entry, store)
    )

    registered = hotkey.register()

    notices = list(result.warnings) + list(style.warnings) + list(store.warnings)
    if not registered:
        notices.append(
            f"全局快捷键 {config.hotkey.text} 注册失败，可能已被其他程序占用"
        )
    for notice in notices:
        print(notice, file=sys.stderr)

    tray = _create_tray_icon(window, app, show_launcher, show_visibility)

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

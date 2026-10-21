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
from desktop_launcher.core.weights import WeightStore
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
    weights: WeightStore,
) -> None:
    if not _launch_entry(window, entry):
        return
    if not weights.record_launch(entry.path):
        detail = weights.warnings[-1] if weights.warnings else "未知错误"
        print(detail, file=sys.stderr)
    window.set_weights(weights.snapshot())


def _create_tray_icon(
    window: LauncherWindow,
    app: QApplication,
    show_launcher: Callable[[], None],
) -> QSystemTrayIcon:
    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Desktop Launcher")

    menu = QMenu(window)
    show_action = QAction("显示", menu)
    show_action.triggered.connect(lambda: show_launcher())
    quit_action = QAction("退出", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
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

    weights = WeightStore()
    weights.load()

    window = LauncherWindow()
    window.set_weights(weights.snapshot())
    index = LinkIndex(
        config.search.paths,
        config.search.max_depth,
        parent=app,
    )
    hotkey = GlobalHotkey(config.hotkey.modifiers, config.hotkey.key)

    def show_launcher() -> None:
        window.show_and_focus()
        index.refresh()

    hotkey.activated.connect(show_launcher)
    window.entryActivated.connect(
        lambda entry: _activate_entry(window, entry, weights)
    )

    registered = hotkey.register()

    notices = list(result.warnings) + list(weights.warnings)
    if not registered:
        notices.append(
            f"全局快捷键 {config.hotkey.text} 注册失败，可能已被其他程序占用"
        )
    for notice in notices:
        print(notice, file=sys.stderr)

    tray = _create_tray_icon(window, app, show_launcher)

    def on_scan_started() -> None:
        window.set_scanning(True)

    def on_scan_updated(entries) -> None:
        window.set_entries(entries)
        warning_count = len(weights.warnings)
        if weights.cleanup_missing(
            (entry.path for entry in entries),
            config.search.paths,
        ):
            window.set_weights(weights.snapshot())
        for warning in weights.warnings[warning_count:]:
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

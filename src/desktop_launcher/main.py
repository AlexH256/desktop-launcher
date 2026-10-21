import sys

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from desktop_launcher.core.config import load_config
from desktop_launcher.core.hotkey import GlobalHotkey
from desktop_launcher.core.window import LauncherWindow


def _create_tray_icon(window: LauncherWindow, app: QApplication) -> QSystemTrayIcon:
    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Desktop Launcher")

    menu = QMenu(window)
    show_action = QAction("显示", menu)
    show_action.triggered.connect(window.show_and_focus)
    quit_action = QAction("退出", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.show_and_focus()
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

    window = LauncherWindow(config.search.paths, config.search.max_depth)
    hotkey = GlobalHotkey(config.hotkey.modifiers, config.hotkey.key)
    hotkey.activated.connect(window.show_and_focus)

    registered = hotkey.register()

    notices = list(result.warnings)
    if not registered:
        notices.append(
            f"全局快捷键 {config.hotkey.text} 注册失败，可能已被其他程序占用"
        )
    for notice in notices:
        print(notice, file=sys.stderr)

    tray = _create_tray_icon(window, app)
    if notices:
        tray.showMessage(
            "Desktop Launcher",
            "\n".join(notices),
            QSystemTrayIcon.MessageIcon.Warning,
        )

    app.aboutToQuit.connect(hotkey.unregister)
    return app.exec()

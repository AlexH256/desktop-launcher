import ctypes
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import QFrame, QLineEdit, QVBoxLayout, QWidget


class LauncherWindow(QWidget):
    queryChanged = Signal(str)
    querySubmitted = Signal(str)

    def __init__(
        self,
        search_paths: Sequence[Path] = (),
        max_depth: int = 5,
    ) -> None:
        super().__init__()
        self.search_paths = tuple(search_paths)
        self.search_max_depth = max_depth
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Desktop Launcher")
        self.setFixedSize(720, 76)

        card = QFrame(self)
        card.setObjectName("card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(20, 12, 20, 12)

        self.search_input = QLineEdit(card)
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("搜索应用…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.queryChanged)
        self.search_input.returnPressed.connect(self._submit)
        inner.addWidget(self.search_input)

        palette = self.search_input.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(255, 255, 255, 110))
        self.search_input.setPalette(palette)

        self.setStyleSheet(
            """
            #card {
                background-color: rgba(32, 32, 36, 235);
                border: 1px solid rgba(255, 255, 255, 40);
                border-radius: 16px;
            }
            #searchInput {
                background: transparent;
                border: none;
                color: #f2f2f2;
                font-size: 18px;
                padding: 6px 4px;
                selection-background-color: #3d7eff;
            }
            #searchInput QToolButton {
                background: transparent;
                border: none;
            }
            """
        )

        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._escape_shortcut.activated.connect(self.hide_launcher)

    def _submit(self) -> None:
        self.querySubmitted.emit(self.search_input.text())

    def _center_on_cursor_screen(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            area.x() + (area.width() - self.width()) // 2,
            area.y() + (area.height() - self.height()) // 2,
        )

    def _force_foreground(self) -> None:
        try:
            user32 = ctypes.windll.user32
            user32.GetForegroundWindow.restype = ctypes.c_void_p
            user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
            user32.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_bool]
            user32.AttachThreadInput.restype = ctypes.c_bool
            user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
            user32.SetForegroundWindow.restype = ctypes.c_bool
            user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
            user32.BringWindowToTop.restype = ctypes.c_bool

            hwnd = ctypes.c_void_p(int(self.winId()))
            foreground = user32.GetForegroundWindow()
            if foreground == hwnd.value:
                return

            kernel32 = ctypes.windll.kernel32
            kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
            current_thread = kernel32.GetCurrentThreadId()
            foreground_thread = (
                user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
            )

            attached = False
            if foreground_thread and foreground_thread != current_thread:
                attached = user32.AttachThreadInput(current_thread, foreground_thread, True)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            if attached:
                user32.AttachThreadInput(current_thread, foreground_thread, False)
        except Exception:
            pass

    def show_and_focus(self) -> None:
        self._center_on_cursor_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        handle = self.windowHandle()
        if handle is not None:
            handle.requestActivate()
        self._force_foreground()
        self._focus_input()
        QTimer.singleShot(0, self._focus_input)

    def _focus_input(self) -> None:
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_input.selectAll()

    def hide_launcher(self) -> None:
        self.search_input.clear()
        self.hide()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide_launcher()

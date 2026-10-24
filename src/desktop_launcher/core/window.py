import ctypes
from collections.abc import Mapping, Sequence

from PySide6.QtCore import QEvent, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QKeySequence,
    QPalette,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from desktop_launcher.core.icons import LinkIconProvider
from desktop_launcher.core.search import AppEntry, filter_entries
from desktop_launcher.core.style import DEFAULT_STYLESHEET

WINDOW_WIDTH = 720
SEARCH_HEIGHT = 44
ROW_HEIGHT = 38
MAX_VISIBLE_ROWS = 8
STATUS_HEIGHT = 26
ICON_SIZE = 20


class _LauncherItemDelegate(QStyledItemDelegate):
    def __init__(
        self,
        icon_provider: LinkIconProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_provider = icon_provider

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        super().initStyleOption(option, index)
        entry = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, AppEntry):
            option.icon = self._icon_provider.icon_for(entry.path)
            option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
            option.decorationSize = QSize(ICON_SIZE, ICON_SIZE)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        return QSize(0, ROW_HEIGHT)



class LauncherWindow(QWidget):
    entryActivated = Signal(object)

    def __init__(self, stylesheet: str = DEFAULT_STYLESHEET) -> None:
        super().__init__()
        self._entries: tuple[AppEntry, ...] = ()
        self._weights: dict[str, int] = {}
        self._scanning = False
        self._error = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle("Desktop Launcher")
        self.setFixedWidth(WINDOW_WIDTH)

        self._card = QFrame(self)
        self._card.setObjectName("card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._card)

        inner = QVBoxLayout(self._card)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(4)
        self._inner_layout = inner

        self.search_input = QLineEdit(self._card)
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("搜索应用…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(SEARCH_HEIGHT)
        self.search_input.textChanged.connect(self._apply_filter)
        self.search_input.returnPressed.connect(self._activate_current)
        self.search_input.installEventFilter(self)
        inner.addWidget(self.search_input)

        palette = self.search_input.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(255, 255, 255, 110))
        self.search_input.setPalette(palette)

        self._status_label = QLabel(self._card)
        self._status_label.setObjectName("statusLabel")
        self._status_label.setFixedHeight(STATUS_HEIGHT)
        self._status_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._status_label.hide()
        inner.addWidget(self._status_label)

        self._result_list = QListWidget(self._card)
        self._result_list.setObjectName("resultList")
        self._result_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._result_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._result_list.setUniformItemSizes(True)
        self._result_list.setMouseTracking(True)
        self._result_list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._icon_provider = LinkIconProvider()
        self._item_delegate = _LauncherItemDelegate(
            self._icon_provider,
            self._result_list,
        )
        self._result_list.setItemDelegate(self._item_delegate)
        self._result_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._result_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._result_list.itemClicked.connect(self._on_item_clicked)
        self._result_list.hide()
        inner.addWidget(self._result_list)

        if stylesheet:
            self.setStyleSheet(stylesheet)

        self._escape_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._escape_shortcut.activated.connect(self.hide_launcher)

        self._apply_filter()

    def set_entries(self, entries: Sequence[AppEntry]) -> None:
        self._entries = tuple(entries)
        self._scanning = False
        self._error = ""
        self._apply_filter()

    def set_weights(self, weights: Mapping[str, int]) -> None:
        self._weights = dict(weights)
        self._apply_filter()

    def set_scanning(self, scanning: bool) -> None:
        self._scanning = scanning
        if scanning:
            self._error = ""
            if not self._entries:
                self._apply_filter()
            return
        self._apply_filter()

    def set_error(self, message: str) -> None:
        self._scanning = False
        self._error = message
        self._apply_filter()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.search_input and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down:
                self._move_selection(1)
                return True
            if event.key() == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
        return super().eventFilter(watched, event)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.WindowDeactivate:
            QTimer.singleShot(0, self._hide_on_focus_loss)
        return super().event(event)

    def _has_active_modal(self) -> bool:
        if QApplication.instance() is None:
            return False
        return QApplication.activeModalWidget() is not None

    def _hide_on_focus_loss(self) -> None:
        if not self.isVisible():
            return
        if self._has_active_modal():
            return
        if self.isActiveWindow():
            return
        self.hide_launcher()

    def _move_selection(self, delta: int) -> None:
        count = self._result_list.count()
        if count == 0:
            return

        current = self._result_list.currentRow()
        if current < 0:
            target = 0 if delta > 0 else count - 1
        else:
            target = max(0, min(current + delta, count - 1))
        self._result_list.setCurrentRow(target)
        item = self._result_list.item(target)
        if item is not None:
            self._result_list.scrollToItem(item)

    def _activate_current(self) -> None:
        item = self._result_list.currentItem()
        if item is not None:
            self._emit_entry(item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._emit_entry(item)

    def _emit_entry(self, item: QListWidgetItem) -> None:
        entry = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(entry, AppEntry):
            self.entryActivated.emit(entry)

    def _apply_filter(self) -> None:
        filtered = filter_entries(
            self._entries,
            self.search_input.text(),
            self._weights,
        )
        self._result_list.clear()

        for entry in filtered:
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(str(entry.path))
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self._result_list.addItem(item)

        if filtered:
            self._result_list.setCurrentRow(0)
            self._result_list.setFixedHeight(
                min(len(filtered), MAX_VISIBLE_ROWS) * ROW_HEIGHT
            )
            self._status_label.hide()
            self._result_list.show()
        else:
            self._result_list.setFixedHeight(0)
            self._result_list.hide()
            self._status_label.setText(self._empty_message())
            self._status_label.show()

        self._resize_to_results()

    def _empty_message(self) -> str:
        if self._error:
            return "扫描快捷方式失败"
        if self._scanning:
            return "正在扫描快捷方式…"
        if self.search_input.text().strip():
            return "无匹配结果"
        return "未找到 .lnk 快捷方式，请检查搜索路径"

    def _resize_to_results(self) -> None:
        rows = self._result_list.count()
        content_height = self.search_input.height()
        if rows:
            content_height += (
                self._inner_layout.spacing() + min(rows, MAX_VISIBLE_ROWS) * ROW_HEIGHT
            )
        else:
            content_height += self._inner_layout.spacing() + STATUS_HEIGHT

        margins = self._inner_layout.contentsMargins()
        target_height = (
            margins.top()
            + margins.bottom()
            + content_height
            + self._card.frameWidth() * 2
        )
        if self.height() != target_height:
            self.setFixedHeight(target_height)

    def _position_on_cursor_screen(self) -> None:
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
        if not self.isVisible():
            self._apply_filter()
            self._position_on_cursor_screen()
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
        self.hide()
        self.search_input.clear()

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide_launcher()

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from desktop_launcher.core.icons import LinkIconProvider
from desktop_launcher.core.item_delegate import AppEntryItemDelegate
from desktop_launcher.core.search import AppEntry, filter_entries, subsequence_match
from desktop_launcher.core.search_config import (
    SearchConfigStore,
    SearchRecord,
    weight_key,
)

ROW_HEIGHT = 36
ICON_SIZE = 20


class VisibilityDialog(QDialog):
    changed = Signal()

    def __init__(
        self,
        entries: Sequence[AppEntry],
        store: SearchConfigStore,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._updating = False

        self.setWindowTitle("可见性配置 - Desktop Launcher")
        self.resize(680, 600)
        self.setMinimumSize(520, 400)
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        self._filter_input = QLineEdit(self)
        self._filter_input.setPlaceholderText("筛选应用…")
        self._filter_input.setClearButtonEnabled(True)
        self._filter_input.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._filter_input, 1)

        self._summary_label = QLabel(self)
        filter_row.addWidget(self._summary_label)
        layout.addLayout(filter_row)

        hint = QLabel(
            "勾选表示在启动器列表中显示；批量操作作用于当前筛选结果。",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._list = QListWidget(self)
        self._list.setUniformItemSizes(True)
        self._list.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self._icon_provider = LinkIconProvider()
        self._item_delegate = AppEntryItemDelegate(
            self._icon_provider,
            ROW_HEIGHT,
            ICON_SIZE,
            self._list,
        )
        self._list.setItemDelegate(self._item_delegate)
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        self._show_all_button = QPushButton("全部显示", self)
        self._show_all_button.setToolTip("作用于当前筛选结果")
        self._show_all_button.clicked.connect(
            lambda: self._set_filtered_visible(True)
        )
        self._hide_all_button = QPushButton("全部隐藏", self)
        self._hide_all_button.setToolTip("作用于当前筛选结果")
        self._hide_all_button.clicked.connect(
            lambda: self._set_filtered_visible(False)
        )
        close_button = QPushButton("关闭", self)
        close_button.clicked.connect(self.close)

        button_row.addWidget(self._show_all_button)
        button_row.addWidget(self._hide_all_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._populate(entries, store.snapshot())

    def _populate(
        self,
        entries: Sequence[AppEntry],
        records: Mapping[str, SearchRecord],
    ) -> None:
        self._updating = True
        self._list.clear()

        for entry in filter_entries(entries, ""):
            record = records.get(weight_key(entry.path), SearchRecord())
            item = QListWidgetItem(entry.name)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(str(entry.path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if record.visible
                else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)

        self._updating = False
        self._apply_filter(self._filter_input.text())

    def _apply_filter(self, query: str) -> None:
        has_query = bool(query.strip())
        for index in range(self._list.count()):
            item = self._list.item(index)
            entry = item.data(Qt.ItemDataRole.UserRole)
            hidden = (
                has_query
                and isinstance(entry, AppEntry)
                and not subsequence_match(query, entry.name)
            )
            item.setHidden(hidden)
        self._update_summary()

    def _update_summary(self) -> None:
        total = self._list.count()
        visible = 0
        filtered = 0
        for index in range(total):
            item = self._list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                visible += 1
            if not item.isHidden():
                filtered += 1

        if total == 0:
            self._summary_label.setText("暂无快捷方式")
        elif self._filter_input.text().strip():
            self._summary_label.setText(
                f"可见 {visible} / 共 {total} · 筛选 {filtered} 项"
            )
        else:
            self._summary_label.setText(f"可见 {visible} / 共 {total}")

        has_filtered = filtered > 0
        self._show_all_button.setEnabled(has_filtered)
        self._hide_all_button.setEnabled(has_filtered)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating:
            return

        entry = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, AppEntry):
            return

        visible = item.checkState() == Qt.CheckState.Checked
        if self._store.set_visible(entry.path, visible):
            self._update_summary()
            self.changed.emit()
            return

        self._set_item_checked(item, not visible)
        self._show_save_error()

    def _set_filtered_visible(self, visible: bool) -> None:
        state = Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        items: list[QListWidgetItem] = []
        changes: dict[str, bool] = {}

        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.isHidden() or item.checkState() == state:
                continue
            entry = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(entry, AppEntry):
                continue
            items.append(item)
            changes[weight_key(entry.path)] = visible

        if not changes:
            return

        if not self._store.set_visibility(changes):
            self._show_save_error()
            return

        self._updating = True
        for item in items:
            item.setCheckState(state)
        self._updating = False

        self._update_summary()
        self.changed.emit()

    def _set_item_checked(self, item: QListWidgetItem, visible: bool) -> None:
        self._updating = True
        item.setCheckState(
            Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        )
        self._updating = False

    def _show_save_error(self) -> None:
        detail = self._store.warnings[-1] if self._store.warnings else "未知错误"
        QMessageBox.warning(self, "保存失败", detail)

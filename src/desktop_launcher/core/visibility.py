from collections.abc import Mapping, Sequence

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
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
ALIAS_COLUMN_WIDTH = 220
ALIAS_SAVE_DELAY_MS = 400


class VisibilityDialog(QDialog):
    changed = Signal()

    def __init__(
        self,
        entries: Sequence[AppEntry],
        store: SearchConfigStore,
        window_icon: QIcon | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._updating = False
        self._aliases: dict[str, str] = {}
        self._alias_edits: dict[str, QLineEdit] = {}
        self._pending_aliases: dict[str, str] = {}
        self._alias_timer = QTimer(self)
        self._alias_timer.setSingleShot(True)
        self._alias_timer.setInterval(ALIAS_SAVE_DELAY_MS)
        self._alias_timer.timeout.connect(self._flush_alias_changes)

        if window_icon is not None:
            self.setWindowIcon(window_icon)

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
            "勾选表示在启动器列表中显示；别名也会参与启动器搜索。"
            "批量操作作用于当前筛选结果。",
            self,
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["应用", "别名"])
        self._tree.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self._tree.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._tree.setUniformRowHeights(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setIndentation(0)
        self._tree.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, ALIAS_COLUMN_WIDTH)
        self._icon_provider = LinkIconProvider()
        self._item_delegate = AppEntryItemDelegate(
            self._icon_provider,
            ROW_HEIGHT,
            ICON_SIZE,
            self._tree,
        )
        self._tree.setItemDelegateForColumn(0, self._item_delegate)
        self._tree.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._tree, 1)

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
        self._alias_timer.stop()
        self._pending_aliases.clear()
        self._aliases.clear()
        self._alias_edits.clear()
        self._tree.clear()

        for entry in filter_entries(entries, ""):
            key = weight_key(entry.path)
            record = records.get(key, SearchRecord())
            item = QTreeWidgetItem([entry.name, ""])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            item.setToolTip(0, str(entry.path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked
                if record.visible
                else Qt.CheckState.Unchecked,
            )
            self._tree.addTopLevelItem(item)

            alias_edit = QLineEdit(self._tree)
            alias_edit.setPlaceholderText("别名")
            alias_edit.setClearButtonEnabled(True)
            alias_edit.setText(record.alias)
            alias_edit.textChanged.connect(
                lambda text, key=key: self._on_alias_changed(key, text)
            )
            alias_edit.editingFinished.connect(self._flush_alias_changes)
            self._tree.setItemWidget(item, 1, alias_edit)

            self._aliases[key] = record.alias
            self._alias_edits[key] = alias_edit

        self._updating = False
        self._apply_filter(self._filter_input.text())

    def _apply_filter(self, query: str) -> None:
        has_query = bool(query.strip())
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            hidden = False
            if has_query and isinstance(entry, AppEntry):
                alias = self._aliases.get(weight_key(entry.path), "")
                hidden = not (
                    subsequence_match(query, entry.name)
                    or (bool(alias) and subsequence_match(query, alias))
                )
            item.setHidden(hidden)
        self._update_summary()

    def _update_summary(self) -> None:
        total = self._tree.topLevelItemCount()
        visible = 0
        filtered = 0
        for index in range(total):
            item = self._tree.topLevelItem(index)
            if item.checkState(0) == Qt.CheckState.Checked:
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

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return

        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(entry, AppEntry):
            return

        visible = item.checkState(0) == Qt.CheckState.Checked
        if self._store.set_visible(entry.path, visible):
            self._update_summary()
            self.changed.emit()
            return

        self._set_item_checked(item, not visible)
        self._show_save_error()

    def _on_alias_changed(self, key: str, text: str) -> None:
        if self._updating:
            return

        alias = text.strip()
        if alias == self._aliases.get(key, ""):
            self._pending_aliases.pop(key, None)
        else:
            self._pending_aliases[key] = alias

        if self._pending_aliases:
            self._alias_timer.start()
        else:
            self._alias_timer.stop()

    def _flush_alias_changes(self) -> None:
        self._alias_timer.stop()
        if not self._pending_aliases:
            return

        changes = dict(self._pending_aliases)
        previous = {
            key: self._aliases.get(key, "") for key in self._pending_aliases
        }
        if self._store.set_aliases(changes):
            self._aliases.update(changes)
            self._pending_aliases.clear()
            self.changed.emit()
            return

        self._updating = True
        for key, alias in previous.items():
            alias_edit = self._alias_edits.get(key)
            if alias_edit is not None:
                alias_edit.setText(alias)
        self._updating = False
        self._pending_aliases.clear()
        self._show_save_error()

    def _set_filtered_visible(self, visible: bool) -> None:
        state = Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
        items: list[QTreeWidgetItem] = []
        changes: dict[str, bool] = {}

        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item.isHidden() or item.checkState(0) == state:
                continue
            entry = item.data(0, Qt.ItemDataRole.UserRole)
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
            item.setCheckState(0, state)
        self._updating = False

        self._update_summary()
        self.changed.emit()

    def _set_item_checked(self, item: QTreeWidgetItem, visible: bool) -> None:
        self._updating = True
        item.setCheckState(
            0,
            Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked,
        )
        self._updating = False

    def _show_save_error(self) -> None:
        detail = self._store.warnings[-1] if self._store.warnings else "未知错误"
        QMessageBox.warning(self, "保存失败", detail)

    def closeEvent(self, event) -> None:
        self._flush_alias_changes()
        super().closeEvent(event)

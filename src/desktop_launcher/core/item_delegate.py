from PySide6.QtCore import QModelIndex, QSize, Qt
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from desktop_launcher.core.icons import LinkIconProvider
from desktop_launcher.core.search import AppEntry


class AppEntryItemDelegate(QStyledItemDelegate):
    def __init__(
        self,
        icon_provider: LinkIconProvider,
        row_height: int,
        icon_size: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_provider = icon_provider
        self._row_height = row_height
        self._icon_size = icon_size

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
            option.decorationSize = QSize(self._icon_size, self._icon_size)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        return QSize(0, self._row_height)

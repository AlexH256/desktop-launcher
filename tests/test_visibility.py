from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QListWidgetItem, QStyleOptionViewItem

from desktop_launcher.core import visibility as visibility_module
from desktop_launcher.core.search import AppEntry
from desktop_launcher.core.search_config import SearchConfigStore, weight_key
from desktop_launcher.core.visibility import VisibilityDialog

ENTRIES = (
    AppEntry("Alpha", Path("alpha.lnk")),
    AppEntry("Beta", Path("beta.lnk")),
    AppEntry("Gamma", Path("gamma.lnk")),
)


@pytest.fixture
def store(tmp_path: Path) -> SearchConfigStore:
    store = SearchConfigStore(tmp_path / "search-config.json")
    store.load()
    return store


@pytest.fixture
def dialog(qapp, store: SearchConfigStore):
    store.set_visibility({weight_key(ENTRIES[1].path): False})
    dialog = VisibilityDialog(ENTRIES, store)
    dialog.show()
    QTest.qWait(20)
    yield dialog
    dialog.close()
    QTest.qWait(10)


def find_item(dialog: VisibilityDialog, name: str) -> QListWidgetItem:
    for index in range(dialog._list.count()):
        item = dialog._list.item(index)
        if item.text() == name:
            return item
    raise AssertionError(f"item not found: {name}")


def test_initial_check_states_and_summary(dialog: VisibilityDialog) -> None:
    assert find_item(dialog, "Alpha").checkState() == Qt.CheckState.Checked
    assert find_item(dialog, "Beta").checkState() == Qt.CheckState.Unchecked
    assert find_item(dialog, "Gamma").checkState() == Qt.CheckState.Checked
    assert dialog._summary_label.text() == "可见 2 / 共 3"


def test_toggle_updates_store_and_emits_changed(
    dialog: VisibilityDialog,
    store: SearchConfigStore,
) -> None:
    changes = []
    dialog.changed.connect(lambda: changes.append(True))

    item = find_item(dialog, "Beta")
    item.setCheckState(Qt.CheckState.Checked)
    QTest.qWait(10)

    assert store.is_visible(ENTRIES[1].path) is True
    assert changes


def test_toggle_failure_reverts_checkbox(
    dialog: VisibilityDialog,
    store: SearchConfigStore,
    monkeypatch,
) -> None:
    warning = Mock()
    monkeypatch.setattr(store, "set_visible", lambda path, visible: False)
    monkeypatch.setattr(visibility_module.QMessageBox, "warning", warning)

    item = find_item(dialog, "Beta")
    item.setCheckState(Qt.CheckState.Checked)
    QTest.qWait(10)

    assert item.checkState() == Qt.CheckState.Unchecked
    warning.assert_called_once()


def test_filter_hides_non_matching_items(dialog: VisibilityDialog) -> None:
    dialog._filter_input.setText("alp")
    QTest.qWait(10)

    assert not find_item(dialog, "Alpha").isHidden()
    assert find_item(dialog, "Beta").isHidden()
    assert find_item(dialog, "Gamma").isHidden()


def test_bulk_actions_only_affect_filtered_items(
    dialog: VisibilityDialog,
    store: SearchConfigStore,
) -> None:
    dialog._filter_input.setText("alp")
    QTest.qWait(10)

    dialog._hide_all_button.click()
    QTest.qWait(10)

    assert store.is_visible(ENTRIES[0].path) is False
    assert store.is_visible(ENTRIES[1].path) is False
    assert store.is_visible(ENTRIES[2].path) is True

    dialog._show_all_button.click()
    QTest.qWait(10)

    assert store.is_visible(ENTRIES[0].path) is True
    assert store.is_visible(ENTRIES[1].path) is False
    assert store.is_visible(ENTRIES[2].path) is True


def test_items_show_icons(dialog: VisibilityDialog) -> None:
    delegate = dialog._list.itemDelegate()
    index = dialog._list.model().index(0, 0)
    option = QStyleOptionViewItem()

    delegate.initStyleOption(option, index)

    assert not option.icon.isNull()
    assert option.features & QStyleOptionViewItem.ViewItemFeature.HasDecoration


def test_clicking_item_text_does_not_select(dialog: VisibilityDialog) -> None:
    item = find_item(dialog, "Alpha")
    rect = dialog._list.visualItemRect(item)

    QTest.mouseClick(
        dialog._list.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        rect.center(),
    )
    QTest.qWait(10)

    assert dialog._list.selectedItems() == []


def test_clicking_checkbox_still_toggles(
    dialog: VisibilityDialog,
    store: SearchConfigStore,
) -> None:
    item = find_item(dialog, "Gamma")
    rect = dialog._list.visualItemRect(item)

    QTest.mouseClick(
        dialog._list.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(rect.left() + 3, rect.center().y()),
    )
    QTest.qWait(10)

    assert item.checkState() == Qt.CheckState.Unchecked
    assert store.is_visible(ENTRIES[2].path) is False

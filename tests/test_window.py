from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from desktop_launcher.core.config import WindowConfig
from desktop_launcher.core.search import AppEntry
from desktop_launcher.core.search_config import SearchRecord, weight_key
from desktop_launcher.core.window import ICON_SIZE, LauncherWindow

ENTRIES = (
    AppEntry("Alpha", Path("alpha.lnk")),
    AppEntry("Beta", Path("beta.lnk")),
    AppEntry("Gamma", Path("gamma.lnk")),
)


@pytest.fixture
def window(qapp):
    window = LauncherWindow()
    window.set_entries(ENTRIES)
    window.show_and_focus()
    QTest.qWait(10)
    yield window
    window.close()
    window.deleteLater()
    QTest.qWait(10)


@pytest.fixture
def received(window):
    entries: list[AppEntry] = []
    window.entryActivated.connect(entries.append)
    return entries


def click_item(window: LauncherWindow, row: int, button: Qt.MouseButton) -> None:
    item = window._result_list.item(row)
    assert item is not None
    rect = window._result_list.visualItemRect(item)
    QTest.mouseClick(
        window._result_list.viewport(),
        button,
        Qt.KeyboardModifier.NoModifier,
        rect.center(),
    )
    QTest.qWait(10)


def test_left_click_activates_item(window, received) -> None:
    click_item(window, 1, Qt.MouseButton.LeftButton)

    assert received == [ENTRIES[1]]


def test_right_click_does_not_activate_item(window, received) -> None:
    click_item(window, 1, Qt.MouseButton.RightButton)

    assert received == []


def test_clicking_search_input_does_not_activate_item(window, received) -> None:
    QTest.mouseClick(
        window.search_input,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(10, 10),
    )
    QTest.qWait(10)

    assert received == []


def test_enter_activates_current_item(window, received) -> None:
    QTest.keyClick(window.search_input, Qt.Key.Key_Down)
    QTest.keyClick(window.search_input, Qt.Key.Key_Return)
    QTest.qWait(10)

    assert received == [ENTRIES[1]]


def test_enter_without_results_does_nothing(window, received) -> None:
    window.search_input.setText("zzz")
    QTest.qWait(10)
    QTest.keyClick(window.search_input, Qt.Key.Key_Return)
    QTest.qWait(10)

    assert received == []


def test_items_show_icons(window) -> None:
    delegate = window._result_list.itemDelegate()
    index = window._result_list.model().index(0, 0)
    option = QStyleOptionViewItem()

    delegate.initStyleOption(option, index)

    assert not option.icon.isNull()
    assert option.features & QStyleOptionViewItem.ViewItemFeature.HasDecoration
    assert option.decorationSize == QSize(ICON_SIZE, ICON_SIZE)


def test_result_list_hides_vertical_scrollbar(window) -> None:
    assert (
        window._result_list.verticalScrollBarPolicy()
        == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )


def test_set_search_config_reorders_items(window) -> None:
    window.set_search_config(
        {weight_key(ENTRIES[2].path): SearchRecord(weight=5)}
    )

    names = [
        window._result_list.item(index).text()
        for index in range(window._result_list.count())
    ]

    assert names == ["Gamma", "Alpha", "Beta"]


def test_equal_weights_sort_by_name(window) -> None:
    window.set_search_config(
        {
            weight_key(ENTRIES[0].path): SearchRecord(weight=2),
            weight_key(ENTRIES[1].path): SearchRecord(weight=2),
        }
    )

    names = [
        window._result_list.item(index).text()
        for index in range(window._result_list.count())
    ]

    assert names == ["Alpha", "Beta", "Gamma"]


def test_hidden_entries_are_not_listed(window) -> None:
    window.set_search_config(
        {weight_key(ENTRIES[1].path): SearchRecord(visible=False)}
    )

    names = [
        window._result_list.item(index).text()
        for index in range(window._result_list.count())
    ]

    assert names == ["Alpha", "Gamma"]


def test_hidden_entries_are_not_searchable(window) -> None:
    window.set_search_config(
        {weight_key(ENTRIES[1].path): SearchRecord(visible=False)}
    )
    window.search_input.setText("beta")
    QTest.qWait(10)

    assert window._result_list.count() == 0
    assert window._status_label.text() == "无匹配结果"


def test_all_hidden_entries_show_status(window) -> None:
    window.set_search_config(
        {
            weight_key(entry.path): SearchRecord(visible=False)
            for entry in ENTRIES
        }
    )

    assert window._result_list.count() == 0
    assert window._status_label.isVisible()
    assert window._status_label.text() == "没有可见的快捷方式"


def test_custom_stylesheet_is_applied(qapp) -> None:
    window = LauncherWindow(stylesheet="#card { color: red; }")

    assert window.styleSheet() == "#card { color: red; }"

    window.deleteLater()
    QTest.qWait(10)


def test_custom_window_config_is_applied(qapp) -> None:
    window = LauncherWindow(
        window_config=WindowConfig(
            width=640,
            search_height=50,
            row_height=42,
            placeholder="查找应用",
        )
    )
    window.set_entries(ENTRIES)
    window.show_and_focus()
    QTest.qWait(10)

    item = window._result_list.item(0)
    assert item is not None
    assert window.width() == 640
    assert window.search_input.placeholderText() == "查找应用"
    assert window.search_input.height() == 50
    assert item.sizeHint().height() == 42
    assert window._result_list.height() == len(ENTRIES) * 42

    window.close()
    window.deleteLater()
    QTest.qWait(10)


def test_window_deactivate_hides_window(window, monkeypatch) -> None:
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)

    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
    QTest.qWait(20)

    assert not window.isVisible()


def test_window_deactivate_keeps_window_when_modal_is_open(
    window,
    monkeypatch,
) -> None:
    monkeypatch.setattr(window, "isActiveWindow", lambda: False)
    monkeypatch.setattr(window, "_has_active_modal", lambda: True)

    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
    QTest.qWait(20)

    assert window.isVisible()


def test_window_deactivate_keeps_window_when_reactivated(
    window,
    monkeypatch,
) -> None:
    monkeypatch.setattr(window, "isActiveWindow", lambda: True)

    QApplication.sendEvent(window, QEvent(QEvent.Type.WindowDeactivate))
    QTest.qWait(20)

    assert window.isVisible()

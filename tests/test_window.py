from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from desktop_launcher.core.search import AppEntry
from desktop_launcher.core.window import LauncherWindow

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

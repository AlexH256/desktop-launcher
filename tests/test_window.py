import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from desktop_launcher.core.search import AppEntry
from desktop_launcher.core.window import LauncherWindow


class WindowActivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.window = LauncherWindow()
        self.entries = (
            AppEntry("Alpha", Path("alpha.lnk")),
            AppEntry("Beta", Path("beta.lnk")),
            AppEntry("Gamma", Path("gamma.lnk")),
        )
        self.received: list[AppEntry] = []
        self.window.entryActivated.connect(self.received.append)
        self.window.set_entries(self.entries)
        self.window.show_and_focus()
        QTest.qWait(10)

    def tearDown(self) -> None:
        self.window.close()
        self.window.deleteLater()
        QTest.qWait(10)

    def click_item(self, row: int, button: Qt.MouseButton) -> None:
        item = self.window._result_list.item(row)
        rect = self.window._result_list.visualItemRect(item)
        QTest.mouseClick(
            self.window._result_list.viewport(),
            button,
            Qt.KeyboardModifier.NoModifier,
            rect.center(),
        )
        QTest.qWait(10)

    def test_left_click_activates_item(self) -> None:
        self.click_item(1, Qt.MouseButton.LeftButton)

        self.assertEqual(self.received, [self.entries[1]])

    def test_right_click_does_not_activate_item(self) -> None:
        self.click_item(1, Qt.MouseButton.RightButton)

        self.assertEqual(self.received, [])

    def test_clicking_search_input_does_not_activate_item(self) -> None:
        QTest.mouseClick(
            self.window.search_input,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(10, 10),
        )
        QTest.qWait(10)

        self.assertEqual(self.received, [])

    def test_enter_activates_current_item(self) -> None:
        QTest.keyClick(self.window.search_input, Qt.Key.Key_Down)
        QTest.keyClick(self.window.search_input, Qt.Key.Key_Return)
        QTest.qWait(10)

        self.assertEqual(self.received, [self.entries[1]])

    def test_enter_without_results_does_nothing(self) -> None:
        self.window.search_input.setText("zzz")
        QTest.qWait(10)
        QTest.keyClick(self.window.search_input, Qt.Key.Key_Return)
        QTest.qWait(10)

        self.assertEqual(self.received, [])


if __name__ == "__main__":
    unittest.main()

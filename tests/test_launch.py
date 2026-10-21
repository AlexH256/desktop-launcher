import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop_launcher.core.search import AppEntry
from desktop_launcher.main import _launch_entry


class LaunchEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = Mock()
        self.entry = AppEntry("App", Path("C:/Tools/App.lnk"))

    @patch("desktop_launcher.main.os.startfile")
    def test_success_launches_and_hides_window(self, startfile: Mock) -> None:
        _launch_entry(self.window, self.entry)

        startfile.assert_called_once_with(str(self.entry.path))
        self.window.hide_launcher.assert_called_once_with()

    @patch("desktop_launcher.main.QMessageBox.warning")
    @patch("desktop_launcher.main.os.startfile", side_effect=OSError("boom"))
    def test_failure_shows_warning_and_keeps_window(
        self,
        startfile: Mock,
        warning: Mock,
    ) -> None:
        _launch_entry(self.window, self.entry)

        startfile.assert_called_once_with(str(self.entry.path))
        warning.assert_called_once()
        self.window.hide_launcher.assert_not_called()


if __name__ == "__main__":
    unittest.main()

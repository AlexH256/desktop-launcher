import os
import tempfile
import unittest
from pathlib import Path

from desktop_launcher.core.config import (
    DEFAULT_HOTKEY,
    DEFAULT_MAX_DEPTH,
    load_config,
)


class LoadConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.config_path = self.base / "config.toml"

    def write_config(self, text: str) -> None:
        self.config_path.write_text(text, encoding="utf-8")

    def test_creates_default_config(self) -> None:
        result = load_config(self.config_path)

        self.assertTrue(result.created)
        self.assertTrue(self.config_path.exists())
        self.assertEqual(result.config.hotkey.text, DEFAULT_HOTKEY)
        self.assertEqual(result.config.search.max_depth, DEFAULT_MAX_DEPTH)
        self.assertGreaterEqual(len(result.config.search.paths), 1)
        self.assertEqual(result.warnings, ())

    def test_loads_custom_values(self) -> None:
        self.write_config(
            'hotkey = "Ctrl+Shift+K"\n\n[search]\npaths = []\nmax_depth = 2\n'
        )

        result = load_config(self.config_path)

        self.assertFalse(result.created)
        self.assertEqual(result.config.hotkey.text, "Ctrl+Shift+K")
        self.assertEqual(result.config.search.paths, ())
        self.assertEqual(result.config.search.max_depth, 2)

    def test_expands_relative_and_environment_paths(self) -> None:
        apps_dir = self.base / "apps"
        apps_dir.mkdir()
        temp_dir = Path(os.environ["TEMP"]).resolve()
        self.write_config(
            'hotkey = "Alt+Space"\n'
            "[search]\n"
            'paths = ["apps", "%TEMP%", "apps"]\n'
            "max_depth = 3\n"
        )

        result = load_config(self.config_path)

        self.assertEqual(
            result.config.search.paths,
            (apps_dir.resolve(), temp_dir),
        )

    def test_warns_about_missing_path(self) -> None:
        missing = self.base / "missing"
        self.write_config(
            'hotkey = "Alt+Space"\n'
            "[search]\n"
            f'paths = ["{missing.as_posix()}"]\n'
        )

        result = load_config(self.config_path)

        self.assertEqual(result.config.search.paths, (missing.resolve(),))
        self.assertTrue(any("不存在" in warning for warning in result.warnings))

    def test_invalid_toml_falls_back_without_overwriting(self) -> None:
        original = "hotkey = ["
        self.write_config(original)

        result = load_config(self.config_path)

        self.assertEqual(result.config.hotkey.text, DEFAULT_HOTKEY)
        self.assertTrue(result.warnings)
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original)

    def test_invalid_hotkey_falls_back(self) -> None:
        self.write_config('hotkey = "Space"\n')

        result = load_config(self.config_path)

        self.assertEqual(result.config.hotkey.text, DEFAULT_HOTKEY)
        self.assertTrue(any("快捷键" in warning for warning in result.warnings))

    def test_invalid_search_values_fall_back(self) -> None:
        self.write_config(
            'hotkey = "Alt+Space"\n'
            "[search]\n"
            'paths = "not-a-list"\n'
            "max_depth = 0\n"
        )

        result = load_config(self.config_path)

        self.assertEqual(result.config.search.max_depth, DEFAULT_MAX_DEPTH)
        self.assertGreaterEqual(len(result.config.search.paths), 1)
        self.assertTrue(any("paths" in warning for warning in result.warnings))
        self.assertTrue(any("max_depth" in warning for warning in result.warnings))

    def test_unknown_keys_warn(self) -> None:
        self.write_config(
            'hotkey = "Alt+Space"\n'
            "unknown = 1\n"
            "[search]\n"
            "paths = []\n"
            "unknown_search = 2\n"
        )

        result = load_config(self.config_path)

        self.assertTrue(any("unknown" in warning for warning in result.warnings))
        self.assertTrue(
            any("unknown_search" in warning for warning in result.warnings)
        )

    def test_all_invalid_paths_fall_back(self) -> None:
        self.write_config(
            'hotkey = "Alt+Space"\n'
            "[search]\n"
            'paths = ["", 3]\n'
        )

        result = load_config(self.config_path)

        self.assertGreaterEqual(len(result.config.search.paths), 1)
        self.assertTrue(any("有效路径" in warning for warning in result.warnings))


if __name__ == "__main__":
    unittest.main()

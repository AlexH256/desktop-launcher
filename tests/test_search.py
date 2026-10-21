import tempfile
import unittest
from pathlib import Path

from desktop_launcher.core.search import (
    AppEntry,
    filter_entries,
    scan_links,
    subsequence_match,
)


class SubsequenceMatchTests(unittest.TestCase):
    def test_letters_in_order(self) -> None:
        self.assertTrue(subsequence_match("vsc", "Visual Studio Code"))

    def test_letter_order_matters(self) -> None:
        self.assertFalse(subsequence_match("csv", "Visual Studio Code"))

    def test_case_and_whitespace_are_ignored(self) -> None:
        self.assertTrue(subsequence_match("vs code", "VSCode"))
        self.assertTrue(subsequence_match("VSCODE", "Visual Studio Code"))

    def test_chinese_characters_in_order(self) -> None:
        self.assertTrue(subsequence_match("微信", "微信开发者工具"))
        self.assertTrue(subsequence_match("微工", "微信开发者工具"))

    def test_chinese_order_matters(self) -> None:
        self.assertFalse(subsequence_match("信微", "微信开发者工具"))

    def test_mixed_letters_and_chinese(self) -> None:
        self.assertTrue(subsequence_match("v微", "Visual 微信"))

    def test_no_match(self) -> None:
        self.assertFalse(subsequence_match("xyz", "Visual Studio Code"))


class FilterEntriesTests(unittest.TestCase):
    def test_empty_query_returns_all_sorted(self) -> None:
        entries = (
            AppEntry("Gamma", Path("g")),
            AppEntry("alpha", Path("a")),
            AppEntry("Beta", Path("b")),
        )

        result = filter_entries(entries, "")

        self.assertEqual([entry.name for entry in result], ["alpha", "Beta", "Gamma"])

    def test_relevance_order(self) -> None:
        entries = (
            AppEntry("Coconut Delight", Path("d")),
            AppEntry("My Code Helper", Path("c")),
            AppEntry("Code Editor", Path("b")),
            AppEntry("Code", Path("a")),
        )

        result = filter_entries(entries, "code")

        self.assertEqual(
            [entry.name for entry in result],
            ["Code", "Code Editor", "My Code Helper", "Coconut Delight"],
        )

    def test_chinese_relevance_order(self) -> None:
        entries = (
            AppEntry("企业微信", Path("c")),
            AppEntry("微信开发者工具", Path("b")),
            AppEntry("微信", Path("a")),
        )

        result = filter_entries(entries, "微信")

        self.assertEqual(
            [entry.name for entry in result],
            ["微信", "微信开发者工具", "企业微信"],
        )

    def test_non_matching_entries_are_excluded(self) -> None:
        entries = (
            AppEntry("Visual Studio Code", Path("a")),
            AppEntry("Calculator", Path("b")),
        )

        result = filter_entries(entries, "vsc")

        self.assertEqual([entry.name for entry in result], ["Visual Studio Code"])


class ScanLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def touch(self, relative: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        return path

    def test_scans_lnk_files_case_insensitively(self) -> None:
        self.touch("Alpha.lnk")
        self.touch("beta.LNK")
        self.touch("gamma.txt")

        entries = scan_links([self.root], max_depth=5)

        self.assertEqual({entry.name for entry in entries}, {"Alpha", "beta"})

    def test_respects_max_depth(self) -> None:
        self.touch("root.lnk")
        self.touch("one/level1.lnk")
        self.touch("one/two/level2.lnk")

        entries = scan_links([self.root], max_depth=2)

        self.assertEqual({entry.name for entry in entries}, {"root", "level1"})

    def test_deduplicates_names_across_paths(self) -> None:
        first = self.touch("first/tool.lnk")
        self.touch("second/tool.lnk")

        entries = scan_links(
            [self.root / "first", self.root / "second"],
            max_depth=5,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, first)

    def test_missing_directory_is_ignored(self) -> None:
        self.touch("valid/app.lnk")

        entries = scan_links(
            [self.root / "missing", self.root / "valid"],
            max_depth=5,
        )

        self.assertEqual([entry.name for entry in entries], ["app"])


if __name__ == "__main__":
    unittest.main()

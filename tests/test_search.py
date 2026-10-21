from pathlib import Path

import pytest

from desktop_launcher.core.search import (
    AppEntry,
    filter_entries,
    scan_links,
    subsequence_match,
)
from desktop_launcher.core.weights import weight_key


@pytest.mark.parametrize(
    ("query", "text"),
    [
        ("vsc", "Visual Studio Code"),
        ("vs code", "VSCode"),
        ("VSCODE", "Visual Studio Code"),
        ("微信", "微信开发者工具"),
        ("微工", "微信开发者工具"),
        ("v微", "Visual 微信"),
    ],
)
def test_subsequence_matches(query: str, text: str) -> None:
    assert subsequence_match(query, text)


@pytest.mark.parametrize(
    ("query", "text"),
    [
        ("csv", "Visual Studio Code"),
        ("信微", "微信开发者工具"),
        ("xyz", "Visual Studio Code"),
    ],
)
def test_subsequence_rejects_wrong_order_or_missing_characters(
    query: str,
    text: str,
) -> None:
    assert not subsequence_match(query, text)


def test_empty_query_returns_all_sorted() -> None:
    entries = (
        AppEntry("Gamma", Path("g")),
        AppEntry("alpha", Path("a")),
        AppEntry("Beta", Path("b")),
    )

    result = filter_entries(entries, "")

    assert [entry.name for entry in result] == ["alpha", "Beta", "Gamma"]


def test_relevance_order() -> None:
    entries = (
        AppEntry("Coconut Delight", Path("d")),
        AppEntry("My Code Helper", Path("c")),
        AppEntry("Code Editor", Path("b")),
        AppEntry("Code", Path("a")),
    )

    result = filter_entries(entries, "code")

    assert [entry.name for entry in result] == [
        "Code",
        "Code Editor",
        "My Code Helper",
        "Coconut Delight",
    ]


def test_chinese_relevance_order() -> None:
    entries = (
        AppEntry("企业微信", Path("c")),
        AppEntry("微信开发者工具", Path("b")),
        AppEntry("微信", Path("a")),
    )

    result = filter_entries(entries, "微信")

    assert [entry.name for entry in result] == [
        "微信",
        "微信开发者工具",
        "企业微信",
    ]


def test_non_matching_entries_are_excluded() -> None:
    entries = (
        AppEntry("Visual Studio Code", Path("a")),
        AppEntry("Calculator", Path("b")),
    )

    result = filter_entries(entries, "vsc")

    assert [entry.name for entry in result] == ["Visual Studio Code"]


def test_empty_query_sorts_by_weight_then_name() -> None:
    entries = (
        AppEntry("Alpha", Path("alpha")),
        AppEntry("Beta", Path("beta")),
        AppEntry("Gamma", Path("gamma")),
    )
    weights = {
        weight_key(Path("beta")): 5,
        weight_key(Path("gamma")): 5,
    }

    result = filter_entries(entries, "", weights)

    assert [entry.name for entry in result] == ["Beta", "Gamma", "Alpha"]


def test_query_sorts_by_relevance_then_weight_then_name() -> None:
    entries = (
        AppEntry("Code", Path("exact")),
        AppEntry("Code Editor", Path("prefix-a")),
        AppEntry("Code Lite", Path("prefix-b")),
        AppEntry("Coconut Delight", Path("subsequence")),
    )
    weights = {
        weight_key(Path("prefix-a")): 10,
        weight_key(Path("prefix-b")): 2,
        weight_key(Path("subsequence")): 100,
    }

    result = filter_entries(entries, "code", weights)

    assert [entry.name for entry in result] == [
        "Code",
        "Code Editor",
        "Code Lite",
        "Coconut Delight",
    ]


def test_query_same_relevance_and_weight_sorts_by_name() -> None:
    entries = (
        AppEntry("Code Beta", Path("beta")),
        AppEntry("Code Alpha", Path("alpha")),
    )

    result = filter_entries(entries, "code")

    assert [entry.name for entry in result] == ["Code Alpha", "Code Beta"]


def touch(root: Path, relative: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_scans_lnk_files_case_insensitively(tmp_path: Path) -> None:
    touch(tmp_path, "Alpha.lnk")
    touch(tmp_path, "beta.LNK")
    touch(tmp_path, "gamma.txt")

    entries = scan_links([tmp_path], max_depth=5)

    assert {entry.name for entry in entries} == {"Alpha", "beta"}


def test_respects_max_depth(tmp_path: Path) -> None:
    touch(tmp_path, "root.lnk")
    touch(tmp_path, "one/level1.lnk")
    touch(tmp_path, "one/two/level2.lnk")

    entries = scan_links([tmp_path], max_depth=2)

    assert {entry.name for entry in entries} == {"root", "level1"}


def test_deduplicates_names_across_paths(tmp_path: Path) -> None:
    first = touch(tmp_path, "first/tool.lnk")
    touch(tmp_path, "second/tool.lnk")

    entries = scan_links(
        [tmp_path / "first", tmp_path / "second"],
        max_depth=5,
    )

    assert len(entries) == 1
    assert entries[0].path == first


def test_missing_directory_is_ignored(tmp_path: Path) -> None:
    touch(tmp_path, "valid/app.lnk")

    entries = scan_links(
        [tmp_path / "missing", tmp_path / "valid"],
        max_depth=5,
    )

    assert [entry.name for entry in entries] == ["app"]

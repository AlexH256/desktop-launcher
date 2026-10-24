from pathlib import Path

import pytest
from PySide6.QtGui import QIcon

from desktop_launcher.core import icons
from desktop_launcher.core.icons import LinkIconProvider


@pytest.fixture
def provider(qapp) -> LinkIconProvider:
    return LinkIconProvider()


def test_icon_for_lnk(tmp_path: Path, provider: LinkIconProvider) -> None:
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")

    icon = provider.icon_for(path)

    assert not icon.isNull()


def test_icon_is_cached(tmp_path: Path, provider: LinkIconProvider) -> None:
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")

    first = provider.icon_for(path)
    second = provider.icon_for(path)

    assert first is second


def test_fallback_when_extraction_fails(
    tmp_path: Path,
    provider: LinkIconProvider,
    monkeypatch,
) -> None:
    monkeypatch.setattr(icons, "_extract_icon", lambda path: None)

    icon = provider.icon_for(tmp_path / "missing.lnk")

    assert not icon.isNull()


def test_fallback_when_extraction_raises(
    tmp_path: Path,
    provider: LinkIconProvider,
    monkeypatch,
) -> None:
    def fail(path: Path):
        raise OSError("boom")

    monkeypatch.setattr(icons, "_extract_icon", fail)

    icon = provider.icon_for(tmp_path / "broken.lnk")

    assert not icon.isNull()


def test_icon_location_has_priority(tmp_path: Path, monkeypatch) -> None:
    icon_file = tmp_path / "icon.dll"
    icon_file.write_bytes(b"")
    target = tmp_path / "app.exe"
    target.write_bytes(b"")
    expected = QIcon()
    monkeypatch.setattr(
        icons,
        "_resolve_shortcut",
        lambda path: (str(target), str(icon_file), 7),
    )
    monkeypatch.setattr(
        icons,
        "_extract_indexed_icon",
        lambda file, index: expected,
    )

    def unexpected(file: str) -> QIcon:
        raise AssertionError("target icon should not be used")

    monkeypatch.setattr(icons, "_shell_icon", unexpected)

    assert icons._extract_icon(tmp_path / "app.lnk") is expected


def test_target_icon_is_used_when_icon_location_is_empty(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "app.exe"
    target.write_bytes(b"")
    expected = QIcon()
    monkeypatch.setattr(
        icons,
        "_resolve_shortcut",
        lambda path: (str(target), "", 0),
    )
    monkeypatch.setattr(icons, "_shell_icon", lambda file: expected)

    assert icons._extract_icon(tmp_path / "app.lnk") is expected


def test_target_icon_is_used_when_icon_location_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    icon_file = tmp_path / "icon.dll"
    icon_file.write_bytes(b"")
    target = tmp_path / "app.exe"
    target.write_bytes(b"")
    expected = QIcon()
    monkeypatch.setattr(
        icons,
        "_resolve_shortcut",
        lambda path: (str(target), str(icon_file), 7),
    )
    monkeypatch.setattr(icons, "_extract_indexed_icon", lambda file, index: None)
    monkeypatch.setattr(icons, "_shell_icon", lambda file: expected)

    assert icons._extract_icon(tmp_path / "app.lnk") is expected


def test_lnk_candidates_are_skipped(tmp_path: Path, monkeypatch) -> None:
    icon_file = tmp_path / "icon.lnk"
    icon_file.write_bytes(b"")
    target = tmp_path / "target.lnk"
    target.write_bytes(b"")
    monkeypatch.setattr(
        icons,
        "_resolve_shortcut",
        lambda path: (str(target), str(icon_file), 0),
    )

    def unexpected(*args):
        raise AssertionError("lnk icons should not be extracted")

    monkeypatch.setattr(icons, "_extract_indexed_icon", unexpected)
    monkeypatch.setattr(icons, "_shell_icon", unexpected)

    assert icons._extract_icon(tmp_path / "app.lnk") is None


def test_resolution_failure_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(icons, "_resolve_shortcut", lambda path: None)

    assert icons._extract_icon(Path("app.lnk")) is None


def test_index_minus_one_uses_shell_icon(monkeypatch) -> None:
    expected = QIcon()
    monkeypatch.setattr(icons, "_shell_icon", lambda file: expected)

    assert icons._extract_indexed_icon("icon.dll", -1) is expected

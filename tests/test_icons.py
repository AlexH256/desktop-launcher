from pathlib import Path

import pytest

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

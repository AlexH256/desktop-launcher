import sys
from pathlib import Path

from PySide6.QtGui import QColor, QPixmap

from desktop_launcher.core.app_icon import (
    ICON_FILE_NAME,
    default_app_icon_path,
    load_app_icon,
)


def test_default_icon_path_uses_project_assets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))

    expected = Path(__file__).resolve().parents[1] / "assets" / ICON_FILE_NAME
    assert default_app_icon_path() == expected


def test_default_icon_path_prefers_assets_next_to_executable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    icon_path = tmp_path / "assets" / ICON_FILE_NAME
    icon_path.parent.mkdir()
    icon_path.write_bytes(b"icon")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "desktop_launcher.exe"))

    assert default_app_icon_path() == icon_path


def test_loads_project_asset_icon(qapp) -> None:
    icon = load_app_icon()

    assert not icon.isNull()


def test_missing_icon_falls_back(tmp_path: Path, qapp) -> None:
    icon = load_app_icon(tmp_path / "missing.ico")

    assert not icon.isNull()


def test_loads_custom_icon(tmp_path: Path, qapp) -> None:
    path = tmp_path / "icon.png"
    pixmap = QPixmap(32, 32)
    pixmap.fill(QColor("red"))
    assert pixmap.save(str(path), "PNG")

    icon = load_app_icon(path)

    assert not icon.isNull()


def test_invalid_icon_falls_back(tmp_path: Path, qapp) -> None:
    path = tmp_path / "icon.ico"
    path.write_bytes(b"not an icon")

    icon = load_app_icon(path)

    assert not icon.isNull()

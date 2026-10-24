from pathlib import Path

from PySide6.QtGui import QColor, QPixmap

from desktop_launcher.core.app_icon import (
    ICON_FILE_NAME,
    default_app_icon_path,
    load_app_icon,
)


def test_default_icon_path_uses_appdata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert default_app_icon_path() == tmp_path / "DesktopLauncher" / ICON_FILE_NAME


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

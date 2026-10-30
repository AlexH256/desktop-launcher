import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

ASSETS_DIR_NAME = "assets"
ICON_FILE_NAME = "icon.ico"


def _executable_icon_path() -> Path:
    executable = getattr(sys, "executable", "")
    if not executable:
        return Path.cwd() / ASSETS_DIR_NAME / ICON_FILE_NAME
    return Path(executable).resolve().parent / ASSETS_DIR_NAME / ICON_FILE_NAME


def _source_icon_path() -> Path:
    return Path(__file__).resolve().parents[3] / ASSETS_DIR_NAME / ICON_FILE_NAME


def default_app_icon_path() -> Path:
    candidates = (_executable_icon_path(), _source_icon_path())
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[-1]


def load_app_icon(path: Path | None = None) -> QIcon:
    icon_path = (path or default_app_icon_path()).expanduser()
    if icon_path.is_file():
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    return _fallback_icon()


def _fallback_icon() -> QIcon:
    if QApplication.instance() is None:
        return QIcon()
    return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

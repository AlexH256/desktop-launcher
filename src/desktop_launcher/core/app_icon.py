import os
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle

from desktop_launcher.core.config import APP_DIR_NAME

ICON_FILE_NAME = "icon.ico"


def default_app_icon_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME / ICON_FILE_NAME


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

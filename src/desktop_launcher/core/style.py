import os
from dataclasses import dataclass
from pathlib import Path

from desktop_launcher.core.config import APP_DIR_NAME

STYLE_FILE_NAME = "style.css"

DEFAULT_STYLESHEET = """/* Desktop Launcher 样式文件，修改后重启生效 */
#card {
    background-color: rgba(32, 32, 36, 240);
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 16px;
}
#searchInput {
    background: transparent;
    border: none;
    color: #f2f2f2;
    font-size: 18px;
    padding: 4px 2px;
    selection-background-color: #3d7eff;
}
#searchInput QToolButton {
    background: transparent;
    border: none;
}
#statusLabel {
    color: rgba(255, 255, 255, 150);
    font-size: 13px;
    padding-left: 4px;
}
#resultList {
    background: transparent;
    border: none;
    outline: none;
    color: #f2f2f2;
    font-size: 15px;
}
#resultList::item {
    border-radius: 8px;
    padding-left: 10px;
}
#resultList::item:hover {
    background-color: rgba(255, 255, 255, 20);
}
#resultList::item:selected {
    background-color: #3d7eff;
    color: #ffffff;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 50);
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}
"""


@dataclass(frozen=True, slots=True)
class StyleLoadResult:
    stylesheet: str
    path: Path
    warnings: tuple[str, ...]
    created: bool


def default_style_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME / STYLE_FILE_NAME


def load_stylesheet(path: Path | None = None) -> StyleLoadResult:
    style_path = (path or default_style_path()).expanduser()
    warnings: list[str] = []

    if not style_path.exists():
        created = _write_default_style(style_path, warnings)
        return StyleLoadResult(DEFAULT_STYLESHEET, style_path, tuple(warnings), created)

    try:
        stylesheet = style_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        warnings.append(f"读取样式文件失败，已使用默认样式：{exc}")
        return StyleLoadResult(DEFAULT_STYLESHEET, style_path, tuple(warnings), False)

    return StyleLoadResult(stylesheet, style_path, (), False)


def _write_default_style(path: Path, warnings: list[str]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_STYLESHEET, encoding="utf-8")
        return True
    except OSError as exc:
        warnings.append(f"无法创建默认样式文件 {path}：{exc}")
        return False

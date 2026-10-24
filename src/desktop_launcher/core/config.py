import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from desktop_launcher.core.hotkey import HotkeyBinding, HotkeyParseError, parse_hotkey

APP_DIR_NAME = "DesktopLauncher"
CONFIG_FILE_NAME = "config.toml"
DEFAULT_HOTKEY = "Alt+Space"
DEFAULT_AUTOSTART = True
DEFAULT_MAX_DEPTH = 5
DEFAULT_SEARCH_PATHS = (
    "%USERPROFILE%/Desktop",
    "%APPDATA%/Microsoft/Windows/Start Menu/Programs",
    "%ProgramData%/Microsoft/Windows/Start Menu/Programs",
)

DEFAULT_CONFIG_TEXT = """# 全局快捷键：修饰键 + 按键，例如 "Alt+Space"、"Ctrl+Alt+K"
hotkey = "Alt+Space"

# 开机自动启动：true 开启，false 关闭
autostart = true

[search]
# 支持 ~ 和 %USERPROFILE%、%APPDATA% 等环境变量
# 相对路径以配置文件所在目录为基准
paths = [
    "%USERPROFILE%/Desktop",
    "%APPDATA%/Microsoft/Windows/Start Menu/Programs",
    "%ProgramData%/Microsoft/Windows/Start Menu/Programs",
]
# 最大递归深度，1 表示仅扫描当前目录
max_depth = 5
"""


@dataclass(frozen=True, slots=True)
class SearchConfig:
    paths: tuple[Path, ...]
    max_depth: int


@dataclass(frozen=True, slots=True)
class AppConfig:
    hotkey: HotkeyBinding
    autostart: bool
    search: SearchConfig


@dataclass(frozen=True, slots=True)
class ConfigLoadResult:
    config: AppConfig
    path: Path
    warnings: tuple[str, ...]
    created: bool


def default_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME / CONFIG_FILE_NAME


def load_config(path: Path | None = None) -> ConfigLoadResult:
    config_path = (path or default_config_path()).expanduser()
    warnings: list[str] = []

    if not config_path.exists():
        created = _write_default_config(config_path, warnings)
        config = _default_config(config_path.parent)
        return ConfigLoadResult(config, config_path, tuple(warnings), created)

    try:
        with config_path.open("rb") as file:
            raw = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        warnings.append(f"读取配置失败，已使用默认配置：{exc}")
        config = _default_config(config_path.parent)
        return ConfigLoadResult(config, config_path, tuple(warnings), False)

    config = _parse_config(raw, config_path, warnings)
    return ConfigLoadResult(config, config_path, tuple(warnings), False)


def _default_config(base_dir: Path) -> AppConfig:
    binding = parse_hotkey(DEFAULT_HOTKEY)
    search = SearchConfig(
        paths=_normalize_paths(DEFAULT_SEARCH_PATHS, base_dir, [], warn_missing=False),
        max_depth=DEFAULT_MAX_DEPTH,
    )
    return AppConfig(hotkey=binding, autostart=DEFAULT_AUTOSTART, search=search)


def _write_default_config(path: Path, warnings: list[str]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
        return True
    except OSError as exc:
        warnings.append(f"无法创建默认配置文件 {path}：{exc}")
        return False


def _parse_config(raw: dict, config_path: Path, warnings: list[str]) -> AppConfig:
    base_dir = config_path.parent

    allowed_top = {"hotkey", "autostart", "search"}
    for key in raw:
        if key not in allowed_top:
            warnings.append(f"未知配置项：{key}")

    return AppConfig(
        hotkey=_parse_hotkey_value(raw.get("hotkey"), warnings),
        autostart=_parse_autostart_value(raw.get("autostart"), warnings),
        search=_parse_search_value(raw.get("search"), base_dir, warnings),
    )


def _parse_autostart_value(value: object, warnings: list[str]) -> bool:
    if value is None:
        return DEFAULT_AUTOSTART
    if not isinstance(value, bool):
        warnings.append(
            f"autostart 必须是布尔值，已使用默认值 {str(DEFAULT_AUTOSTART).lower()}"
        )
        return DEFAULT_AUTOSTART
    return value


def _parse_hotkey_value(value: object, warnings: list[str]) -> HotkeyBinding:
    if value is None:
        return parse_hotkey(DEFAULT_HOTKEY)
    if not isinstance(value, str):
        warnings.append(f"hotkey 必须是字符串，已使用默认值 {DEFAULT_HOTKEY}")
        return parse_hotkey(DEFAULT_HOTKEY)
    try:
        return parse_hotkey(value)
    except HotkeyParseError as exc:
        warnings.append(f"快捷键配置无效（{exc}），已使用默认值 {DEFAULT_HOTKEY}")
        return parse_hotkey(DEFAULT_HOTKEY)


def _parse_search_value(value: object, base_dir: Path, warnings: list[str]) -> SearchConfig:
    defaults = _default_config(base_dir)
    if value is None:
        return defaults.search
    if not isinstance(value, dict):
        warnings.append("[search] 必须是表，已使用默认搜索配置")
        return defaults.search

    allowed_search = {"paths", "max_depth"}
    for key in value:
        if key not in allowed_search:
            warnings.append(f"未知搜索配置项：search.{key}")

    paths = defaults.search.paths
    if "paths" in value:
        raw_paths = value["paths"]
        if not isinstance(raw_paths, list):
            warnings.append("search.paths 必须是字符串列表，已使用默认搜索路径")
        else:
            normalized = _normalize_paths(raw_paths, base_dir, warnings, warn_missing=True)
            if raw_paths and not normalized:
                warnings.append("search.paths 中没有有效路径，已使用默认搜索路径")
            else:
                paths = normalized

    max_depth = defaults.search.max_depth
    if "max_depth" in value:
        raw_depth = value["max_depth"]
        if isinstance(raw_depth, bool) or not isinstance(raw_depth, int):
            warnings.append("search.max_depth 必须是正整数，已使用默认值 5")
        elif raw_depth < 1:
            warnings.append("search.max_depth 必须大于 0，已使用默认值 5")
        else:
            max_depth = raw_depth

    return SearchConfig(paths=paths, max_depth=max_depth)


def _normalize_paths(
    values: object,
    base_dir: Path,
    warnings: list[str],
    warn_missing: bool,
) -> tuple[Path, ...]:
    if not isinstance(values, (list, tuple)):
        return ()

    result: list[Path] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str) or not item.strip():
            warnings.append("search.paths 包含无效路径项，已忽略")
            continue

        text = os.path.expandvars(item.strip())
        path = Path(os.path.expanduser(text))
        if not path.is_absolute():
            path = base_dir / path
        try:
            path = path.resolve(strict=False)
        except OSError:
            pass

        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        result.append(path)

        if warn_missing:
            if not path.exists():
                warnings.append(f"搜索路径不存在：{path}")
            elif not path.is_dir():
                warnings.append(f"搜索路径不是目录：{path}")

    return tuple(result)

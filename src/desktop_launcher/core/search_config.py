import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from desktop_launcher.core.config import APP_DIR_NAME

SEARCH_CONFIG_FILE_NAME = "search-config.json"
SEARCH_CONFIG_VERSION = 2


def default_search_config_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME / SEARCH_CONFIG_FILE_NAME


def weight_key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class SearchRecord:
    weight: int = 0
    visible: bool = True


class SearchConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = (path or default_search_config_path()).expanduser()
        self._entries: dict[str, SearchRecord] = {}
        self._warnings: list[str] = []

    @property
    def path(self) -> Path:
        return self._path

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def load(self) -> None:
        self._warnings.clear()
        self._entries = {}
        if not self._path.exists():
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._warnings.append(f"读取搜索配置文件失败，已使用空配置：{exc}")
            return

        if not isinstance(raw, dict):
            self._warnings.append("搜索配置文件格式无效，已使用空配置")
            return

        version = raw.get("version")
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != SEARCH_CONFIG_VERSION
        ):
            self._warnings.append(
                f"搜索配置文件版本不支持：{version}，已使用空配置"
            )
            return

        raw_entries = raw.get("entries")
        if not isinstance(raw_entries, dict):
            self._warnings.append("搜索配置文件缺少 entries 表，已使用空配置")
            return

        entries: dict[str, SearchRecord] = {}
        for raw_key, raw_value in raw_entries.items():
            if not isinstance(raw_key, str) or not raw_key:
                self._warnings.append("搜索配置文件包含无效路径，已忽略")
                continue
            if not isinstance(raw_value, dict):
                self._warnings.append(f"条目格式无效，已忽略：{raw_key}")
                continue

            raw_weight = raw_value.get("weight", 0)
            raw_visible = raw_value.get("visible", True)
            if (
                isinstance(raw_weight, bool)
                or not isinstance(raw_weight, int)
                or raw_weight < 0
            ):
                self._warnings.append(f"权重值无效，已忽略：{raw_key}")
                continue
            if not isinstance(raw_visible, bool):
                self._warnings.append(f"visible 值无效，已忽略：{raw_key}")
                continue

            entries[weight_key(raw_key)] = SearchRecord(
                weight=raw_weight,
                visible=raw_visible,
            )

        self._entries = entries

    def weight_for(self, path: Path) -> int:
        record = self._entries.get(weight_key(path))
        return record.weight if record is not None else 0

    def is_visible(self, path: Path) -> bool:
        record = self._entries.get(weight_key(path))
        return record.visible if record is not None else True

    def snapshot(self) -> dict[str, SearchRecord]:
        return dict(self._entries)

    def record_launch(self, path: Path) -> bool:
        key = weight_key(path)
        current = self._entries.get(key, SearchRecord())
        self._entries[key] = SearchRecord(
            weight=current.weight + 1,
            visible=current.visible,
        )
        return self._save()

    def sync_entries(
        self,
        discovered_paths: Iterable[Path],
        search_roots: Iterable[Path],
    ) -> bool:
        discovered = {weight_key(path) for path in discovered_paths}
        changed = False

        for key in discovered:
            if key not in self._entries:
                self._entries[key] = SearchRecord()
                changed = True

        accessible_roots: list[str] = []
        for root in search_roots:
            root_key = weight_key(root)
            try:
                if Path(root_key).is_dir():
                    accessible_roots.append(root_key)
            except (OSError, ValueError):
                continue

        for key in list(self._entries):
            if key in discovered:
                continue
            path = Path(key)
            try:
                if path.exists():
                    continue
            except (OSError, ValueError):
                continue
            if not any(_is_under(key, root) for root in accessible_roots):
                continue
            del self._entries[key]
            changed = True

        if changed:
            self._save()
        return changed

    def _save(self) -> bool:
        payload = {
            "version": SEARCH_CONFIG_VERSION,
            "entries": {
                key: {
                    "weight": record.weight,
                    "visible": record.visible,
                }
                for key, record in self._entries.items()
            },
        }
        temporary_path: Path | None = None

        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=self._path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self._path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._warnings.append(f"保存搜索配置文件失败：{exc}")
            return False

        return True

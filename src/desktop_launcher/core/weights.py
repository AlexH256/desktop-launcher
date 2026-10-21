import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from desktop_launcher.core.config import APP_DIR_NAME

WEIGHTS_FILE_NAME = "weights.json"
WEIGHTS_VERSION = 1


def default_weights_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / APP_DIR_NAME / WEIGHTS_FILE_NAME


def weight_key(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _is_under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


class WeightStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = (path or default_weights_path()).expanduser()
        self._weights: dict[str, int] = {}
        self._warnings: list[str] = []

    @property
    def path(self) -> Path:
        return self._path

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    def load(self) -> None:
        self._warnings.clear()
        self._weights = {}
        if not self._path.exists():
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self._warnings.append(f"读取权重文件失败，已使用空权重：{exc}")
            return

        if not isinstance(raw, dict):
            self._warnings.append("权重文件格式无效，已使用空权重")
            return

        version = raw.get("version")
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != WEIGHTS_VERSION
        ):
            self._warnings.append(f"权重文件版本不支持：{version}，已使用空权重")
            return

        raw_weights = raw.get("weights")
        if not isinstance(raw_weights, dict):
            self._warnings.append("权重文件缺少 weights 表，已使用空权重")
            return

        weights: dict[str, int] = {}
        for raw_key, raw_value in raw_weights.items():
            if not isinstance(raw_key, str) or not raw_key:
                self._warnings.append("权重文件包含无效路径，已忽略")
                continue
            if (
                isinstance(raw_value, bool)
                or not isinstance(raw_value, int)
                or raw_value < 0
            ):
                self._warnings.append(f"权重值无效，已忽略：{raw_key}")
                continue

            key = weight_key(raw_key)
            previous = weights.get(key)
            if previous is None or raw_value > previous:
                weights[key] = raw_value

        self._weights = weights

    def weight_for(self, path: Path) -> int:
        return self._weights.get(weight_key(path), 0)

    def snapshot(self) -> dict[str, int]:
        return dict(self._weights)

    def record_launch(self, path: Path) -> bool:
        key = weight_key(path)
        self._weights[key] = self._weights.get(key, 0) + 1
        return self._save()

    def cleanup_missing(
        self,
        discovered_paths: Iterable[Path],
        search_roots: Iterable[Path],
    ) -> bool:
        discovered = {weight_key(path) for path in discovered_paths}
        accessible_roots: list[str] = []
        for root in search_roots:
            root_key = weight_key(root)
            try:
                if Path(root_key).is_dir():
                    accessible_roots.append(root_key)
            except (OSError, ValueError):
                continue

        removed = False
        for key in list(self._weights):
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
            del self._weights[key]
            removed = True

        if removed:
            self._save()
        return removed

    def _save(self) -> bool:
        payload = {
            "version": WEIGHTS_VERSION,
            "weights": self._weights,
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
            self._warnings.append(f"保存权重文件失败：{exc}")
            return False

        return True

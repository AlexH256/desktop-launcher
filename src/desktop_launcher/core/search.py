import os
import time
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from desktop_launcher.core.search_config import weight_key

REFRESH_THROTTLE_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class AppEntry:
    name: str
    path: Path


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def _compact(text: str) -> str:
    return "".join(_normalize(text).split())


def _is_subsequence(needle: str, haystack: str) -> bool:
    if not needle:
        return True
    position = 0
    for character in haystack:
        if character == needle[position]:
            position += 1
            if position == len(needle):
                return True
    return False


def subsequence_match(query: str, text: str) -> bool:
    return _is_subsequence(_compact(query), _compact(text))


def _match_rank(needle: str, haystack: str) -> int | None:
    if needle == haystack:
        return 0
    if haystack.startswith(needle):
        return 1
    if needle in haystack:
        return 2
    if _is_subsequence(needle, haystack):
        return 3
    return None


def filter_entries(
    entries: Sequence[AppEntry],
    query: str,
    weights: Mapping[str, int] | None = None,
) -> tuple[AppEntry, ...]:
    weight_map = weights or {}
    needle = _compact(query)
    if not needle:
        return tuple(
            sorted(
                entries,
                key=lambda entry: (
                    -weight_map.get(weight_key(entry.path), 0),
                    _compact(entry.name),
                    os.path.normcase(str(entry.path)),
                ),
            )
        )

    matches: list[tuple[int, int, str, str, AppEntry]] = []
    for entry in entries:
        haystack = _compact(entry.name)
        rank = _match_rank(needle, haystack)
        if rank is None:
            continue
        matches.append(
            (
                rank,
                -weight_map.get(weight_key(entry.path), 0),
                haystack,
                os.path.normcase(str(entry.path)),
                entry,
            )
        )

    matches.sort(key=lambda item: item[:4])
    return tuple(item[4] for item in matches)


def scan_links(paths: Sequence[Path], max_depth: int) -> tuple[AppEntry, ...]:
    limit = max(1, max_depth)
    entries: list[AppEntry] = []
    seen_names: set[str] = set()

    for root in paths:
        for entry in _walk_links(Path(root), 1, limit):
            key = _compact(entry.name)
            if key in seen_names:
                continue
            seen_names.add(key)
            entries.append(entry)

    return tuple(entries)


def _walk_links(directory: Path, depth: int, max_depth: int) -> Iterator[AppEntry]:
    try:
        with os.scandir(directory) as iterator:
            items = sorted(iterator, key=lambda item: item.name.casefold())
    except OSError:
        return

    for item in items:
        try:
            if item.is_file(follow_symlinks=False) and item.name.casefold().endswith(
                ".lnk"
            ):
                path = Path(item.path)
                yield AppEntry(path.stem, path)
        except OSError:
            continue

    if depth >= max_depth:
        return

    for item in items:
        try:
            if item.is_dir(follow_symlinks=False):
                yield from _walk_links(Path(item.path), depth + 1, max_depth)
        except OSError:
            continue


class _ScanSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class _ScanTask(QRunnable):
    def __init__(
        self,
        paths: Sequence[Path],
        max_depth: int,
        signals: _ScanSignals,
    ) -> None:
        super().__init__()
        self._paths = tuple(paths)
        self._max_depth = max_depth
        self._signals = signals

    def run(self) -> None:
        try:
            entries = scan_links(self._paths, self._max_depth)
        except Exception as exc:
            self._signals.failed.emit(str(exc))
        else:
            self._signals.finished.emit(entries)


class LinkIndex(QObject):
    started = Signal()
    updated = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        paths: Sequence[Path],
        max_depth: int,
        parent: QObject | None = None,
        throttle_seconds: float = REFRESH_THROTTLE_SECONDS,
    ) -> None:
        super().__init__(parent)
        self._paths = tuple(paths)
        self._max_depth = max_depth
        self._throttle_seconds = throttle_seconds
        self._entries: tuple[AppEntry, ...] = ()
        self._scanning = False
        self._last_scan = 0.0
        self._scan_signals: _ScanSignals | None = None
        self._thread_pool = QThreadPool(self)

    @property
    def entries(self) -> tuple[AppEntry, ...]:
        return self._entries

    @property
    def scanning(self) -> bool:
        return self._scanning

    def search(self, query: str) -> tuple[AppEntry, ...]:
        return filter_entries(self._entries, query)

    def refresh(self, force: bool = False) -> None:
        if self._scanning:
            return

        now = time.monotonic()
        if (
            not force
            and self._last_scan > 0
            and now - self._last_scan < self._throttle_seconds
        ):
            return

        self._scanning = True
        signals = _ScanSignals()
        signals.finished.connect(self._on_finished)
        signals.failed.connect(self._on_failed)
        self._scan_signals = signals
        self.started.emit()
        self._thread_pool.start(_ScanTask(self._paths, self._max_depth, signals))

    def _on_finished(self, entries: object) -> None:
        self._finish_scan()
        if not isinstance(entries, tuple):
            return
        self._entries = cast(tuple[AppEntry, ...], entries)
        self.updated.emit(self._entries)

    def _on_failed(self, message: str) -> None:
        self._finish_scan()
        self.failed.emit(message)

    def _finish_scan(self) -> None:
        self._scanning = False
        self._last_scan = time.monotonic()
        self._scan_signals = None

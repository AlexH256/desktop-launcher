import json
from pathlib import Path

from desktop_launcher.core import search_config as config_module
from desktop_launcher.core.search_config import (
    SearchConfigStore,
    SearchRecord,
    weight_key,
)


def make_store(tmp_path: Path) -> SearchConfigStore:
    store = SearchConfigStore(tmp_path / "search-config.json")
    store.load()
    return store


def test_missing_file_has_empty_entries(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.snapshot() == {}
    assert store.weight_for(tmp_path / "app.lnk") == 0
    assert store.is_visible(tmp_path / "app.lnk") is True
    assert store.warnings == ()


def test_record_launch_increments_and_persists(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")

    assert store.record_launch(path) is True
    assert store.record_launch(path) is True
    assert store.weight_for(path) == 2
    assert store.is_visible(path) is True

    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["version"] == 2
    assert raw["entries"][weight_key(path)] == {
        "weight": 2,
        "visible": True,
    }

    reloaded = make_store(tmp_path)
    assert reloaded.snapshot() == {weight_key(path): SearchRecord(2, True)}
    assert reloaded.warnings == ()


def test_record_launch_preserves_visibility(tmp_path: Path) -> None:
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")
    config_path = tmp_path / "search-config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 2,
                "entries": {
                    weight_key(path): {"weight": 1, "visible": False},
                },
            }
        ),
        encoding="utf-8",
    )
    store = SearchConfigStore(config_path)
    store.load()

    assert store.record_launch(path) is True
    assert store.snapshot()[weight_key(path)] == SearchRecord(2, False)


def test_set_visible_preserves_weight_and_persists(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")
    store.record_launch(path)
    store.record_launch(path)

    assert store.set_visible(path, False) is True
    assert store.weight_for(path) == 2
    assert store.is_visible(path) is False

    reloaded = make_store(tmp_path)
    assert reloaded.weight_for(path) == 2
    assert reloaded.is_visible(path) is False


def test_set_visibility_updates_multiple_entries(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = tmp_path / "first.lnk"
    second = tmp_path / "second.lnk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    store.record_launch(first)
    store.record_launch(second)

    assert store.set_visibility(
        {
            weight_key(first): False,
            weight_key(second): False,
        }
    ) is True
    assert store.is_visible(first) is False
    assert store.is_visible(second) is False

    reloaded = make_store(tmp_path)
    assert reloaded.is_visible(first) is False
    assert reloaded.is_visible(second) is False


def test_set_visible_creates_missing_record(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    path = Path("C:/Apps/App.lnk")

    assert store.set_visible(path, False) is True
    assert store.is_visible(path) is False
    assert store.weight_for(path) == 0


def test_set_visibility_rolls_back_on_save_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")
    store.record_launch(path)

    def fail(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(config_module.os, "replace", fail)

    assert store.set_visible(path, False) is False
    assert store.is_visible(path) is True
    assert store.weight_for(path) == 1
    assert store.warnings
    assert list(tmp_path.glob("*.tmp")) == []


def test_weight_key_is_case_insensitive(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.record_launch(Path("C:/Apps/App.lnk"))

    assert store.weight_for(Path("c:/apps/app.lnk")) == 1


def test_visible_defaults_to_true_when_omitted(tmp_path: Path) -> None:
    config_path = tmp_path / "search-config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 2,
                "entries": {
                    "C:/Apps/App.lnk": {"weight": 3},
                },
            }
        ),
        encoding="utf-8",
    )
    store = SearchConfigStore(config_path)
    store.load()

    record = store.snapshot()[weight_key(Path("C:/Apps/App.lnk"))]
    assert record == SearchRecord(3, True)


def test_invalid_json_falls_back_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "search-config.json"
    path.write_text("{", encoding="utf-8")

    store = SearchConfigStore(path)
    store.load()

    assert store.snapshot() == {}
    assert store.warnings


def test_invalid_values_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "search-config.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "entries": {
                    "a": {"weight": True, "visible": True},
                    "b": {"weight": -1, "visible": True},
                    "c": {"weight": 2.5, "visible": True},
                    "d": {"weight": 3, "visible": "yes"},
                    "e": {"weight": 4, "visible": False},
                    "f": 5,
                },
            }
        ),
        encoding="utf-8",
    )

    store = SearchConfigStore(path)
    store.load()

    assert store.snapshot() == {
        weight_key(Path("e")): SearchRecord(4, False),
    }
    assert len(store.warnings) == 5


def test_old_weights_file_is_not_migrated(tmp_path: Path) -> None:
    old_path = tmp_path / "weights.json"
    old_content = json.dumps(
        {
            "version": 1,
            "weights": {"C:/Apps/App.lnk": 7},
        }
    )
    old_path.write_text(old_content, encoding="utf-8")
    store = SearchConfigStore(tmp_path / "search-config.json")

    store.load()

    assert store.snapshot() == {}
    assert old_path.read_text(encoding="utf-8") == old_content
    assert not store.path.exists()


def test_sync_adds_all_discovered_entries(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    first = tmp_path / "first.lnk"
    second = tmp_path / "second.lnk"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")

    assert store.sync_entries([first, second], [tmp_path]) is True

    assert store.snapshot() == {
        weight_key(first): SearchRecord(0, True),
        weight_key(second): SearchRecord(0, True),
    }
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["version"] == 2
    assert raw["entries"][weight_key(first)] == {
        "weight": 0,
        "visible": True,
    }


def test_sync_preserves_existing_records(tmp_path: Path) -> None:
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")
    config_path = tmp_path / "search-config.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 2,
                "entries": {
                    weight_key(path): {"weight": 5, "visible": False},
                },
            }
        ),
        encoding="utf-8",
    )
    store = SearchConfigStore(config_path)
    store.load()

    assert store.sync_entries([path], [tmp_path]) is False
    assert store.snapshot()[weight_key(path)] == SearchRecord(5, False)


def test_sync_removes_deleted_lnk_records(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    existing = tmp_path / "existing.lnk"
    existing.write_text("", encoding="utf-8")
    missing = tmp_path / "missing.lnk"
    store.record_launch(existing)
    store.record_launch(missing)

    assert store.sync_entries([existing], [tmp_path]) is True
    assert weight_key(existing) in store.snapshot()
    assert weight_key(missing) not in store.snapshot()

    reloaded = make_store(tmp_path)
    assert weight_key(existing) in reloaded.snapshot()
    assert weight_key(missing) not in reloaded.snapshot()


def test_sync_removes_deleted_directory_records(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    missing = tmp_path / "deleted" / "app.lnk"
    store.record_launch(missing)

    assert store.sync_entries([], [tmp_path]) is True
    assert weight_key(missing) not in store.snapshot()


def test_sync_keeps_existing_undiscovered_records(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    existing = tmp_path / "existing.lnk"
    existing.write_text("", encoding="utf-8")
    store.record_launch(existing)

    assert store.sync_entries([], [tmp_path]) is False
    assert weight_key(existing) in store.snapshot()


def test_sync_keeps_records_for_missing_root(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    offline_root = tmp_path / "offline"
    offline = offline_root / "app.lnk"
    store.record_launch(offline)

    assert store.sync_entries([], [offline_root]) is False
    assert weight_key(offline) in store.snapshot()


def test_save_failure_still_updates_memory(tmp_path: Path, monkeypatch) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(config_module.os, "replace", fail)

    assert store.record_launch(path) is False
    assert store.weight_for(path) == 1
    assert store.warnings
    assert list(tmp_path.glob("*.tmp")) == []

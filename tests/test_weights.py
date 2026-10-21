import json
from pathlib import Path

from desktop_launcher.core import weights as weights_module
from desktop_launcher.core.weights import WeightStore, weight_key


def make_store(tmp_path: Path) -> WeightStore:
    store = WeightStore(tmp_path / "weights.json")
    store.load()
    return store


def test_missing_file_has_empty_weights(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    assert store.snapshot() == {}
    assert store.weight_for(tmp_path / "app.lnk") == 0
    assert store.warnings == ()


def test_record_launch_increments_and_persists(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")

    assert store.record_launch(path) is True
    assert store.record_launch(path) is True
    assert store.weight_for(path) == 2

    raw = json.loads(store.path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["weights"][weight_key(path)] == 2

    reloaded = make_store(tmp_path)
    assert reloaded.weight_for(path) == 2
    assert reloaded.warnings == ()


def test_weight_key_is_case_insensitive(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.record_launch(Path("C:/Apps/App.lnk"))

    assert store.weight_for(Path("c:/apps/app.lnk")) == 1


def test_invalid_json_falls_back_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "weights.json"
    path.write_text("{", encoding="utf-8")

    store = WeightStore(path)
    store.load()

    assert store.snapshot() == {}
    assert store.warnings


def test_invalid_values_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "weights.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "weights": {
                    "a": True,
                    "b": -1,
                    "c": 2.5,
                    "d": 3,
                },
            }
        ),
        encoding="utf-8",
    )

    store = WeightStore(path)
    store.load()

    assert store.weight_for(Path("a")) == 0
    assert store.weight_for(Path("b")) == 0
    assert store.weight_for(Path("c")) == 0
    assert store.weight_for(Path("d")) == 3
    assert len(store.warnings) == 3


def test_cleanup_removes_deleted_lnk_records(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    existing = tmp_path / "existing.lnk"
    existing.write_text("", encoding="utf-8")
    missing = tmp_path / "missing.lnk"
    store.record_launch(existing)
    store.record_launch(missing)

    assert store.cleanup_missing([existing], [tmp_path]) is True
    assert store.weight_for(existing) == 1
    assert store.weight_for(missing) == 0

    reloaded = make_store(tmp_path)
    assert reloaded.weight_for(existing) == 1
    assert reloaded.weight_for(missing) == 0


def test_cleanup_removes_deleted_directory_records(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    missing = tmp_path / "deleted" / "app.lnk"
    store.record_launch(missing)

    assert store.cleanup_missing([], [tmp_path]) is True
    assert store.weight_for(missing) == 0


def test_cleanup_keeps_existing_undiscovered_records(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    existing = tmp_path / "existing.lnk"
    existing.write_text("", encoding="utf-8")
    store.record_launch(existing)

    assert store.cleanup_missing([], [tmp_path]) is False
    assert store.weight_for(existing) == 1


def test_cleanup_keeps_records_for_missing_root(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    offline_root = tmp_path / "offline"
    offline = offline_root / "app.lnk"
    store.record_launch(offline)

    assert store.cleanup_missing([], [offline_root]) is False
    assert store.weight_for(offline) == 1


def test_save_failure_still_updates_memory(tmp_path: Path, monkeypatch) -> None:
    store = make_store(tmp_path)
    path = tmp_path / "app.lnk"
    path.write_text("", encoding="utf-8")

    def fail(*args, **kwargs):
        raise OSError("boom")

    monkeypatch.setattr(weights_module.os, "replace", fail)

    assert store.record_launch(path) is False
    assert store.weight_for(path) == 1
    assert store.warnings
    assert list(tmp_path.glob("*.tmp")) == []

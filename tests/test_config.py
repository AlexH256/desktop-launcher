from pathlib import Path

from desktop_launcher.core.config import (
    DEFAULT_AUTOSTART,
    DEFAULT_HOTKEY,
    DEFAULT_MAX_DEPTH,
    load_config,
)


def write_config(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def test_creates_default_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    result = load_config(config_path)

    assert result.created
    assert config_path.exists()
    assert result.config.hotkey.text == DEFAULT_HOTKEY
    assert result.config.autostart is True
    assert result.config.search.max_depth == DEFAULT_MAX_DEPTH
    assert len(result.config.search.paths) >= 1
    assert "autostart = true" in config_path.read_text(encoding="utf-8")
    assert result.warnings == ()


def test_loads_custom_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        'hotkey = "Ctrl+Shift+K"\n'
        "autostart = false\n"
        "\n"
        "[search]\n"
        "paths = []\n"
        "max_depth = 2\n",
    )

    result = load_config(config_path)

    assert not result.created
    assert result.config.hotkey.text == "Ctrl+Shift+K"
    assert result.config.autostart is False
    assert result.config.search.paths == ()
    assert result.config.search.max_depth == 2


def test_missing_autostart_defaults_to_true(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, 'hotkey = "Alt+Space"\n[search]\npaths = []\n')

    result = load_config(config_path)

    assert result.config.autostart is DEFAULT_AUTOSTART


def test_invalid_autostart_falls_back_to_true(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        'hotkey = "Alt+Space"\nautostart = "yes"\n[search]\npaths = []\n',
    )

    result = load_config(config_path)

    assert result.config.autostart is True
    assert any("autostart" in warning for warning in result.warnings)


def test_expands_relative_and_environment_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    apps_dir = tmp_path / "apps"
    apps_dir.mkdir()
    env_dir = tmp_path / "env-dir"
    env_dir.mkdir()
    monkeypatch.setenv("LAUNCHER_TEST_DIR", str(env_dir))
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        'hotkey = "Alt+Space"\n'
        "[search]\n"
        'paths = ["apps", "%LAUNCHER_TEST_DIR%", "apps"]\n'
        "max_depth = 3\n",
    )

    result = load_config(config_path)

    assert result.config.search.paths == (apps_dir.resolve(), env_dir.resolve())


def test_warns_about_missing_path(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    missing = tmp_path / "missing"
    write_config(
        config_path,
        'hotkey = "Alt+Space"\n'
        "[search]\n"
        f'paths = ["{missing.as_posix()}"]\n',
    )

    result = load_config(config_path)

    assert result.config.search.paths == (missing.resolve(),)
    assert any("不存在" in warning for warning in result.warnings)


def test_invalid_toml_falls_back_without_overwriting(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    original = "hotkey = ["
    write_config(config_path, original)

    result = load_config(config_path)

    assert result.config.hotkey.text == DEFAULT_HOTKEY
    assert result.warnings
    assert config_path.read_text(encoding="utf-8") == original


def test_invalid_hotkey_falls_back(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, 'hotkey = "Space"\n')

    result = load_config(config_path)

    assert result.config.hotkey.text == DEFAULT_HOTKEY
    assert any("快捷键" in warning for warning in result.warnings)


def test_invalid_search_values_fall_back(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        'hotkey = "Alt+Space"\n'
        "[search]\n"
        'paths = "not-a-list"\n'
        "max_depth = 0\n",
    )

    result = load_config(config_path)

    assert result.config.search.max_depth == DEFAULT_MAX_DEPTH
    assert len(result.config.search.paths) >= 1
    assert any("paths" in warning for warning in result.warnings)
    assert any("max_depth" in warning for warning in result.warnings)


def test_unknown_keys_warn(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        'hotkey = "Alt+Space"\n'
        "unknown = 1\n"
        "[search]\n"
        "paths = []\n"
        "unknown_search = 2\n",
    )

    result = load_config(config_path)

    assert any("unknown" in warning for warning in result.warnings)
    assert any("unknown_search" in warning for warning in result.warnings)


def test_all_invalid_paths_fall_back(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    write_config(
        config_path,
        'hotkey = "Alt+Space"\n'
        "[search]\n"
        'paths = ["", 3]\n',
    )

    result = load_config(config_path)

    assert len(result.config.search.paths) >= 1
    assert any("有效路径" in warning for warning in result.warnings)

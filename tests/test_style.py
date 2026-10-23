from pathlib import Path

from desktop_launcher.core.style import (
    DEFAULT_STYLESHEET,
    STYLE_FILE_NAME,
    default_style_path,
    load_stylesheet,
)


def test_default_style_path_uses_appdata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert default_style_path() == tmp_path / "DesktopLauncher" / STYLE_FILE_NAME


def test_missing_file_creates_default(tmp_path: Path) -> None:
    path = tmp_path / "style.css"

    result = load_stylesheet(path)

    assert result.created
    assert result.stylesheet == DEFAULT_STYLESHEET
    assert result.warnings == ()
    assert path.read_text(encoding="utf-8") == DEFAULT_STYLESHEET


def test_loads_custom_stylesheet(tmp_path: Path) -> None:
    path = tmp_path / "style.css"
    custom = "#card { background-color: red; }\n"
    path.write_text(custom, encoding="utf-8")

    result = load_stylesheet(path)

    assert not result.created
    assert result.stylesheet == custom
    assert result.warnings == ()


def test_read_failure_falls_back_to_default(tmp_path: Path) -> None:
    path = tmp_path / "style.css"
    path.mkdir()

    result = load_stylesheet(path)

    assert not result.created
    assert result.stylesheet == DEFAULT_STYLESHEET
    assert result.warnings


def test_invalid_encoding_falls_back_to_default(tmp_path: Path) -> None:
    path = tmp_path / "style.css"
    path.write_bytes(b"\xff\xfe\x00")

    result = load_stylesheet(path)

    assert result.stylesheet == DEFAULT_STYLESHEET
    assert result.warnings


def test_write_failure_returns_default(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("", encoding="utf-8")
    path = blocker / "style.css"

    result = load_stylesheet(path)

    assert not result.created
    assert result.stylesheet == DEFAULT_STYLESHEET
    assert result.warnings

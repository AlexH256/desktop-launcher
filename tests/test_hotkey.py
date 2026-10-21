import pytest

from desktop_launcher.core.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    HotkeyBinding,
    HotkeyParseError,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("Alt+Space", HotkeyBinding("Alt+Space", MOD_ALT, 0x20)),
        (" ctrl + shift + k ", HotkeyBinding("ctrl+shift+k", MOD_CONTROL | MOD_SHIFT, ord("K"))),
        ("Ctrl+F12", HotkeyBinding("Ctrl+F12", MOD_CONTROL, 0x7B)),
        ("Win+Slash", HotkeyBinding("Win+Slash", MOD_WIN, 0xBF)),
    ],
)
def test_parse_hotkey(spec: str, expected: HotkeyBinding) -> None:
    assert parse_hotkey(spec) == expected


@pytest.mark.parametrize(
    "spec",
    [
        "Space",
        "Ctrl+A+B",
        "Ctrl+Unknown",
        "Ctrl+Control+A",
        "   ",
    ],
)
def test_invalid_hotkey(spec: str) -> None:
    with pytest.raises(HotkeyParseError):
        parse_hotkey(spec)

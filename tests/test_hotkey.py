import unittest

from desktop_launcher.core.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    HotkeyParseError,
    parse_hotkey,
)


class ParseHotkeyTests(unittest.TestCase):
    def test_alt_space(self) -> None:
        binding = parse_hotkey("Alt+Space")
        self.assertEqual(binding.text, "Alt+Space")
        self.assertEqual(binding.modifiers, MOD_ALT)
        self.assertEqual(binding.key, 0x20)

    def test_case_and_spacing_are_normalized(self) -> None:
        binding = parse_hotkey(" ctrl + shift + k ")
        self.assertEqual(binding.text, "ctrl+shift+k")
        self.assertEqual(binding.modifiers, MOD_CONTROL | MOD_SHIFT)
        self.assertEqual(binding.key, ord("K"))

    def test_function_key(self) -> None:
        binding = parse_hotkey("Ctrl+F12")
        self.assertEqual(binding.key, 0x7B)

    def test_punctuation_key(self) -> None:
        binding = parse_hotkey("Win+Slash")
        self.assertEqual(binding.key, 0xBF)

    def test_requires_modifier(self) -> None:
        with self.assertRaises(HotkeyParseError):
            parse_hotkey("Space")

    def test_requires_single_key(self) -> None:
        with self.assertRaises(HotkeyParseError):
            parse_hotkey("Ctrl+A+B")

    def test_unknown_key(self) -> None:
        with self.assertRaises(HotkeyParseError):
            parse_hotkey("Ctrl+Unknown")

    def test_duplicate_modifier(self) -> None:
        with self.assertRaises(HotkeyParseError):
            parse_hotkey("Ctrl+Control+A")

    def test_empty(self) -> None:
        with self.assertRaises(HotkeyParseError):
            parse_hotkey("   ")


if __name__ == "__main__":
    unittest.main()

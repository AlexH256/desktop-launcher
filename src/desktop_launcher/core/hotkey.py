import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

WM_HOTKEY = 0x0312
VK_SPACE = 0x20

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
    "meta": MOD_WIN,
    "super": MOD_WIN,
}

_KEYS = {
    "space": VK_SPACE,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "comma": 0xBC,
    ",": 0xBC,
    "period": 0xBE,
    "dot": 0xBE,
    ".": 0xBE,
    "slash": 0xBF,
    "/": 0xBF,
    "backslash": 0xDC,
    "\\": 0xDC,
    "semicolon": 0xBA,
    ";": 0xBA,
    "quote": 0xDE,
    "'": 0xDE,
    "minus": 0xBD,
    "dash": 0xBD,
    "-": 0xBD,
    "equal": 0xBB,
    "=": 0xBB,
    "lbracket": 0xDB,
    "[": 0xDB,
    "rbracket": 0xDD,
    "]": 0xDD,
    "grave": 0xC0,
    "backquote": 0xC0,
    "`": 0xC0,
}

for _letter in "abcdefghijklmnopqrstuvwxyz":
    _KEYS[_letter] = ord(_letter.upper())

for _digit in "0123456789":
    _KEYS[_digit] = ord(_digit)

for _number in range(1, 25):
    _KEYS[f"f{_number}"] = 0x6F + _number


class HotkeyParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HotkeyBinding:
    text: str
    modifiers: int
    key: int


def parse_hotkey(spec: str) -> HotkeyBinding:
    if not isinstance(spec, str) or not spec.strip():
        raise HotkeyParseError("快捷键不能为空")

    parts = [part.strip() for part in spec.split("+")]
    if any(not part for part in parts):
        raise HotkeyParseError(f"快捷键格式无效：{spec}")

    modifiers = 0
    key: int | None = None
    for part in parts:
        token = part.lower()
        if token in _MODIFIERS:
            bit = _MODIFIERS[token]
            if modifiers & bit:
                raise HotkeyParseError(f"修饰键重复：{part}")
            modifiers |= bit
            continue
        if key is not None:
            raise HotkeyParseError(f"快捷键只能包含一个普通按键：{spec}")
        if token not in _KEYS:
            raise HotkeyParseError(f"不支持的按键：{part}")
        key = _KEYS[token]

    if modifiers == 0:
        raise HotkeyParseError("快捷键必须包含至少一个修饰键")
    if key is None:
        raise HotkeyParseError("快捷键缺少普通按键")

    return HotkeyBinding("+".join(parts), modifiers, key)


class _HotkeyEventFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkey") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):
        if not self._owner.registered:
            return False, 0
        if bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and int(msg.wParam) == self._owner.hotkey_id:
            self._owner.activated.emit()
            return True, 0
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()

    def __init__(self, modifiers: int, key: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._modifiers = modifiers
        self._key = key
        self._id = 0x4C41
        self._registered = False
        self._filter = _HotkeyEventFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    @property
    def hotkey_id(self) -> int:
        return self._id

    @property
    def registered(self) -> bool:
        return self._registered

    def register(self) -> bool:
        if self._registered:
            return True
        user32 = ctypes.windll.user32
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        result = user32.RegisterHotKey(None, self._id, self._modifiers, self._key)
        self._registered = bool(result)
        return self._registered

    def unregister(self) -> None:
        if not self._registered:
            return
        ctypes.windll.user32.UnregisterHotKey(None, self._id)
        self._registered = False

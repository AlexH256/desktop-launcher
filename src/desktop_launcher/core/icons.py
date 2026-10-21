import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

SHGFI_ICON = 0x000000100
SHGFI_SHELLICONSIZE = 0x000000004


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_shell32.SHGetFileInfoW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(_SHFILEINFOW),
    wintypes.UINT,
    wintypes.UINT,
]
_shell32.SHGetFileInfoW.restype = ctypes.c_size_t

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.DestroyIcon.argtypes = [wintypes.HICON]
_user32.DestroyIcon.restype = wintypes.BOOL


class LinkIconProvider:
    def __init__(self) -> None:
        self._cache: dict[str, QIcon] = {}
        self._fallback = QApplication.style().standardIcon(
            QStyle.StandardPixmap.SP_FileIcon
        )

    def icon_for(self, path: Path) -> QIcon:
        key = os.path.normcase(str(path))
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        try:
            icon = _extract_icon(path)
        except Exception:
            icon = None
        if icon is None or icon.isNull():
            icon = self._fallback
        self._cache[key] = icon
        return icon


def _extract_icon(path: Path) -> QIcon | None:
    info = _SHFILEINFOW()
    result = _shell32.SHGetFileInfoW(
        str(path),
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_ICON | SHGFI_SHELLICONSIZE,
    )
    if not result or not info.hIcon:
        return None

    try:
        image = QImage.fromHICON(int(info.hIcon))
    finally:
        _user32.DestroyIcon(info.hIcon)

    if image.isNull():
        return None

    pixmap = QPixmap.fromImage(image)
    if pixmap.isNull():
        return None
    return QIcon(pixmap)

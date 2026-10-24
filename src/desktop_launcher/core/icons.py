import ctypes
import os
import threading
from ctypes import wintypes
from pathlib import Path

from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QStyle

SHGFI_ICON = 0x000000100
SHGFI_SHELLICONSIZE = 0x000000004
SLGP_RAWPATH = 0x000000004
STGM_READ = 0
CLSCTX_INPROC_SERVER = 1
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = -2147417850
MAX_PATH_BUFFER = 1024


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


_ole32 = ctypes.WinDLL("ole32", use_last_error=True)
_ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.c_long
_ole32.CoCreateInstance.argtypes = [
    ctypes.POINTER(_GUID),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(_GUID),
    ctypes.POINTER(ctypes.c_void_p),
]
_ole32.CoCreateInstance.restype = ctypes.c_long
_ole32.IIDFromString.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(_GUID)]
_ole32.IIDFromString.restype = ctypes.c_long

_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_shell32.SHGetFileInfoW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(_SHFILEINFOW),
    wintypes.UINT,
    wintypes.UINT,
]
_shell32.SHGetFileInfoW.restype = ctypes.c_size_t
_shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.c_int,
    ctypes.POINTER(wintypes.HICON),
    ctypes.POINTER(wintypes.HICON),
    wintypes.UINT,
]
_shell32.ExtractIconExW.restype = wintypes.UINT

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.DestroyIcon.argtypes = [wintypes.HICON]
_user32.DestroyIcon.restype = wintypes.BOOL


def _guid_from_string(value: str) -> _GUID:
    guid = _GUID()
    result = _ole32.IIDFromString(value, ctypes.byref(guid))
    if result < 0:
        raise OSError(f"IIDFromString failed: {result}")
    return guid


_CLSID_SHELL_LINK = _guid_from_string("{00021401-0000-0000-C000-000000000046}")
_IID_ISHELL_LINK_W = _guid_from_string("{000214F9-0000-0000-C000-000000000046}")
_IID_IPERSIST_FILE = _guid_from_string("{0000010b-0000-0000-C000-000000000046}")

_com_state = threading.local()


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


def _ensure_com() -> bool:
    if getattr(_com_state, "initialized", False):
        return True

    result = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if result < 0 and result != RPC_E_CHANGED_MODE:
        return False

    _com_state.initialized = True
    return True


def _com_method(pointer: ctypes.c_void_p, index: int, restype, *argtypes):
    vtable = ctypes.cast(
        pointer,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
    ).contents
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])


def _release(pointer: ctypes.c_void_p) -> None:
    if pointer.value:
        _com_method(pointer, 2, ctypes.c_long)(pointer)


def _resolve_shortcut(path: Path) -> tuple[str, str, int] | None:
    if not _ensure_com():
        return None

    link = ctypes.c_void_p()
    result = _ole32.CoCreateInstance(
        ctypes.byref(_CLSID_SHELL_LINK),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(_IID_ISHELL_LINK_W),
        ctypes.byref(link),
    )
    if result < 0 or not link.value:
        return None

    persist = ctypes.c_void_p()
    try:
        query = _com_method(
            link,
            0,
            ctypes.c_long,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        )
        result = query(
            link,
            ctypes.byref(_IID_IPERSIST_FILE),
            ctypes.byref(persist),
        )
        if result < 0 or not persist.value:
            return None

        load = _com_method(
            persist,
            5,
            ctypes.c_long,
            wintypes.LPCWSTR,
            wintypes.DWORD,
        )
        if load(persist, str(path), STGM_READ) < 0:
            return None

        target_buffer = ctypes.create_unicode_buffer(MAX_PATH_BUFFER)
        get_path = _com_method(
            link,
            3,
            ctypes.c_long,
            wintypes.LPWSTR,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        get_path(
            link,
            target_buffer,
            MAX_PATH_BUFFER,
            None,
            SLGP_RAWPATH,
        )

        icon_buffer = ctypes.create_unicode_buffer(MAX_PATH_BUFFER)
        icon_index = ctypes.c_int()
        get_icon = _com_method(
            link,
            16,
            ctypes.c_long,
            wintypes.LPWSTR,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_int),
        )
        get_icon(
            link,
            icon_buffer,
            MAX_PATH_BUFFER,
            ctypes.byref(icon_index),
        )

        return target_buffer.value, icon_buffer.value, icon_index.value
    finally:
        _release(persist)
        _release(link)


def _extract_icon(path: Path) -> QIcon | None:
    resolved = _resolve_shortcut(path)
    if resolved is None:
        return None

    target, icon_location, icon_index = resolved
    icon_file = _clean_path(icon_location)
    if (
        icon_file
        and not _is_shortcut_file(icon_file)
        and Path(icon_file).is_file()
    ):
        icon = _extract_indexed_icon(icon_file, icon_index)
        if icon is not None:
            return icon

    target_file = _clean_path(target)
    if target_file and not _is_shortcut_file(target_file):
        return _shell_icon(target_file)

    return None


def _clean_path(value: str) -> str:
    value = value.strip().strip('"')
    if not value:
        return ""
    return os.path.expanduser(os.path.expandvars(value))


def _is_shortcut_file(path: str) -> bool:
    return path.casefold().endswith(".lnk")


def _icon_from_hicon(handle) -> QIcon | None:
    if isinstance(handle, ctypes.c_void_p):
        value = handle.value or 0
    else:
        value = int(handle)
    if not value:
        return None

    try:
        image = QImage.fromHICON(value)
    finally:
        _user32.DestroyIcon(ctypes.c_void_p(value))

    if image.isNull():
        return None

    pixmap = QPixmap.fromImage(image)
    if pixmap.isNull():
        return None
    return QIcon(pixmap)


def _shell_icon(file_path: str) -> QIcon | None:
    info = _SHFILEINFOW()
    result = _shell32.SHGetFileInfoW(
        file_path,
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_ICON | SHGFI_SHELLICONSIZE,
    )
    if not result or not info.hIcon:
        return None
    return _icon_from_hicon(info.hIcon)


def _extract_indexed_icon(file_path: str, icon_index: int) -> QIcon | None:
    if icon_index == -1:
        return _shell_icon(file_path)

    hicon = wintypes.HICON()
    count = _shell32.ExtractIconExW(
        file_path,
        icon_index,
        ctypes.byref(hicon),
        None,
        1,
    )
    if not count or not hicon.value:
        return None
    return _icon_from_hicon(hicon)

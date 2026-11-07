"""Keeping saved passwords and login sessions private.

On Windows they are encrypted with your Windows account (the same protection Windows uses for saved Wi-Fi passwords),
so the files in data/accounts are useless on another computer or to another Windows user.
On other systems the files are only readable by your user account."""
import ctypes
import os
import sys
from pathlib import Path

_ENTROPY = b"bookkeeper-accounts-v1"


def available() -> bool:
    """True when passwords can be stored encrypted."""
    return sys.platform == "win32"


if sys.platform == "win32":
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data: bytes) -> _Blob:
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _call(fn, data: bytes) -> bytes:
        src, ent, out = _blob(data), _blob(_ENTROPY), _Blob()
        if not fn(ctypes.byref(src), None, ctypes.byref(ent), None, None, 0x01, ctypes.byref(out)):  # UI_FORBIDDEN
            raise OSError("Windows could not encrypt or decrypt the data")
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def protect(data: bytes) -> bytes:
        crypt = ctypes.windll.crypt32.CryptProtectData
        src, ent, out = _blob(data), _blob(_ENTROPY), _Blob()
        if not crypt(ctypes.byref(src), "Bookkeeper", ctypes.byref(ent), None, None, 0x01, ctypes.byref(out)):
            raise OSError("Windows could not encrypt the data")
        try:
            return b"DPAPI" + ctypes.string_at(out.pbData, out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def unprotect(blob: bytes) -> bytes:
        if not blob.startswith(b"DPAPI"):
            return blob
        return _call(ctypes.windll.crypt32.CryptUnprotectData, blob[5:])
else:
    def protect(data: bytes) -> bytes:
        return data

    def unprotect(blob: bytes) -> bytes:
        return blob


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(protect(data))
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read(path: Path) -> bytes | None:
    if not path.exists():
        return None
    try:
        return unprotect(path.read_bytes())
    except OSError:
        return None  # made by another Windows user or computer

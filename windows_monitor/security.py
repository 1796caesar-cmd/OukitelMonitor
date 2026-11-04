"""Keep Wonderfree credentials encrypted for the current Windows user (DPAPI)."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(raw: bytes):
    buffer = ctypes.create_string_buffer(raw)
    return DATA_BLOB(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _protect(raw: bytes, decrypt: bool = False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Захист облікових даних працює лише у Windows")
    source, buffer = _blob(raw)
    target = DATA_BLOB()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(ctypes.cast(target.pbData, ctypes.c_void_p))


def credentials_path(directory: Path) -> Path:
    return directory / "credentials.dat"


def save_credentials(directory: Path, credentials: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    target = credentials_path(directory)
    encrypted = _protect(json.dumps(credentials, ensure_ascii=False).encode("utf-8"))
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(encrypted)
    os.replace(tmp, target)


def load_credentials(directory: Path) -> dict | None:
    target = credentials_path(directory)
    if not target.exists():
        return None
    try:
        obj = json.loads(_protect(target.read_bytes(), decrypt=True).decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def delete_credentials(directory: Path) -> None:
    credentials_path(directory).unlink(missing_ok=True)

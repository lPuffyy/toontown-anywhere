"""Keeps the saved password protected with the Windows account's own key (DPAPI), so it is useless if the settings file is copied
to another computer or account. On other systems nothing is saved (the player types the password each time)."""
import base64
import sys


def available():
    return sys.platform == "win32"


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _blob(data):
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def protect(text):
        data = text.encode("utf8")
        inb, _keep = _blob(data)
        out = _Blob()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(inb), "TTA", None, None, None, 0, ctypes.byref(out)):
            return ""
        try:
            return base64.b64encode(ctypes.string_at(out.pbData, out.cbData)).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)

    def unprotect(blob):
        try:
            data = base64.b64decode(blob)
        except Exception:
            return ""
        inb, _keep = _blob(data)
        out = _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(inb), None, None, None, None, 0, ctypes.byref(out)):
            return ""
        try:
            return ctypes.string_at(out.pbData, out.cbData).decode("utf8")
        finally:
            ctypes.windll.kernel32.LocalFree(out.pbData)
else:
    def protect(text):
        return ""

    def unprotect(blob):
        return ""

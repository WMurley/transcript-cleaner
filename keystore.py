"""API keys in the computer's own password store (Windows Credential Manager, or the macOS Keychain).

Shared by the meeting-app connectors (Fathom, Granola). Keys never sit in a file the app or an agent can read.
"""

import subprocess
import sys

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _CRED(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _GENERIC, _LOCAL_MACHINE = 1, 2

    def get(target, account):
        p = ctypes.POINTER(_CRED)()
        if not _adv.CredReadW(target, _GENERIC, 0, ctypes.byref(p)):
            return ""
        try:
            return ctypes.string_at(p.contents.CredentialBlob, p.contents.CredentialBlobSize).decode("utf-16-le")
        finally:
            _adv.CredFree(p)

    def put(target, account, key, label):
        blob = key.encode("utf-16-le")
        buf = (ctypes.c_byte * len(blob)).from_buffer_copy(blob)
        c = _CRED(Type=_GENERIC, TargetName=target, CredentialBlobSize=len(blob),
                  CredentialBlob=ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)), Persist=_LOCAL_MACHINE,
                  UserName=f"{account}-api-key", Comment=f"Transcript Cleaner: {label} API key")
        if not _adv.CredWriteW(ctypes.byref(c), 0):
            raise OSError("Couldn't save the key to Windows Credential Manager.")

    def clear(target, account):
        _adv.CredDeleteW(target, _GENERIC, 0)

elif sys.platform == "darwin":
    def get(target, account):
        r = subprocess.run(["security", "find-generic-password", "-s", target, "-a", account, "-w"],
                           capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""

    def put(target, account, key, label):
        r = subprocess.run(["security", "add-generic-password", "-U", "-s", target, "-a", account, "-w", key],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise OSError("Couldn't save the key to the macOS Keychain.")

    def clear(target, account):
        subprocess.run(["security", "delete-generic-password", "-s", target, "-a", account], capture_output=True)

else:
    def get(target, account):
        return ""

    def put(target, account, key, label):
        raise OSError(f"Saving a {label} key is supported on Windows and Mac in this version.")

    def clear(target, account):
        pass

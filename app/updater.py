"""Updates from inside the app: check GitHub for a newer version, then swap in the app's own files.

Only the app's own files change. Python and its packages (.tools, .venv), your calls, clients and settings
(TranscriptCleaner-Vault, outside this folder), your look and logo (themes) and practice data stay as they
are. Every file an update replaces or removes is copied to .update/backup-<time> first. Files an older
version shipped and the new one doesn't are removed, using the list every release carries (FILES.txt), so
nothing else in the folder is touched. Packages are installed only when the release changed
requirements.lock. A developer copy (a git folder) is never updated this way: use git there.

The app goes online for this only when the person clicks Check for updates or Update now.
"""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "WMurley/transcript-cleaner"
BRANCH = "main"
# tests point this at a local folder (given as a file URL) holding VERSION and release.zip, never the internet
BASE = os.environ.get("CLEANER_UPDATE_BASE", "")
MAX_ZIP = 80 * 1024 * 1024
KEEP = {".tools", ".venv", "themes", "_practice", ".update", ".git", "Transcript Cleaner.app"}  # never written


def version_url():
    return f"{BASE}/VERSION" if BASE else f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/app/VERSION"


def zip_url():
    return f"{BASE}/release.zip" if BASE else f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"


def local_version(root):
    v = Path(root) / "app" / "VERSION"
    return v.read_text(encoding="utf-8").strip() if v.exists() else "1.0.0"  # the first release had no VERSION


def newer(a, b):
    """True when version a is newer than version b ("1.10.0" > "1.9.2")."""
    def parts(v):
        nums = [int(n) for n in re.findall(r"\d+", v)[:3]]
        return nums + [0] * (3 - len(nums))
    return parts(a) > parts(b)


def is_developer_copy(root):
    return (Path(root) / ".git").exists()


def _get(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": "TranscriptCleaner-updater"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError("The download was larger than expected, so it was stopped.")
    return data


def check(root):
    current = local_version(root)
    if is_developer_copy(root):
        return {"current": current, "available": False, "can_update": False,
                "message": "This is a developer copy (a git folder), so it updates with git, not from here."}
    try:
        latest = _get(version_url(), 100).decode("utf-8").strip()
    except Exception:
        return {"current": current, "available": False, "can_update": True,
                "message": "Couldn't reach GitHub to check. Check your internet connection and try again."}
    if not re.fullmatch(r"\d+(\.\d+){0,2}", latest):
        return {"current": current, "available": False, "can_update": True, "message": "Couldn't read the newest version number."}
    available = newer(latest, current)
    return {"current": current, "latest": latest, "available": available, "can_update": True,
            "message": f"Version {latest} is ready." if available else "You have the newest version."}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _kept(rel):
    return Path(rel).parts[0] in KEEP


def apply(root, data=None):
    """Download the newest release (or use data, the ZIP's bytes) and swap in its files. Returns a summary."""
    root = Path(root)
    if is_developer_copy(root):
        raise ValueError("This is a developer copy (a git folder). Update it with git.")
    data = data if data is not None else _get(zip_url(), MAX_ZIP)
    z = zipfile.ZipFile(io.BytesIO(data))
    entries = [i for i in z.infolist() if not i.is_dir()]
    prefix = os.path.commonprefix([i.filename for i in entries]).rpartition("/")[0]
    files = {}
    for info in entries:
        rel = info.filename[len(prefix) + 1:] if prefix else info.filename
        if not rel or rel.startswith("/") or ".." in Path(rel).parts or ":" in rel:
            raise ValueError("The download has a file in an unexpected place, so nothing was changed.")
        files[rel] = info
    if not {"app/app.py", "app/clean.py", "app/index.html", "app/VERSION", "app/FILES.txt"} <= set(files):
        raise ValueError("The download doesn't look like Transcript Cleaner, so nothing was changed.")
    new_list = set(z.read(files["app/FILES.txt"]).decode("utf-8").splitlines())
    old_list = set((root / "app" / "FILES.txt").read_text(encoding="utf-8").splitlines()) if (root / "app" / "FILES.txt").exists() else set()
    lock_before = _sha(root / "app" / "requirements.lock")
    backup = root / ".update" / time.strftime("backup-%Y%m%d-%H%M%S")

    def keep_copy(dest, rel):
        (backup / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, backup / rel)

    changed = removed = 0
    for rel, info in sorted(files.items()):
        if _kept(rel):
            continue
        body, dest = z.read(info), root / rel
        if dest.exists() and dest.read_bytes() == body:
            continue
        if dest.exists():
            keep_copy(dest, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".updating")
        tmp.write_bytes(body)
        os.replace(tmp, dest)  # each file is swapped whole, never left half-written
        if sys.platform != "win32" and ((info.external_attr >> 16) & 0o111 or rel.endswith(".command")):
            dest.chmod(dest.stat().st_mode | 0o755)
        changed += 1
    for rel in sorted(old_list - new_list):
        dest = root / rel
        if _kept(rel) or rel in files or not dest.is_file():
            continue
        keep_copy(dest, rel)
        dest.unlink()
        removed += 1
    return {"version": z.read(files["app/VERSION"]).decode("utf-8").strip(), "changed": changed, "removed": removed,
            "packages": _sha(root / "app" / "requirements.lock") != lock_before, "backup": str(backup)}


def install_packages(root):
    """After an update that changed requirements.lock: install exactly what it pins, the way setup does."""
    root = Path(root)
    tools = root / ".tools"
    uv = tools / ("uv.exe" if sys.platform == "win32" else "uv")
    py = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not uv.exists() or not py.exists():
        return False, "This update needs new packages. Run Setup Transcript Cleaner once more to install them."
    env = {**os.environ, "UV_PYTHON_INSTALL_DIR": str(tools / "python"), "UV_CACHE_DIR": str(tools / "cache"),
           "UV_PYTHON_BIN_DIR": str(tools / "bin"), "UV_PYTHON_INSTALL_BIN": "0", "UV_PYTHON_INSTALL_REGISTRY": "0",
           "UV_MANAGED_PYTHON": "1"}
    r = subprocess.run([str(uv), "pip", "install", "--python", str(py), "--require-hashes", "-r", str(root / "app" / "requirements.lock")],
                       env=env, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        return False, "The new packages didn't install. Run Setup Transcript Cleaner once more to finish."
    return True, ""


def relaunch(root):
    """Open a fresh copy of the app (the caller then closes this one)."""
    root = Path(root)
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(["wscript.exe", str(root / "app" / "Open Transcript Cleaner.vbs")], creationflags=flags, close_fds=True)
    elif sys.platform == "darwin":
        bundle = root / "Transcript Cleaner.app"
        subprocess.Popen(["open", "-n", str(bundle)] if bundle.is_dir() else ["open", str(root / "app" / "Open Transcript Cleaner.command")])
    else:
        subprocess.Popen([sys.executable, str(root / "app" / "app.py")], start_new_session=True)

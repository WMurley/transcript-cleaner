"""The guided tutorial leaves nothing behind: its sample folders go when it ends,
and folders from a tutorial closed partway through are pruned at the next start.
Runs entirely in a throwaway folder; never touches the app folder or a real vault."""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="tc-tutorial-cleanup-"))
os.environ["CLEANER_HOME"] = str(TMP / "vault")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402  (reads CLEANER_HOME at import)

app.HERE = TMP / "app"
app.HERE.mkdir()
results = []


def check(label, ok):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + label)


app.clean.init()
home_before = app.clean.HOME
app.start_tutorial()
session = app.TUTORIAL_SESSION
check("the tutorial gets its own sample folders", session["home"].is_dir() and session["exports"].is_dir())
app.end_tutorial()
check("ending the tutorial removes both sample folders", not session["home"].exists() and not session["exports"].exists())
check("ending the tutorial returns to the real vault", app.clean.HOME == home_before)

old = time.time() - 7 * 3600
stale = app.HERE / ("_tutorial-" + "a" * 32)
stale_exports = app.HERE / ("_tutorial-exports-" + "a" * 32)
fresh = app.HERE / ("_tutorial-" + "b" * 32)
shots = app.HERE / "_tutorial-shots"
for folder in (stale, stale_exports, fresh, shots):
    folder.mkdir()
for folder in (stale, stale_exports, shots):
    os.utime(folder, (old, old))
app.prune_tutorial_folders()
check("startup removes sample folders from a tutorial closed partway through", not stale.exists() and not stale_exports.exists())
check("startup keeps a recent tutorial (another open copy of the app may be using it)", fresh.is_dir())
check("startup leaves folders that are not tutorial samples alone", shots.is_dir())

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)

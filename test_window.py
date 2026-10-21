"""The app window: its own Chrome profile, and closing it stops the app within seconds (a reload doesn't).

Never opens Chrome: the window-close behaviour is switched on with CLEANER_TEST_BYE.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable
ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


def start(vault):
    (vault / "private").mkdir(parents=True, exist_ok=True)
    (vault / "_themes").mkdir(exist_ok=True)
    (vault / "_themes" / "active.json").write_text('{"tour_done": true}', encoding="utf-8")
    env = dict(os.environ, CLEANER_HOME=str(vault), CLEANER_THEMES=str(vault / "_themes"), CLEANER_TEST_BYE="1")
    proc = subprocess.Popen([PY, "-u", str(HERE / "app.py"), "--no-window"], env=env, stdout=subprocess.PIPE, text=True)
    url = re.search(r"http://127\.0\.0\.1:\d+/", proc.stdout.readline()).group(0)
    html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
    token = re.search(r'const TOKEN = "([^"]+)"', html).group(1)
    return proc, url, token


def post(url, token, path, page=""):
    req = urllib.request.Request(url + path.lstrip("/"), data=b"{}", method="POST",
                                 headers={"X-Token": token, "Content-Type": "application/json", **({"X-Page": page} if page else {})})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def beacon(url, token, page):
    """What the page sends as it closes: navigator.sendBeacon carries the token and page id in the address."""
    req = urllib.request.Request(f"{url}api/bye?t={token}&p={page}", data=b"{}", method="POST", headers={"Content-Type": "text/plain"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def stopped_within(proc, seconds):
    try:
        proc.wait(timeout=seconds)
        return True
    except subprocess.TimeoutExpired:
        return False


sys.path.insert(0, str(HERE))
import app  # noqa: E402

args = app.window_args("http://127.0.0.1:5555/")
profile = app.window_profile()
check("the window gets its own Chrome profile, outside the code folder",
      f"--user-data-dir={profile}" in args and HERE not in profile.parents)
check("extensions never load in the app window", "--disable-extensions" in args)
check("it still opens as an app window (no tabs)", "--app=http://127.0.0.1:5555/" in args)


class FakeServer:
    stopped = False

    def shutdown(self):
        self.stopped = True


# A covered window on a Mac can go quiet for minutes. In the app's own window that must not stop the server
# (it left a window saying "Load failed"); a browser window that goes quiet was closed, so it still stops.
app.last_ping[0] = time.time() - app.IDLE_LIMIT - 600
server = FakeServer()
app.NATIVE[0] = True
threading.Thread(target=app.watchdog, args=(server,), daemon=True).start()
time.sleep(2.5)
check("a quiet app window never stops the app under it", not server.stopped)
app.NATIVE[0] = False
time.sleep(2.5)
check("a quiet browser window still stops the app", server.stopped)

vault = HERE / f"ClientVault-window-{os.getpid()}"
try:
    proc, url, token = start(vault)
    post(url, token, "/api/ping", page="first")
    beacon(url, token, "first")
    time.sleep(1)
    urllib.request.urlopen(url, timeout=10).read()  # a reload: the page comes straight back
    post(url, token, "/api/ping", page="second")
    check("a reload cancels the goodbye: the app keeps running", not stopped_within(proc, 7))
    beacon(url, token, "first")  # the old page's goodbye arriving late, after the new page has spoken
    check("a late goodbye from an older page load is ignored", not stopped_within(proc, 7))
    beacon(url, token, "second")
    check("closing the window stops the app within seconds", stopped_within(proc, 9))
finally:
    if proc.poll() is None:
        proc.kill()
    shutil.rmtree(vault, ignore_errors=True)

print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

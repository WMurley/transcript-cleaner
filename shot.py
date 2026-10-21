"""Screenshot the app in headless Chrome with synthetic data, default and Clay looks."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / "ClientVault-shots"
THEMES = VAULT / "_themes"
CHROME = Path(os.environ["PROGRAMFILES"]) / "Google" / "Chrome" / "Application" / "chrome.exe"
OUT = HERE / "_shots"
OUT.mkdir(exist_ok=True)
env = dict(os.environ, CLEANER_HOME=str(VAULT), CLEANER_THEMES=str(THEMES))

if not VAULT.exists():  # pass 1 only, so "Needs you" has questions in it
    (VAULT / "private").mkdir(parents=True)
    for f in ("clients.csv", "companies.csv", "allow.txt"):
        shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
    THEMES.mkdir()
    shutil.copy(HERE / "test-fixtures" / "clay-design.md", THEMES / "clay.md")
    subprocess.run([sys.executable, str(HERE / "clean.py"), str(HERE / "test-calls")], env=env, capture_output=True)

views = ["calls:zoom-2026-09-14-bluefern-kickoff.txt", "review", "clients:C001", "appearance"]
for label, theme_id in (("default", ""), ("clay", "clay")):
    (THEMES / "active.json").write_text('{"active": "%s"}' % theme_id, encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-u", str(HERE / "app.py"), "--no-window"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = re.search(r"http://127\.0\.0\.1:\d+/", proc.stdout.readline()).group(0)
    time.sleep(0.5)
    for v in views:
        target = OUT / f"{label}-{v.split(':')[0]}.png"
        with tempfile.TemporaryDirectory() as prof:
            subprocess.run([str(CHROME), "--headless=new", f"--user-data-dir={prof}", "--hide-scrollbars",
                            "--force-prefers-reduced-motion", "--window-size=1320,880", "--virtual-time-budget=5000",
                            f"--screenshot={target}", f"{url}#{v}"], capture_output=True, timeout=90)
        print(target.name, target.exists())
    proc.terminate()

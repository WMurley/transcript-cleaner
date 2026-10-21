"""Smoke test for app.py against a throwaway vault, synthetic calls only. No browser."""
import json
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / "ClientVault-smoke"
if VAULT.exists():
    shutil.move(str(VAULT), str(HERE / f"_old-{VAULT.name}-{os.getpid()}"))
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)

env = dict(os.environ, CLEANER_HOME=str(VAULT), CLEANER_THEMES=str(VAULT / "_themes"))
proc = subprocess.Popen([sys.executable, "-u", str(HERE / "app.py"), "--no-window"], env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
line = proc.stdout.readline()
url = re.search(r"http://127\.0\.0\.1:\d+/", line).group(0)
ok = []


def check(label, cond):
    ok.append(cond)
    print(("PASS  " if cond else "FAIL  ") + label)


def req(path, body=None, token=None, host=None):
    r = urllib.request.Request(url.rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                               headers={"Content-Type": "application/json", **({"X-Token": token} if token else {}),
                                        **({"Host": host} if host else {})})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


try:
    time.sleep(0.5)
    status, page = req("/")
    token = re.search(rb'const TOKEN = "([^"]+)"', page).group(1).decode()
    check("page loads and carries a launch token", status == 200 and len(token) > 20)
    check("API refuses calls without the token", req("/api/state")[0] == 403)
    check("API refuses a foreign Host header (DNS-rebinding guard)", req("/api/state", token=token, host="evil.example")[0] == 403)
    files = [{"name": p.name, "text": p.read_text(encoding="utf-8")} for p in sorted((HERE / "test-calls").iterdir())]
    status, body = req("/api/upload", {"files": files}, token)
    res = json.loads(body)
    check("upload cleans two and holds three", res["summary"]["cleaned"] == 2 and res["summary"]["held"] == 3)
    review = res["state"]["review"]
    check("four questions waiting, each with context", len(review) == 4 and all(r["context"] for r in review))
    answers = {"Derek Olsen": "client", "dana": "oneoff", "mike": "C003", "Olsen Builds": "company"}
    for r in review:
        status, body = req("/api/decide", {"id": r["id"], "decision": answers[r["name"]]}, token)
    st = json.loads(body)["state"]
    check("after answering, nothing waits and all five calls are clean",
          not st["review"] and sum(c["status"] == "clean" for c in st["calls"]) == 5)
    status, body = req("/api/client", {"full_name": "Sam Ortiz", "emails": "sam@ortizco.com, s.ortiz@ortizco.com"}, token)
    r = json.loads(body)
    check("add a client from the app (gets C006, emails stored)", r["code"] == "C006" and
          any(c["code"] == "C006" and c["emails"] == "sam@ortizco.com;s.ortiz@ortizco.com" for c in r["state"]["clients"]))
    status, data = req(f"/api/export?code=C003&kind=clean&t={token}")
    check("export Mike Chen's clean calls as a zip of three", status == 200 and data[:2] == b"PK" and data.count(b".txt") >= 3)
    status, body = req("/api/call?file=fathom-2026-09-22-harbor-lane.txt&kind=clean", token=token)
    check("clean preview has codes, no names", b"C005" in body and b"Derek" not in body)
    status, data = req(f"/api/download?file=fathom-2026-09-22-harbor-lane.txt&kind=clean&t={token}")
    check("download a clean call as Markdown", status == 200 and b"C005" in data and b"Derek" not in data)
    check("downloads refuse paths outside the vault",
          req(f"/api/download?file=..%2F..%2Fapp.py&kind=clean&t={token}")[0] == 404)
    check("default look: theme.css is empty", req("/theme.css")[1] == b"")
    md = (HERE / "test-fixtures" / "clay-design.md").read_text(encoding="utf-8")
    status, body = req("/api/theme", {"text": md}, token)
    css = req("/theme.css")[1].decode()
    check("drop the Clay design.md: app now uses its terracotta and cream",
          status == 200 and json.loads(body)["name"] == "Clay" and "#b05a36" in css and "#fef9ef" in css)
    evil = md.replace("- accent: #b05a36", "- accent: #b05a36;}</style><script>alert(1)</script>").replace(
        "'Inter'", "'x;}body{display:none'")
    req("/api/theme", {"text": evil.replace("# Clay", "# Evil")}, token)
    css2 = req("/theme.css")[1].decode()
    check("a malicious design.md can't inject code or hide the page",
          "<" not in css2 and "display:none" not in css2 and "alert" not in css2)
    status, body = req("/api/theme", {"text": "# Not a design\nhello"}, token)
    check("a file with no colours is refused with a plain reason", status == 400)
    status, body = req("/api/theme", {"use": ""}, token)
    check("back to the default look", status == 200 and req("/theme.css")[1] == b"")
finally:
    proc.terminate()
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

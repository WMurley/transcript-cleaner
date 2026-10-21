"""Fathom pull against a stand-in Fathom server on this computer (synthetic meetings only).

Also proves the key round-trips through the computer's password store, under a TEST entry
that is removed at the end. Never contacts the real Fathom.
"""
import http.server
import json
import os
import shutil
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-fathom-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
os.environ["FATHOM_KEY_TARGET"] = "TranscriptCleaner/Fathom-TEST"
GOOD_KEY = "test-key-1234567890"

MEETINGS = [
    {"recording_id": 111, "title": "Bluefern kickoff with Jane Whitfield", "created_at": "2026-09-30T15:00:00Z",
     "recording_start_time": "2026-09-30T15:00:00Z",
     "calendar_invitees": [{"name": "Jane Whitfield", "email": "jane@bluefernbakery.com", "is_external": True}],
     "transcript": [{"speaker": {"display_name": "Morgan Reyes"}, "text": "Hi Jane, how is the van schedule?", "timestamp": "00:00:04"},
                    {"speaker": {"display_name": "Jane Whitfield"}, "text": "Much better. Call me on (555) 214-8890 if it slips.", "timestamp": "00:00:09"}]},
    {"recording_id": 222, "title": "Northgate check-in", "created_at": "2026-10-01T16:00:00Z",
     "recording_start_time": "2026-10-01T16:00:00Z", "calendar_invitees": [],
     "transcript": [{"speaker": {"display_name": "Priya Nair"}, "text": "Reminders are live.", "timestamp": "00:00:02"}]},
    {"recording_id": 333, "title": "No transcript yet", "created_at": "2026-10-02T09:00:00Z", "transcript": None},
]


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.headers.get("X-Api-Key") != GOOD_KEY:
            self.send_response(401)
            self.end_headers()
            return
        page2 = "cursor=p2" in self.path
        body = {"items": MEETINGS[2:] if page2 else MEETINGS[:2], "next_cursor": None if page2 else "p2", "limit": 2}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["FATHOM_API_BASE"] = f"http://127.0.0.1:{srv.server_address[1]}"

sys.path.insert(0, str(HERE))
import clean  # noqa: E402
import fathom  # noqa: E402

ok = []


def check(label, cond):
    ok.append(cond)
    print(("PASS  " if cond else "FAIL  ") + label)


try:
    fathom.clear_key()
    check("no key yet", not fathom.has_key())
    try:
        fathom.set_key("not a key")
        check("a malformed key is refused", False)
    except ValueError:
        check("a malformed key is refused", True)
    fathom.set_key("wrong-key-0987654321")
    try:
        fathom.pull()
        check("a key Fathom rejects gives a plain message", False)
    except fathom.FathomError as e:
        check("a key Fathom rejects gives a plain message", "didn't accept the key" in str(e))
    fathom.set_key(GOOD_KEY)
    check("the key is stored in the computer's password store and read back", fathom.has_key())
    got, newest = fathom.pull()
    names = [n for n, _ in got]
    check("both pages pulled; the meeting with no transcript is skipped", len(got) == 2 and newest == "2026-10-02T09:00:00Z")
    check("pulled calls get neutral file names (no client in the title)",
          names == ["fathom-2026-09-30-111.txt", "fathom-2026-10-01-222.txt"])
    check("transcript arrives as plain timestamped lines with invitees",
          "[00:00:09] Jane Whitfield: Much better." in got[0][1] and "Invitees: Jane Whitfield <jane@bluefernbakery.com>" in got[0][1])
    s = clean.run(texts=got)
    con = clean.connect()
    c = clean.clean_path(con, "fathom-2026-09-30-111.txt").read_text(encoding="utf-8")
    con.close()
    check("pulled calls are cleaned like any other (title, invitee, speaker, phone)",
          s["cleaned"] == 2 and "Jane" not in c and "Bluefern" not in c and "214-8890" not in c and "C001-EMAIL" in c)
    again, _ = fathom.pull(since=newest, known=frozenset(names))
    check("pulling again skips calls already in the app", again == [])
finally:
    fathom.clear_key()
    print("test key removed:", not fathom.has_key())
    srv.shutdown()
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

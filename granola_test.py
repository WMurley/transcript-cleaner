"""Granola pull against a stand-in Granola server on this computer (synthetic notes only).

Follows Granola's public API as documented at docs.granola.ai (Bearer grn_ keys, /v1/notes with
hasMore/cursor, include=transcript, 413 TRANSCRIPT_TOO_LARGE with a paged /transcript endpoint).
The key round-trips through the computer's password store under a TEST entry removed at the end.
Never contacts the real Granola.
"""
import http.server
import json
import os
import shutil
import sys
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-granola-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
os.environ["GRANOLA_KEY_TARGET"] = "TranscriptCleaner/Granola-TEST"
os.environ["GRANOLA_PAUSE"] = "0"
GOOD_KEY = "grn_test1234567890abcdef"

SHORT = "not_aaaaaaaaaaaaa1"
LONG = "not_bbbbbbbbbbbbb2"
NOTES = {
    SHORT: {"id": SHORT, "object": "note", "title": "Bluefern kickoff with Jane Whitfield", "owner": {"name": "Morgan Reyes", "email": "morgan@example.com"},
            "created_at": "2026-09-30T15:00:00Z", "updated_at": "2026-09-30T16:00:00Z", "deleted_at": None,
            "calendar_event": {"event_title": "Bluefern kickoff", "invitees": [{"email": "jane@bluefernbakery.com"}],
                               "scheduled_start_time": "2026-09-30T15:00:00Z"},
            "attendees": [{"name": "Jane Whitfield", "email": "jane@bluefernbakery.com"}],
            "transcript": [
                {"speaker": {"source": "microphone", "attribution": "me"}, "text": "Hi Jane, how is the van schedule?",
                 "start_time": "2026-09-30T15:00:04Z", "end_time": "2026-09-30T15:00:07Z"},
                {"speaker": {"source": "speaker", "attribution": "them", "name": "Jane Whitfield"},
                 "text": "Much better. Call me on (555) 214-8890 if it slips.", "start_time": "2026-09-30T15:00:09Z",
                 "end_time": "2026-09-30T15:00:12Z"}]},
    LONG: {"id": LONG, "object": "note", "title": "Northgate check-in", "owner": {"name": "Morgan Reyes", "email": "morgan@example.com"},
           "created_at": "2026-10-01T16:00:00Z", "updated_at": "2026-10-01T17:00:00Z", "deleted_at": None,
           "calendar_event": None, "attendees": [],
           "transcript": [{"speaker": {"source": "speaker", "attribution": "them", "diarization_label": "Speaker B"},
                           "text": f"Line {i}.", "start_time": f"2026-10-01T16:00:{i:02d}Z", "end_time": f"2026-10-01T16:00:{i:02d}Z"}
                          for i in range(5)]},
}
REQUESTS = []


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body=None):
        data = json.dumps(body or {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        REQUESTS.append(self.path)
        if self.headers.get("Authorization") != f"Bearer {GOOD_KEY}":
            return self.reply(401, {"error": "unauthorized"})
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        parts = url.path.strip("/").split("/")  # v1 / notes / {id} / transcript
        summary = lambda n: {k: v for k, v in n.items() if k in ("id", "object", "title", "owner", "created_at", "updated_at", "deleted_at")}
        if parts == ["v1", "notes"]:
            page2 = q.get("cursor") == ["p2"]
            notes = [summary(NOTES[LONG])] if page2 else [summary(NOTES[SHORT])]
            return self.reply(200, {"notes": notes, "hasMore": not page2, "cursor": None if page2 else "p2"})
        if len(parts) == 3 and parts[:2] == ["v1", "notes"] and parts[2] in NOTES:
            note = dict(NOTES[parts[2]])
            if q.get("include") == ["transcript"]:
                if parts[2] == LONG:
                    return self.reply(413, {"error": "TRANSCRIPT_TOO_LARGE"})
            else:
                note["transcript"] = None
            return self.reply(200, note)
        if len(parts) == 4 and parts[3] == "transcript" and parts[2] in NOTES:
            lines = NOTES[parts[2]]["transcript"]
            start = int((q.get("cursor") or ["0"])[0])
            size = 2
            nxt = start + size
            return self.reply(200, {"transcript": lines[start:nxt], "hasMore": nxt < len(lines), "cursor": str(nxt) if nxt < len(lines) else None})
        return self.reply(404, {"error": "not found"})


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["GRANOLA_API_BASE"] = f"http://127.0.0.1:{srv.server_address[1]}/v1"

sys.path.insert(0, str(HERE))
import clean  # noqa: E402
import granola  # noqa: E402

ok = []


def check(label, cond):
    ok.append(cond)
    print(("PASS  " if cond else "FAIL  ") + label)


try:
    granola.clear_key()
    check("no key yet", not granola.has_key())
    for bad in ("not a key", "fathom-style-key-1234567890"):
        try:
            granola.set_key(bad)
            check(f"a key without grn_ is refused ({bad})", False)
        except ValueError:
            check(f"a key without grn_ is refused ({bad})", True)
    granola.set_key("grn_wrongkey0987654321")
    try:
        granola.list_calls(limit=0)
        check("a key Granola rejects gives a plain message", False)
    except granola.GranolaError as e:
        check("a key Granola rejects gives a plain message", "didn't accept the key" in str(e))
    granola.set_key(GOOD_KEY)
    check("the key is stored in the computer's password store and read back", granola.has_key())
    calls, more = granola.list_calls(after="2026-09-01T00:00:00Z", limit=0)
    check("both pages listed, newest first, nothing more to fetch",
          [c["id"] for c in calls] == [LONG, SHORT] and not more)
    check("the list carries no transcripts (it only fetches what you tick)", not any("transcript" in r for r in REQUESTS))
    check("listing uses Bearer auth and Granola's created_after filter", any("created_after=2026-09-01" in r for r in REQUESTS))
    got = [granola.fetch(c["meta"]) for c in calls]
    names = [n for n, _ in got]
    check("pulled notes get neutral file names (no client in the title)",
          sorted(names) == ["granola-2026-09-30-aaaaaaaaaaaaa1.txt", "granola-2026-10-01-bbbbbbbbbbbbb2.txt"])
    short = dict(got)["granola-2026-09-30-aaaaaaaaaaaaa1.txt"]
    long_ = dict(got)["granola-2026-10-01-bbbbbbbbbbbbb2.txt"]
    check("transcript arrives as plain timestamped lines with attendees",
          "[00:00:05] Jane Whitfield: Much better." in short and "Attendees: Jane Whitfield <jane@bluefernbakery.com>" in short)
    check("the note-taker's own lines use their name (so it can be kept or hidden like any name)",
          "[00:00:00] Morgan Reyes: Hi Jane" in short)
    check("a transcript too large to send inline is fetched in pages, all lines kept",
          all(f"Speaker B: Line {i}." in long_ for i in range(5)) and sum("/transcript" in r for r in REQUESTS) == 3)
    s = clean.run(texts=got)
    con = clean.connect()
    c = clean.clean_path(con, "granola-2026-09-30-aaaaaaaaaaaaa1.txt").read_text(encoding="utf-8")
    con.close()
    check("pulled notes are cleaned like any other (title, attendee, speaker, phone)",
          s["cleaned"] >= 1 and "Jane" not in c and "Bluefern" not in c and "214-8890" not in c)
    try:
        granola.fetch({"id": "../../etc"})
        check("only real Granola note ids are fetched", False)
    except granola.GranolaError:
        check("only real Granola note ids are fetched", True)
finally:
    granola.clear_key()
    print("test key removed:", not granola.has_key())
    srv.shutdown()
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

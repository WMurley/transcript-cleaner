"""Transcript Cleaner app: a small local server plus a Chrome app window.

Only Python's built-in modules plus the cleaning engine (clean.py). The
server listens on 127.0.0.1 only, checks the Host header, and requires a
per-launch token on every API call, so other machines and websites cannot
talk to it. It shuts itself down a couple of minutes after the window closes.
"""

import http.server
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import clean
import fathom
import granola
import intake
import restore
import team
import theme
import identities
import decisions
import updater
import comparison
import uuid

HERE = Path(__file__).resolve().parent  # the app's own files (this folder)
ROOT = HERE.parent  # the install folder: Python (.venv), your look and logo, practice data, the Mac app
TOKEN = secrets.token_urlsafe(24)
REAL_HOME = clean.HOME
# meeting apps the member can pull from; each keeps the details of its last list, so a pull fetches only what was ticked
SOURCES = {"fathom": (fathom, "Fathom", fathom.FathomError), "granola": (granola, "Granola", granola.GranolaError)}
PICKS = {name: {} for name in SOURCES}
PRACTICE_HOME = ROOT / "_practice"
TUTORIAL_SESSION = None
TUTORIAL_CALL = 'guided-first-call.txt'
TUTORIAL_SAMPLE = ('Morgan Reyes: Thanks for joining.\n'
                   'Derek Olsen: The team at Bluefern Bakery approved the scope. '
                   'Bluefern will send the notes. Email derek@bluefern.example or call 459-928-8815.\n'
                   'Morgan Reyes: We will review the clean copy before sharing it.\n')
IDLE_LIMIT = 120  # seconds without a heartbeat before the server exits
BYE_GRACE = 4  # after the window says goodbye, seconds to wait for a reload before stopping
state_lock = threading.Lock()
last_ping = [time.time()]
last_request = [time.time()]  # any request at all, so a page reload cancels a goodbye
bye_at = [0.0]
bye_page = [""]  # the page that said goodbye
current_page = [""]  # the newest page load that has talked to the server
WINDOWED = False  # only an app the user opened stops itself when its window closes (tests run with --no-window)
NATIVE = [False]  # in the app's own window: closing it stops the app, so a quiet window never does
MAC_APP = False  # opened in its own Mac window: the Finder icon follows Appearance (never during tests)


PORT = 0
ALLOWED_HOSTS = set()


class LocalServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def terms_of(*values):
    """Names, emails and phones a change touches, for re-checking only the calls that mention them."""
    out = []
    for v in values:
        if isinstance(v, (list, tuple)):
            out += terms_of(*v)
        elif v:
            out += [x.strip() for x in re.split(r"[;,\n]", str(v)) if x.strip()]
    return out


def display_name(name):
    """Same as the page's displayName: an all-lowercase name gets capitals, anything else stays as written."""
    return re.sub(r"(^|[\s'-])(\w)", lambda m: m.group(1) + m.group(2).upper(), name) if name == name.lower() else name


def record_name(con, code):
    row = con.execute("SELECT full_name AS n FROM clients WHERE code=? UNION ALL SELECT names AS n FROM companies WHERE code=?",
                      (code, code)).fetchone() if code else None
    return clean.split(row["n"])[0] if row and clean.split(row["n"]) else ""


def decision_label(con, action, name, code=None):
    """One plain sentence per decision, shown in the Undo pop-up and on Recent decisions."""
    who = record_name(con, code)
    return {
        "keep": f"{name} shows in every call",
        "tool": f"{name} is an AI tool and shows in every call",
        "hide_always": f"{name} is hidden in every call",
        "hide_call": f"{name} is hidden in this call",
        "link_call": f"{name} in this call is {who} ({code})" if who else f"{name} in this call is {code}",
        "which": f"{name} is {who} ({code})" if who else f"{name} is someone else, kept hidden",
    }.get(action, name)


def record_terms(con, code):
    """Everything a saved client or company currently goes by (before an edit changes it)."""
    if not code:
        return []
    row = con.execute("SELECT full_name, aliases, emails, phones FROM clients WHERE code=?", (code,)).fetchone()
    if row:
        return terms_of(row["full_name"], row["aliases"], row["emails"], row["phones"])
    row = con.execute("SELECT names FROM companies WHERE code=?", (code,)).fetchone()
    return terms_of(row["names"]) if row else []


def norm_list(value):
    return ";".join(v.strip() for v in re.split(r"[;,\n]", value or "") if v.strip())


def original_text(file, cache=None):
    """A call's original, wherever it is now (held, cleaned or waiting). Read once per state build."""
    if cache is not None and file in cache:
        return cache[file]
    p = next((d / file for d in (clean.HELD, clean.RAW, clean.DIRTY) if (d / file).exists()), None)
    text = clean.read_text(p) if p else ""
    if cache is not None:
        cache[file] = text
    return text


def snippet(file, name, cache=None):
    """A short piece of the original transcript around the name, so the owner can decide."""
    t = original_text(file, cache)
    if not t:
        return ""
    m = re.search(clean.word_re(name), t, flags=re.IGNORECASE)
    if not m:
        return ""
    a, b = max(0, m.start() - 110), min(len(t), m.end() + 110)
    return ("..." if a else "") + t[a:b].replace("\n", " ") + ("..." if b < len(t) else "")


TIME_ONLY = re.compile(r"^\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*-->\s*\S+.*$")
TIME_LEAD = re.compile(r"^\s*\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+")
SPEAKER = re.compile(r"^([A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,3}):\s+")


def _clip(text, start, end, room=240):
    """Cut a long line around [start, end) at word boundaries."""
    if len(text) <= room:
        return text
    a = max(0, start - (room - (end - start)) // 2)
    b = min(len(text), a + room)
    a = max(0, b - room)
    space = text.find(" ", a)
    if a and 0 <= space < start:
        a = space + 1
    space = text.rfind(" ", a, b)
    if b < len(text) and space >= end:
        b = space
    return ("..." if a else "") + text[a:b].strip() + ("..." if b < len(text) else "")


def transcript_lines(text):
    """A transcript as lines of time, speaker and words."""
    lines, time = [], ""
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().upper() == "WEBVTT" or raw.strip().isdigit():
            continue
        cue = TIME_ONLY.match(raw)
        if cue:  # a caption timing line belongs to the line after it
            time = cue.group(1).split(".")[0].split(",")[0]
            continue
        text, stamp = raw.strip(), time
        lead = TIME_LEAD.match(text)
        if lead:
            stamp, text = lead.group(1), text[lead.end():]
        speaker = SPEAKER.match(text)
        who = speaker.group(1) if speaker else ""
        if speaker:
            text = text[speaker.end():]
        lines.append({"time": stamp, "speaker": who, "text": text})
        time = ""
    return lines


def excerpt(file, name, before=1, after=1, cache=None):
    """The transcript lines around the first mention, split into time, speaker and words, plus how often it is mentioned."""
    key = ("lines", file)
    if cache is not None and key in cache:
        lines = cache[key]
    else:
        lines = transcript_lines(original_text(file, cache))
        if cache is not None:
            cache[key] = lines
    if not lines:
        return {"lines": [], "mentions": 0}
    pattern = re.compile(clean.word_re(name), re.IGNORECASE)
    mentions = sum(len(pattern.findall(l["speaker"] + " " + l["text"])) for l in lines)
    at = next((i for i, l in enumerate(lines) if pattern.search(l["text"]) or pattern.search(l["speaker"])), None)
    if at is None:
        return {"lines": [], "mentions": mentions}
    out = []
    for i in range(max(0, at - before), min(len(lines), at + after + 1)):
        line = dict(lines[i], hit=i == at)
        m = pattern.search(line["text"])
        line["text"] = _clip(line["text"], *(m.span() if m else (0, 0)), room=320 if i == at else 180)
        out.append(line)
    return {"lines": out, "mentions": mentions}


def get_state():
    clean.init()
    con = clean.connect()
    calls = [dict(r) for r in con.execute("SELECT * FROM calls ORDER BY updated DESC, file")]
    for call in calls:
        call["export_approved"] = clean.export_approved(con, call["file"]) if call["status"] == "clean" else False
    clients = [dict(r) for r in con.execute("SELECT * FROM clients ORDER BY code")]
    companies = [dict(r) for r in con.execute("SELECT * FROM companies ORDER BY code")]
    for c in clients + companies:
        c["calls"] = sum(1 for k in calls if f",{c['code']}," in (k["codes"] or ""))
    for co in companies:
        co["people"] = sum(1 for c in clients if c["company_code"] == co["code"])
    # names still to look at; ones marked "keep hidden" stay hidden and leave the list
    review = [dict(r) for r in con.execute("SELECT * FROM review WHERE reviewed=0 ORDER BY file, speaker DESC, mentions DESC, name")]
    suggested_people = intake.pending(con)
    con.commit()
    cache = {}
    for r in review:
        r["context"] = snippet(r["file"], r["name"], cache)
        r["excerpt"] = excerpt(r["file"], r["name"], cache=cache)
        r["excerpt_more"] = excerpt(r["file"], r["name"], 4, 4, cache=cache)
        r["suggestions"] = identities.suggestions(con, r, original_text(r["file"], cache))
    data = {
        "calls": calls, "clients": clients, "companies": companies, "review": review,
        "decisions": decisions.recent(con),
        "version": updater.local_version(ROOT), "developer_copy": updater.is_developer_copy(ROOT),
        "next_codes": {"person": clean.next_code(con, "C"), "company": clean.next_code(con, "O")},
        "suggested_people": suggested_people,
        "allow": clean.get_list(con, "allow"),
        "home": str(clean.HOME), "onedrive": "onedrive" in str(clean.HOME).lower(),
        "waiting_files": len([f for f in clean.DIRTY.iterdir() if f.is_file()]) if clean.DIRTY.exists() else 0,
        "themes": theme.themes(), "theme": theme.active_id(), "mode": theme.mode(), "brand": theme.brand(),
        "practice": clean.PRACTICE or TUTORIAL_SESSION is not None, "tour_done": theme.tour_done(),
        "tutorial": tutorial_state(con), "sample": TUTORIAL_SAMPLE,
        "output_dir": clean.get_setting(con, "output_dir"), "output_ok": clean.output_dir(con) is not None,
        "review_before_export": clean.needs_export_review(con),
        "answers": clean.answers(con), "hide": clean.hide_settings(con),
        "hold_unknown": clean.hold_unknown(con), "owner_name": clean.get_setting(con, "owner_name"),
        "tools": clean.get_list(con, "tools"),
        "team": clean.get_list(con, "team"),
        "fathom": {"has_key": TUTORIAL_SESSION['fathom_connected'] if TUTORIAL_SESSION else fathom.has_key(), "last_pull": clean.get_setting(con, "fathom_pulled_at")},
        "granola": {"has_key": False if TUTORIAL_SESSION else granola.has_key(), "last_pull": clean.get_setting(con, "granola_pulled_at")},
    }
    con.close()
    return data


def tutorial_state(con):
    if TUTORIAL_SESSION is None:
        return {'active': False}
    row = con.execute('SELECT clean_name,status FROM calls WHERE file=?', (TUTORIAL_CALL,)).fetchone()
    exported = bool(row and row['status'] == 'clean' and row['clean_name'] and (TUTORIAL_SESSION['exports'] / row['clean_name']).is_file())
    return {'active': True, 'call': TUTORIAL_CALL, 'sample': TUTORIAL_SAMPLE,
            'step': TUTORIAL_SESSION['step'], 'reviewed': TUTORIAL_SESSION['reviewed'],
            'folder_opened': TUTORIAL_SESSION['folder_opened'], 'exported': exported}


def start_tutorial():
    global TUTORIAL_SESSION
    if TUTORIAL_SESSION is not None:
        return
    suffix = uuid.uuid4().hex
    home, exports = ROOT / f'_tutorial-{suffix}', ROOT / f'_tutorial-exports-{suffix}'
    previous_home, previous_practice = clean.HOME, clean.PRACTICE
    fathom_connected = fathom.has_key()
    try:
        exports.mkdir()
        clean.set_home(home, practice=False)
        clean.init()
        con = clean.connect()
        try:
            with con:
                clean.add_to_list(con, 'allow', 'Morgan Reyes')
                clean.set_setting(con, 'output_dir', str(exports))
                clean.set_setting(con, 'review_before_export', '1')
        finally:
            con.close()
    except Exception:
        clean.set_home(previous_home, practice=previous_practice)
        raise
    TUTORIAL_SESSION = {'return_home':previous_home, 'return_practice':previous_practice,
                        'home':home, 'exports':exports, 'step':0, 'reviewed':False, 'folder_opened':False,
                        'fathom_connected':fathom_connected}


def end_tutorial():
    global TUTORIAL_SESSION
    if TUTORIAL_SESSION:
        previous = TUTORIAL_SESSION
        clean.set_home(previous['return_home'], practice=previous['return_practice'])
        TUTORIAL_SESSION = None
        # The tutorial only ever holds the built-in sample, so its folders go when it ends.
        shutil.rmtree(previous['home'], ignore_errors=True)
        shutil.rmtree(previous['exports'], ignore_errors=True)


def prune_tutorial_folders(max_age=6 * 3600):
    """Remove sample folders left by a tutorial that was closed partway through.
    Only folders older than max_age, so a second open copy of the app keeps its live tutorial."""
    cutoff = time.time() - max_age
    for folder in ROOT.glob('_tutorial-*'):
        if folder.is_dir() and re.fullmatch(r'_tutorial-(exports-)?[0-9a-f]{32}', folder.name) and folder.stat().st_mtime < cutoff:
            shutil.rmtree(folder, ignore_errors=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the console quiet; never log request contents

    # ---- guards
    def guard(self, need_token=True):
        last_request[0] = time.time()
        if self.headers.get("X-Page") and self.headers.get("X-Page") != current_page[0] and self.headers.get("Host") in ALLOWED_HOSTS:
            if not self.path.startswith("/api/bye"):
                current_page[0] = self.headers["X-Page"]
        if self.headers.get("Host") not in ALLOWED_HOSTS:
            self.send_error(403)
            return False
        if need_token:
            q = parse_qs(urlparse(self.path).query)
            if self.headers.get("X-Token") != TOKEN and q.get("t", [""])[0] != TOKEN:
                self.send_error(403)
                return False
        return True

    def send(self, code, body, ctype="application/json", extra=None):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if not isinstance(body, bytes) else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    # ---- GET
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            if not self.guard(need_token=False):
                return
            html = (HERE / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", TOKEN)
            return self.send(200, html, "text/html",
                             {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                                         "script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:"})
        if url.path == "/favicon.ico":
            if not self.guard(need_token=False):
                return
            return self.send(200, current_icon().read_bytes(), "image/x-icon")
        if url.path == "/logo.png":
            if not self.guard(need_token=False):
                return
            if not theme.LOGO.exists():
                return self.send_error(404)
            return self.send(200, theme.LOGO.read_bytes(), "image/png")
        if url.path == "/theme.css":
            if not self.guard(need_token=False):
                return
            return self.send(200, theme.active_css(), "text/css")
        if url.path == '/tutorial.js':
            if not self.guard(need_token=False):
                return
            return self.send(200, (HERE / 'tutorial.js').read_bytes(), 'text/javascript; charset=utf-8')
        if not self.guard():
            return
        q = parse_qs(url.query)
        if url.path == "/api/download":
            name = Path(q.get("file", [""])[0]).name
            kind = q.get("kind", ["clean"])[0]
            folder = {"clean": clean.CLEAN, "raw": clean.RAW, "held": clean.HELD}.get(kind)
            p = None
            if folder and name:
                if kind == "clean":
                    con = clean.connect()
                    p = clean.clean_path(con, name)
                    con.close()
                else:
                    p = folder / name
            if not p or not p.exists():
                return self.send_error(404)
            out = (p.stem + ".md") if kind == "clean" else (Path(name).stem + "-original.md")
            return self.send(200, clean.read_text(p).encode("utf-8"), "text/markdown; charset=utf-8",
                             {"Content-Disposition": f'attachment; filename="{out}"'})
        if url.path == "/api/state":
            with state_lock:
                return self.send(200, get_state())
        if url.path == "/api/call":
            name = Path(q.get("file", [""])[0]).name
            kind = q.get("kind", ["clean"])[0]
            folder = {"clean": clean.CLEAN, "raw": clean.RAW, "held": clean.HELD}.get(kind)
            p = folder / name if folder else None
            if kind == "clean" and name:
                con = clean.connect()
                p = clean.clean_path(con, name)
                con.close()
            return self.send(200, {"text": clean.read_text(p) if p and p.exists() else ""})
        if url.path == "/api/final-check":
            name = q.get('file', [''])[0]
            if not name or name != clean.safe_name(name):
                return self.send(400, {'error': 'Choose a call in this app.'})
            with state_lock:
                con = clean.connect()
                try:
                    row = con.execute('SELECT status FROM calls WHERE file=?', (name,)).fetchone()
                    if not row or row['status'] != 'clean':
                        return self.send(200, {'items': []})
                    return self.send(200, {'items': clean.final_check(con, name)})
                finally:
                    con.close()
        if url.path == "/api/compare":
            name = q.get('file', [''])[0]
            if not name or name != clean.safe_name(name):
                return self.send(400, {'error': 'Choose a call in this app.'})
            with state_lock:
                con = clean.connect()
                try:
                    row = con.execute('SELECT status FROM calls WHERE file=?', (name,)).fetchone()
                    src, dst = clean.RAW / name, clean.clean_path(con, name)
                    if not row or row['status'] != 'clean' or not src.exists() or not dst.exists():
                        return self.send(409, {'error': "Resolve this call's questions before comparing its copies."})
                    return self.send(200, comparison.compare(clean.read_text(src), clean.read_text(dst)))
                finally:
                    con.close()
        if url.path == "/api/export":
            code = q.get("code", [""])[0].upper()
            kind = q.get("kind", ["clean"])[0]
            if not re.fullmatch(r"[CO]\d{3}", code) or kind not in ("clean", "raw"):
                return self.send_error(400)
            con = clean.connect()
            rows = con.execute("SELECT file, clean_name FROM calls WHERE codes LIKE ?", (f"%,{code},%",)).fetchall()
            files = [(r["file"], r["clean_name"] or r["file"]) for r in rows]
            con.close()
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f, cname in files:
                    p = clean.CLEAN / cname if kind == "clean" else clean.RAW / f
                    if p.exists():
                        z.write(p, p.name)
            label = "clean" if kind == "clean" else "originals"
            return self.send(200, buf.getvalue(), "application/zip",
                             {"Content-Disposition": f'attachment; filename="{code}-{label}.zip"'})
        self.send_error(404)

    # ---- POST
    def do_POST(self):
        try:
            self.handle_post()
        except (ValueError, OSError) as e:
            self.send(400, {"error": str(e)})

    def handle_post(self):
        if not self.guard():
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > 200 * 1024 * 1024:
            return self.send_error(413)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send_error(400)
        path = urlparse(self.path).path
        last_ping[0] = time.time()
        if path == "/api/ping":
            return self.send(200, {"ok": True})
        if path == "/api/bye":  # the window is closing; stop soon unless it was only a reload
            if (self.headers.get("X-Page") or parse_qs(urlparse(self.path).query).get("p", [""])[0]) in ("", current_page[0]):  # an older page's late goodbye is ignored
                bye_page[0] = self.headers.get("X-Page") or parse_qs(urlparse(self.path).query).get("p", [""])[0]
                bye_at[0] = time.time()
            return self.send(200, {"ok": True})
        summary = None
        with state_lock:
            if path == "/api/upload":
                texts = [(f.get("name", ""), f.get("text", "")) for f in body.get("files", [])]
                before = {c["file"] for c in get_state()["calls"]}
                summary = clean.run(texts=texts)
                state = get_state()
                added = [c["file"] for c in state["calls"] if c["file"] not in before]
                return self.send(200, {"summary": summary, "state": state, "added_files": added})
            elif path == "/api/run":
                summary = clean.run()
            elif path == "/api/reclean":
                summary = clean.reclean_all()
            elif path == "/api/decide":
                con = clean.connect()
                try:
                    row = con.execute("SELECT name FROM review WHERE id=?", (int(body["id"]),)).fetchone()
                    clean.set_decision(con, int(body["id"]), str(body["decision"]))
                    con.commit()
                finally:
                    con.close()
                summary = clean.reclean_all([row["name"]]) if row else clean.run()  # see /api/decide-group
            elif path == "/api/identity":
                con = clean.connect()
                try:
                    with con:
                        ids = [int(i) for i in (body.get("review_ids") or [body.get("review_id")]) if str(i).isdigit()]
                        touched = terms_of(body.get("detected"), body.get("full_name"), body.get("aliases"), body.get("emails"),
                                           body.get("phones"), body.get("names"), body.get("company_names"))
                        touched += record_terms(con, body.get("code")) + record_terms(con, body.get("company_code"))
                        touched += [r["name"] for r in con.execute(f"SELECT name FROM review WHERE id IN ({','.join('?' * len(ids))})", ids)] if ids else []
                        action = body.get("action", "new")
                        logged = action in ("keep", "tool", "hide_always", "hide_call", "link_call")  # new clients go through Clients instead
                        before = decisions.start(con) if logged else None
                        code = identities.save_group(con, body) if body.get('review_ids') else identities.save(con, body)
                        undo = None
                        if logged:
                            name = display_name(str(body.get("detected") or (touched[-1] if touched else "")))
                            file = str(body.get("file") or "") if action in ("hide_call", "link_call") else ""
                            label = decision_label(con, action, name, body.get("code"))
                            undo = {"id": decisions.record(con, before, action, label, file), "label": label}
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                finally:
                    con.close()
                summary = clean.reclean_all(touched)
                return self.send(200, {"code": code, "summary": summary, "state": get_state(), "undo": undo})
            elif path == "/api/decide-group":
                con = clean.connect()
                try:
                    with con:
                        before = decisions.start(con)  # the answer lands when the run applies it, so it is logged after
                        rows = identities.group_rows(con, body.get('ids'))
                        if any(r['kind'] != 'ambiguous' for r in rows) or str(body.get('decision')) not in rows[0]['candidates'].split(' or ') + ['person']:
                            raise ValueError('Choose a listed answer for these first-name questions.')
                        for row in rows:
                            clean.set_decision(con, row['id'], str(body['decision']))
                        files = {r['file'] for r in rows}
                        name, code = display_name(rows[0]['name']), (str(body['decision']) if body['decision'] != 'person' else None)
                finally:
                    con.close()
                # re-check every call saying the name: with names hidden by default those calls are already
                # clean, not held, so a plain run would save the answer without updating their clean copies
                summary = clean.reclean_all([rows[0]['name']])
                con = clean.connect()
                try:
                    with con:
                        label = decision_label(con, "which", name, code)
                        undo = {"id": decisions.record(con, before, "which", label, files.pop() if len(files) == 1 else "", [name]), "label": label}
                finally:
                    con.close()
                return self.send(200, {'summary': summary, 'state': get_state(), 'undo': undo})
            elif path == "/api/merge":
                con = clean.connect()
                try:
                    with con:
                        identities.merge(con, str(body.get("keep", "")), str(body.get("remove", "")))
                finally:
                    con.close()
                summary = clean.reclean_all()
            elif path == "/api/client":
                con = clean.connect()
                before = record_terms(con, body.get("code", ""))  # an edit can rename: re-check calls with the old names too
                fields = dict(full_name=body.get("full_name", "").strip(), aliases=norm_list(body.get("aliases")),
                              company_code=body.get("company_code", ""), emails=norm_list(body.get("emails")),
                              phones=norm_list(body.get("phones")), notes=body.get("notes", ""))
                if not fields["full_name"]:
                    con.close()
                    return self.send(400, {"error": "A client needs a name."})
                if fields["company_code"] and not con.execute("SELECT 1 FROM companies WHERE code=?", (fields["company_code"],)).fetchone():
                    con.close()
                    return self.send(400, {"error": "Choose a company from the list."})
                if identities.duplicate(con, "person", fields["full_name"], body.get("code", "")) and not body.get("distinct"):
                    con.close()
                    return self.send(409, {"error": "This person already exists. Open their record, or confirm this is a different person with the same name."})
                if body.get("company_names", "").strip():
                    value = identities.names(body["company_names"])
                    matches = identities.duplicate(con, "company", value)
                    if len(matches) > 1:
                        con.close()
                        return self.send(400, {"error": "Several companies match. Choose the existing company from the list."})
                    fields["company_code"] = matches[0]["code"] if matches else clean.add_company(con, value)
                if body.get("code"):
                    con.execute("UPDATE clients SET full_name=:full_name, aliases=:aliases, company_code=:company_code, "
                                "emails=:emails, phones=:phones, notes=:notes WHERE code=:code",
                                dict(fields, code=body["code"]))
                    code = body["code"]
                else:
                    code = clean.add_client(con, **fields)
                con.commit()
                con.close()
                summary = clean.reclean_all(before + terms_of(fields["full_name"], fields["aliases"], fields["emails"],
                                                              fields["phones"], body.get("company_names")))
                return self.send(200, {"code": code, "summary": summary, "state": get_state()})
            elif path == "/api/company":
                con = clean.connect()
                before = record_terms(con, body.get("code", ""))
                names = norm_list(body.get("names"))
                if not names:
                    con.close()
                    return self.send(400, {"error": "A company needs a name."})
                if identities.duplicate(con, "company", names, body.get("code", "")) and not body.get("distinct"):
                    con.close()
                    return self.send(409, {"error": "This company already exists. Open its record, or confirm this is a separate company."})
                if body.get("code"):
                    con.execute("UPDATE companies SET names=? WHERE code=?", (names, body["code"]))
                    code = body["code"]
                else:
                    code = clean.add_company(con, names)
                con.commit()
                con.close()
                summary = clean.reclean_all(before + terms_of(names))
                return self.send(200, {"code": code, "summary": summary, "state": get_state()})
            elif path == "/api/theme":
                try:
                    if "text" in body:
                        tid = theme.save(body["text"])
                    else:
                        tid = body.get("use", "")
                        theme.use(tid)
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                if MAC_APP:  # the shield takes the look's colour
                    mac_finder_icon()
                name = next((t["name"] for t in theme.themes() if t["id"] == tid), "the default look")
                return self.send(200, {"name": name, "state": get_state()})
            elif path == "/api/rename-call":
                try:
                    new = clean.rename_call(str(body.get("file", "")), str(body.get("to", "")))
                except (ValueError, OSError) as e:
                    return self.send(400, {"error": str(e)})
                return self.send(200, {"file": new, "message": "Renamed.", "state": get_state()})
            elif path == "/api/delete-call":
                try:
                    clean.delete_call(str(body.get("file", "")))
                except OSError as e:
                    return self.send(400, {"error": str(e)})
                return self.send(200, {"message": "Call moved to the Recycle Bin.", "state": get_state()})
            elif path == "/api/hide":
                con = clean.connect()
                current = clean.hide_settings(con)
                new = {k: bool(body.get(k, v)) for k, v in current.items()}
                clean.set_setting(con, "hide", json.dumps(new))
                con.commit()
                con.close()
                summary = clean.reclean_all()
            elif path == "/api/vault":
                global REAL_HOME
                if clean.PRACTICE or TUTORIAL_SESSION:
                    return self.send(400, {"error": "Leave practice mode first."})
                chosen = pick_folder(str(clean.HOME.parent), title="Choose private storage for originals and client identities") if body.get("browse") else str(body.get("path", "")).strip()
                if not chosen:
                    return self.send(200, {"message": "", "state": get_state()})
                target = Path(chosen)
                if not (target / "private" / "vault.db").exists() and target.name != "TranscriptCleaner-Vault":
                    target = target / "TranscriptCleaner-Vault"
                try:
                    moved_to = clean.move_vault(target)
                except (ValueError, OSError) as e:
                    return self.send(400, {"error": str(e)})
                REAL_HOME = moved_to
                theme._write(vault=str(moved_to))
                warn = " It's inside OneDrive, so originals would sync to the cloud. Consider another folder." \
                    if "onedrive" in str(moved_to).lower() else ""
                return self.send(200, {"message": f"Your private files now live in {moved_to}.{warn}", "state": get_state()})
            elif path in ("/api/fathom", "/api/granola"):
                source = path.rsplit("/", 1)[1]
                src, label, SourceError = SOURCES[source]
                if TUTORIAL_SESSION:
                    return self.send(400, {'error':'Exit the guided tutorial before connecting or pulling real calls.'})
                try:
                    if body.get("key"):
                        src.set_key(str(body["key"]))
                        return self.send(200, {"message": f"{label} is connected.", "state": get_state()})
                    if body.get("clear"):
                        src.clear_key()
                        return self.send(200, {"message": f"{label} key removed from this computer.", "state": get_state()})
                    if body.get("list") or body.get("pull_ids"):
                        if clean.PRACTICE or TUTORIAL_SESSION:
                            return self.send(400, {"error": "Leave practice mode to pull your real calls."})
                    if body.get("list"):
                        # list calls in a window WITHOUT transcripts, so the member picks what to pull
                        from datetime import datetime as _dt, timedelta, timezone
                        w = body["list"]
                        now = _dt.now(timezone.utc)
                        iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
                        rng = w.get("range", "recent")
                        if rng == "24h":
                            calls, more = src.list_calls(after=iso(now - timedelta(hours=24)), limit=0)
                        elif rng == "7d":
                            calls, more = src.list_calls(after=iso(now - timedelta(days=7)), limit=0)
                        elif rng == "dates":
                            try:
                                a = _dt.strptime(w.get("from", ""), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                                b = _dt.strptime(w.get("to", "") or w.get("from", ""), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            except ValueError:
                                return self.send(400, {"error": "Pick a start date (and an end date if you like)."})
                            calls, more = src.list_calls(after=iso(a), before=iso(b + timedelta(days=1)), limit=0)
                        else:  # the most recent call: look back a little further until one turns up
                            calls, more = [], False
                            for days in (2, 14, 60, 365):
                                calls, more = src.list_calls(after=iso(now - timedelta(days=days)), limit=1)
                                if calls:
                                    break
                        con = clean.connect()
                        known = {r["file"] for r in con.execute("SELECT file FROM calls")}
                        con.close()
                        PICKS[source].clear()
                        out = []
                        for c in calls:
                            PICKS[source][str(c["id"])] = c["meta"]
                            out.append({k: c[k] for k in ("id", "title", "when", "minutes", "people")}
                                       | {"in_app": c["file"] in known})
                        return self.send(200, {"calls": out, "more": more})
                    if body.get("pull_ids"):
                        got, invited = [], []
                        for rid in body["pull_ids"][:25]:
                            meta = PICKS[source].get(str(rid))
                            if meta:
                                got.append(src.fetch(meta))
                                invited.append((got[-1][0], src.people(meta)))
                        summary = clean.run(texts=got)
                        con = clean.connect()
                        summary["suggested"] = sum(intake.suggest(con, people, name) for name, people in invited)
                        from datetime import datetime as _dt2
                        clean.set_setting(con, f"{source}_pulled_at", _dt2.now().isoformat(timespec="seconds"))
                        con.commit()
                        con.close()
                        summary["pulled"] = len(got)
                except (ValueError, OSError, SourceError) as e:
                    return self.send(400, {"error": str(e)})
            elif path == "/api/output":
                if TUTORIAL_SESSION and (body.get('browse') or 'path' in body):
                    return self.send(400, {'error':'The tutorial uses its own temporary export folder. Exit the tutorial to choose your own folder.'})
                con = clean.connect()
                msg = ""
                if body.get("browse"):
                    chosen = pick_folder(clean.get_setting(con, "output_dir"))
                    if chosen:
                        try:
                            chosen = str(clean.validate_output(chosen))
                        except ValueError as e:
                            con.close()
                            return self.send(400, {"error": str(e)})
                        clean.set_setting(con, "output_dir", chosen)
                        msg = "Clean copies will land there from now on."
                elif "path" in body:
                    folder = Path(str(body["path"]).strip().strip('"'))
                    if body["path"] and not folder.is_dir():
                        con.close()
                        return self.send(400, {"error": "That folder doesn't exist."})
                    try:
                        folder = clean.validate_output(folder) if body["path"] else None
                    except ValueError as e:
                        con.close()
                        return self.send(400, {"error": str(e)})
                    clean.set_setting(con, "output_dir", str(folder) if folder else "")
                    msg = "Saved." if body["path"] else "Clean copies will only stay in the app."
                con.commit()
                con.close()
                if body.get("send_all"):
                    n = clean.deliver_all()
                    msg = f"Sent {n} clean call{'s' if n != 1 else ''} to your folder."
                    state = get_state()
                    failed = sum(bool(c["export_error"]) for c in state["calls"])
                    pending = sum(c["status"] == "clean" and not c["export_approved"] for c in state["calls"]) if state["review_before_export"] else 0
                    if pending:
                        msg += f" {pending} need preview approval first."
                    if failed:
                        msg += f" {failed} could not be exported; open the call for details."
                return self.send(200, {"message": msg, "state": get_state()})
            elif path == "/api/open-folder":
                if body.get("kind") == "private":
                    folder = clean.HOME
                elif body.get("kind") == "output":
                    con = clean.connect()
                    try:
                        folder = clean.output_dir(con)
                    finally:
                        con.close()
                else:
                    return self.send(400, {"error": "Choose private storage or the clean export folder."})
                if not folder or not folder.is_dir():
                    return self.send(400, {"error": "That folder can't be found. Choose it again."})
                open_folder(folder)
                if TUTORIAL_SESSION and body.get('kind') == 'output':
                    TUTORIAL_SESSION['folder_opened'] = True
                return self.send(200, {"ok": True})
            elif path == "/api/restore":  # put names back into an agent's answer; nothing is stored
                text = str(body.get("text", ""))
                if len(text) > 2 * 1024 * 1024:
                    return self.send(400, {"error": "That's too long to restore in one go. Paste a shorter piece."})
                con = clean.connect()
                try:
                    return self.send(200, {"segments": restore.restore(con, text)})
                finally:
                    con.close()
            elif path in ("/api/suggestions", "/api/import-clients"):
                # people from meeting invites, or a pasted list / CSV: previewed, then saved together
                con = clean.connect()
                try:
                    with con:
                        if path == "/api/import-clients" and not body.get("save"):
                            text = str(body.get("text", ""))
                            if len(text) > 5 * 1024 * 1024:
                                return self.send(400, {"error": "That list is too large. Split it into smaller files."})
                            return self.send(200, {"rows": intake.preview(con, intake.parse(text))})
                        if body.get("dismiss"):
                            intake.dismiss(con, body["dismiss"][:500])
                        given = body.get("rows") if path == "/api/import-clients" else body.get("save")
                        rows = [r for r in given if isinstance(r, dict)][:intake.MAX_ROWS] if isinstance(given, list) else []
                        codes = intake.save(con, rows) if rows else []
                finally:
                    con.close()
                summary = clean.reclean_all(terms_of([(r.get("name"), r.get("email"), r.get("phone"), r.get("company")) for r in rows])) if codes else None
                return self.send(200, {"saved": len(codes), "summary": summary, "state": get_state()})
            elif path == "/api/review-done":  # "keep hidden": the stand-in stays; the name leaves the list
                ids = [i for i in body.get("ids", []) if isinstance(i, int) and not isinstance(i, bool)][:2000]
                con = clean.connect()
                try:
                    with con:
                        before = decisions.start(con)
                        rows = con.execute(f"SELECT name, file FROM review WHERE id IN ({','.join('?' * len(ids))})", ids).fetchall() if ids else []
                        con.executemany("UPDATE review SET reviewed=1 WHERE id=?", [(i,) for i in ids])
                        names = list(dict.fromkeys(display_name(r["name"]) for r in rows))
                        files = {r["file"] for r in rows}
                        label = f"{names[0]} stays hidden" if len(names) == 1 else f"{len(names)} names stay hidden"
                        undo = {"id": decisions.record(con, before, "keep_hidden", label, files.pop() if len(files) == 1 else ""), "label": label} if rows else None
                finally:
                    con.close()
                return self.send(200, {"state": get_state(), "undo": undo})
            elif path == "/api/team":  # teammates: visible in every call, shareable as a plain-text list
                con = clean.connect()
                try:
                    with con:
                        before = decisions.start(con)
                        if body.get("remove"):
                            name = str(body["remove"])
                            team.remove_member(con, name)
                            message = f"Removed. {name} is hidden again wherever the cleaner isn't sure about them."
                            label = f"{name} was taken off your team"
                        else:
                            name, why = team.add_member(con, body.get("add", ""))
                            if not name:
                                return self.send(400, {"error": why})
                            message = f"Saved. {name} stays visible in every call."
                            label = f"{name} is on your team and shows in every call"
                        undo = {"id": decisions.record(con, before, "team", label, terms=[name]), "label": label}
                finally:
                    con.close()
                summary = clean.reclean_all(terms_of(name))
                return self.send(200, {"summary": summary, "state": get_state(), "message": message, "undo": undo})
            elif path == "/api/team-list":  # export, preview or import a team list
                con = clean.connect()
                try:
                    action = body.get("action")
                    if action == "export":
                        return self.send(200, {"text": team.export_text(con)})
                    if action == "preview":
                        return self.send(200, team.preview(con, body.get("text", "")))
                    if action != "import":
                        return self.send(400, {"error": "Unknown team list action."})
                    with con:
                        got = team.import_text(con, body.get("text", ""))
                finally:
                    con.close()
                summary = clean.reclean_all(terms_of(*got["terms"])) if got["terms"] else None
                parts = [p for p in (f"{got['people']} {'person' if got['people'] == 1 else 'people'}" if got["people"] else "",
                                     f"{got['tools']} tool{'' if got['tools'] == 1 else 's'}" if got["tools"] else "") if p]
                message = (f"Added {' and '.join(parts)}." if parts else "Nothing new to add.") + \
                    (f" Left out {len(got['refused'])} saved client name{'' if len(got['refused']) == 1 else 's'}: they stay hidden." if got["refused"] else "")
                return self.send(200, {"summary": summary, "state": get_state(), "message": message})
            elif path == "/api/owner":  # the member's own name: never hidden in their calls
                name = " ".join(str(body.get("name", "")).split())[:80]
                if not name:
                    return self.send(400, {"error": "Enter your name."})
                con = clean.connect()
                try:
                    with con:
                        before = decisions.start(con)
                        old = clean.get_setting(con, "owner_name")
                        clean.set_setting(con, "owner_name", name)
                        for n in dict.fromkeys([name, name.split()[0]]):
                            if len(n) >= 2:
                                clean.add_to_list(con, "allow", n)
                        label = f"Your name is {name}"
                        undo = {"id": decisions.record(con, before, "owner", label, terms=[name]), "label": label}
                finally:
                    con.close()
                summary = clean.reclean_all([name, old])
                return self.send(200, {"summary": summary, "state": get_state(), "undo": undo,
                                       "message": "Saved. Your name stays visible in every call." + (" (Your previous name is still on the fine-to-keep list.)" if old and old != name else "")})
            elif path == "/api/hold":  # strict mode: hold calls until every unsure name is answered
                con = clean.connect()
                try:
                    with con:
                        clean.set_setting(con, "hold_unknown", "1" if body.get("on") else "0")
                finally:
                    con.close()
                summary = clean.reclean_all()
                return self.send(200, {"summary": summary, "state": get_state()})
            elif path == "/api/final-ok":  # "it's fine here": this phrase stays in this call's clean copy
                name, phrase = str(body.get("file", "")), str(body.get("phrase", "")).strip()
                if not name or name != clean.safe_name(name) or not phrase:
                    return self.send(400, {"error": "Choose a call and a phrase."})
                con = clean.connect()
                try:
                    with con:
                        before = decisions.start(con)
                        clean.final_ok(con, name, phrase)
                        label = f"“{phrase}” shows in this call"
                        undo = {"id": decisions.record(con, before, "final_ok", label, name), "label": label}
                        items = clean.final_check(con, name)
                finally:
                    con.close()
                return self.send(200, {"items": items, "undo": undo})
            elif path == "/api/undo":  # reverse one logged decision, then re-check the calls it touched
                con = clean.connect()
                try:
                    with con:
                        row, terms = decisions.undo(con, int(body.get("id", 0)))
                except (ValueError, TypeError) as e:
                    return self.send(400, {"error": str(e) or "Choose a decision to undo."})
                finally:
                    con.close()
                summary = clean.reclean_all(terms)
                return self.send(200, {"summary": summary, "state": get_state(),
                                       "message": f"Undone. {'It is back in Review names.' if row['action'] in ('keep', 'tool', 'hide_always', 'keep_hidden', 'which') else 'Your clean copies are updated.'}"})
            elif path == "/api/update-check":  # goes online only because the person clicked Check for updates
                return self.send(200, updater.check(ROOT))
            elif path == "/api/update-apply":
                try:
                    result = updater.apply(ROOT)
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                except Exception:
                    return self.send(400, {"error": "The update couldn't be downloaded. Check your internet connection and try again. Nothing was changed."})
                note = ""
                if result["packages"]:
                    ok, note = updater.install_packages(ROOT)
                return self.send(200, {**result, "note": note,
                                       "message": f"Updated to version {result['version']}. Restart to finish." + (f" {note}" if note else "")})
            elif path == "/api/restart":  # after an update: open the new version, then close this one
                if not (WINDOWED or NATIVE[0]):
                    return self.send(400, {"error": "Close Transcript Cleaner and open it again to finish."})
                updater.relaunch(ROOT)
                threading.Timer(1.5, quit_app).start()
                return self.send(200, {"ok": True})
            elif path == "/api/approve-export":
                con = clean.connect()
                try:
                    with con:
                        sent = clean.approve_export(con, str(body.get("file", "")))
                finally:
                    con.close()
                return self.send(200, {"message": "Approved and exported." if sent else "Approved. Choose an export folder to send it there.", "state": get_state()})
            elif path == "/api/export-review":
                if TUTORIAL_SESSION:
                    return self.send(400, {'error':'The tutorial includes review before export. Exit it to change this setting for your calls.'})
                con = clean.connect()
                try:
                    clean.set_setting(con, "review_before_export", "1" if body.get("on") else "0")
                    con.commit()
                finally:
                    con.close()
                summary = clean.reclean_all()
            elif path == "/api/forget":
                con = clean.connect()
                clean.forget_answer(con, str(body.get("kind", "")), str(body.get("name", "")), str(body.get("file", "")))
                con.commit()
                con.close()
                summary = clean.reclean_all(terms_of(body.get("name")))
            elif path == "/api/practice":
                if TUTORIAL_SESSION:
                    return self.send(400, {'error':'Exit the guided tutorial before switching practice workspaces.'})
                if body.get("on"):
                    start_practice()
                    summary = clean.run(paths=[HERE / "samples" / "calls"])
                else:
                    clean.set_home(REAL_HOME, practice=False)
                    return self.send(200, {"state": get_state()})
            elif path == "/api/tour":
                theme.set_tour_done(body.get("done", True))
                return self.send(200, {"state": get_state()})
            elif path == '/api/tutorial':
                action = body.get('action')
                if action == 'start':
                    start_tutorial()
                    theme.set_tour_done(True)
                elif action == 'load' and TUTORIAL_SESSION:
                    # Always use the built-in fixture in the isolated tutorial workspace.
                    con = clean.connect()
                    try:
                        exists = con.execute('SELECT 1 FROM calls WHERE file=?', (TUTORIAL_CALL,)).fetchone()
                    finally:
                        con.close()
                    if not exists:
                        summary = clean.run(texts=[(TUTORIAL_CALL, TUTORIAL_SAMPLE)])
                    if TUTORIAL_SESSION['step'] == 0:
                        TUTORIAL_SESSION['step'] = 1
                    return self.send(200, {'summary':summary, 'state':get_state()})
                elif action in ('exit', 'finish'):
                    if action == 'finish':
                        state = get_state()['tutorial']
                        if not state.get('exported') or not state.get('folder_opened'):
                            raise ValueError('Export the sample and open its folder before finishing, or choose Exit.')
                    end_tutorial()
                elif action == 'progress' and TUTORIAL_SESSION:
                    step = body.get('step', TUTORIAL_SESSION['step'])
                    if not isinstance(step, int) or isinstance(step, bool) or not 0 <= step <= 6:
                        raise ValueError('Choose a valid tutorial step.')
                    TUTORIAL_SESSION['step'] = step
                    if body.get('reviewed'):
                        con = clean.connect()
                        try:
                            row = con.execute('SELECT status FROM calls WHERE file=?', (TUTORIAL_CALL,)).fetchone()
                            if not row or row[0] != 'clean':
                                raise ValueError('Resolve the sample before reviewing it.')
                            TUTORIAL_SESSION['reviewed'] = True
                        finally:
                            con.close()
                else:
                    raise ValueError('Start a tutorial or choose a valid tutorial action.')
                return self.send(200, {'state':get_state()})
            elif path == "/api/brand":
                import base64
                unreadable = "That image couldn't be read. Try a PNG or JPG."
                try:
                    png = base64.b64decode(str(body["logo"]).split(",")[-1], validate=True) if body.get("logo") else None
                except ValueError:
                    return self.send(400, {"error": unreadable})
                try:
                    if "name" in body:
                        theme.set_name(str(body["name"]))
                    if png:
                        theme.set_logo(png)
                    if body.get("reset_logo"):
                        theme.clear_logo()
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                if MAC_APP:
                    mac_finder_icon()
                return self.send(200, {"state": get_state()})
            elif path == "/api/mode":
                try:
                    theme.set_mode(str(body.get("mode", "")))
                except ValueError as e:
                    return self.send(400, {"error": str(e)})
                return self.send(200, {"mode": theme.mode()})
            elif path == "/api/shortcut":
                return self.send(200, {"message": make_shortcut()})
            elif path == "/api/allow":
                con = clean.connect()
                if body.get("remove"):
                    clean.forget_answer(con, "allow", body["remove"])
                elif body.get("add", "").strip():
                    clean.add_to_list(con, "allow", body["add"])
                con.commit()
                con.close()
                summary = clean.reclean_all(terms_of(body.get("remove"), body.get("add")))
                return self.send(200, {"summary": summary, "state": get_state()})
            else:
                return self.send_error(404)
            return self.send(200, {"summary": summary, "state": get_state()})


ICON_VERSION = 2  # bump when the drawing changes, so Windows doesn't keep showing a cached old icon
ICON_SIZES = (16, 24, 32, 48, 64, 256)


def _in_shield(u, v):
    """Is the point (u, v), both 0..1 from the top left, inside the shield? One continuous outline, no seams."""
    x, top, mid, tip, w, r = abs(u - 0.5), 0.07, 0.48, 0.95, 0.40, 0.09
    if v < top or v > tip:
        return False
    if v < mid:
        if v < top + r and x > w - r:  # rounded top corners
            return (x - (w - r)) ** 2 + (v - top - r) ** 2 <= r * r
        return x <= w
    t = (v - mid) / (tip - mid)  # sides curve in to a soft point
    return x <= w * (1 - t ** 1.7) ** 0.62


def _on_check(u, v, half=0.052):
    """Is the point on the check mark (two strokes with round ends)?"""
    def near(ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        k = max(0.0, min(1.0, ((u - ax) * dx + (v - ay) * dy) / (dx * dx + dy * dy)))
        return (u - ax - k * dx) ** 2 + (v - ay - k * dy) ** 2 <= half * half
    return near(0.325, 0.50, 0.445, 0.62) or near(0.445, 0.62, 0.675, 0.375)


def _icon_pixels(n, rgb):
    """Rows of BGRA pixels, top to bottom, smoothed by sampling each pixel 4x4 times."""
    steps = [(i + 0.5) / 4 for i in range(4)]
    rows = []
    for y in range(n):
        row = bytearray()
        for x in range(n):
            shield = check = 0
            for sy in steps:
                for sx in steps:
                    u, v = (x + sx) / n, (y + sy) / n
                    if _in_shield(u, v):
                        shield += 1
                        check += _on_check(u, v)
            if not shield:
                row += b"\x00\x00\x00\x00"
                continue
            lift = 0.14 * (1 - y / n)  # a gentle top-lit gradient on the accent colour
            base = [c + (255 - c) * lift for c in rgb]
            mix = check / shield  # white check over the shield colour
            r, g, b = (round(c + (255 - c) * mix) for c in base)
            row += bytes([b, g, r, round(255 * shield / 16)])
        rows.append(bytes(row))
    return rows


def _png(n, rows):
    import struct
    import zlib
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(px for i in range(0, len(r), 4) for px in (r[i + 2], r[i + 1], r[i], r[i + 3])) for r in rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def make_icon(path, color="#2f6fdb"):
    """Draw a smooth shield-and-check .ico in every size Windows asks for, with no image library."""
    import struct
    rgb = [int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    images = []
    for n in ICON_SIZES:
        rows = _icon_pixels(n, rgb)
        if n >= 256:  # big sizes are stored as PNG inside the icon
            images.append((n, _png(n, rows)))
            continue
        pixels = b"".join(reversed(rows))  # bitmaps are stored bottom-up
        mask = b"\x00" * (((n + 31) // 32) * 4 * n)
        images.append((n, struct.pack("<IiiHHIIiiII", 40, n, n * 2, 1, 32, 0, len(pixels) + len(mask), 0, 0, 0, 0) + pixels + mask))
    offset = 6 + 16 * len(images)
    header, body = struct.pack("<HHH", 0, 1, len(images)), b""
    for n, data in images:
        header += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(data), offset + len(body))
        body += data
    path.write_bytes(header + body)


def open_folder(folder):
    if sys.platform == 'win32':
        os.startfile(str(folder.resolve()))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(folder.resolve())])
    else:
        subprocess.Popen(['xdg-open', str(folder.resolve())])


def pick_folder(start="", title="Choose where clean copies are exported"):
    if sys.platform == "darwin":
        # macOS's native chooser avoids running Tk's GUI outside the main thread.
        prompt = json.dumps(title)
        script = f"POSIX path of (choose folder with prompt {prompt})"
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else ""
    """The computer's own folder picker (like OBS's Browse...). Returns a path or ''."""
    result = []

    def ask():
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        result.append(filedialog.askdirectory(title=title, initialdir=start or str(Path.home()),
                                              mustexist=True, parent=root))
        root.destroy()
    t = threading.Thread(target=ask)
    t.start()
    t.join()
    return str(Path(result[0])) if result and result[0] else ""


def start_practice():
    """A fresh sample vault inside the app folder: made-up clients and calls, nothing real."""
    if PRACTICE_HOME.exists():
        shutil.rmtree(PRACTICE_HOME)
    (PRACTICE_HOME / "private").mkdir(parents=True)
    for f in ("clients.csv", "companies.csv", "allow.txt"):
        shutil.copy(HERE / "samples" / f, PRACTICE_HOME / "private" / f)
    clean.set_home(PRACTICE_HOME, practice=True)


def mac_icon_png():
    """The custom logo if there is one, else the shield as a PNG (drawn once, then reused)."""
    if theme.LOGO.exists():
        return theme.LOGO
    color = theme.accent() or "#2f6fdb"
    theme.THEMES.mkdir(parents=True, exist_ok=True)
    png = theme.THEMES / f"icon-v{ICON_VERSION}-{color.lstrip('#')}-256.png"
    if not png.exists():
        png.write_bytes(_png(256, _icon_pixels(256, [int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)])))
    return png


def mac_identity():
    """On a Mac the app runs inside its own copy of Python, so the Dock and menu bar would say "Python 3.13".
    Give them the app's name and logo from Appearance instead. Any step macOS ignores is skipped quietly."""
    global MAC_APP
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle, NSProcessInfo
    except Exception:
        return
    name = theme.brand()["name"]
    try:
        NSProcessInfo.processInfo().setProcessName_(name)
    except Exception:
        pass
    try:  # opened through Transcript Cleaner.app (made by setup): keep its name matching Appearance, from the next open
        bundle = Path(str(NSBundle.mainBundle().bundlePath()))
        plist = bundle / "Contents" / "Info.plist"
        if bundle.suffix == ".app" and plist.exists():
            import plistlib
            data = plistlib.loads(plist.read_bytes())
            if data.get("CFBundleName") != name:
                data["CFBundleName"] = data["CFBundleDisplayName"] = name
                plist.write_bytes(plistlib.dumps(data))
                os.utime(bundle)  # nudge macOS to re-read the package
    except Exception:
        pass
    try:  # read when the app registers with macOS, so it must be set before the window opens
        info = NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = name
            info["CFBundleDisplayName"] = name
    except Exception:
        pass
    try:
        image = NSImage.alloc().initWithContentsOfFile_(str(mac_icon_png()))
        if image is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(image)
    except Exception:
        pass
    MAC_APP = True
    mac_finder_icon()


def mac_finder_icon():
    """Give Transcript Cleaner.app (and so its desktop shortcut) the logo from Appearance in Finder.
    Setup calls this once; the app calls it again when the logo or look changes. Skipped when nothing changed."""
    bundle = ROOT / "Transcript Cleaner.app"
    if sys.platform != "darwin" or not bundle.is_dir():
        return
    try:
        from AppKit import NSImage, NSWorkspace
        png = mac_icon_png()
        stamp, key = bundle / "Contents" / "icon-source", f"{png}:{png.stat().st_mtime_ns}"
        if stamp.exists() and stamp.read_text(encoding="utf-8") == key:
            return
        image = NSImage.alloc().initWithContentsOfFile_(str(png))
        if image is not None and NSWorkspace.sharedWorkspace().setIcon_forFile_options_(image, str(bundle), 0):
            stamp.write_text(key, encoding="utf-8")
    except Exception:
        pass


def current_icon():
    """The custom logo if there is one, else the shield in the current look's accent colour."""
    if theme.LOGO_ICO.exists():
        return theme.LOGO_ICO
    color = theme.accent() or "#2f6fdb"
    theme.THEMES.mkdir(parents=True, exist_ok=True)
    icon = theme.THEMES / f"icon-v{ICON_VERSION}-{color.lstrip('#')}.ico"
    if not icon.exists():
        make_icon(icon, color)
    return icon


def make_shortcut():
    """Put the app's icon on the user's desktop (Windows), pointing at the launcher, with the chosen name."""
    if sys.platform != "win32":
        return "Desktop shortcuts are Windows-only in this version. On a Mac, drag the launcher to your Dock."
    icon = current_icon()
    name = re.sub(r'[\\/:*?"<>|\']', "", theme.brand()["name"]).strip() or "Transcript Cleaner"
    launcher = HERE / "Open Transcript Cleaner.vbs"
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '{name}.lnk'));"
        f"$s.TargetPath=\"$env:WINDIR\\System32\\wscript.exe\";$s.Arguments='\"{launcher}\"';"
        f"$s.WorkingDirectory='{HERE}';$s.IconLocation='{icon},0';$s.Description='Clean call transcripts on this computer';"
        "$s.Save();Write-Output $d"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if out.returncode != 0:
        return "Couldn't create the shortcut. You can right-click the launcher and choose Send to, Desktop."
    return f"Added {name} to your desktop."


def window_profile():
    """The app window's own Chrome profile, outside the code folder and outside private storage."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "TranscriptCleaner" / "app-window"


def window_args(url):
    """Chrome flags for the app window. Its own profile makes it a separate Chrome: closing or ending it
    can't take the member's browsing with it, and their extensions (which could read the original
    transcripts on this page) never load here."""
    return [f"--user-data-dir={window_profile()}", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-sync", f"--app={url}", "--window-size=1320,880"]


def native_window(url):
    """The app in its own window: Windows' built-in WebView2, or Apple's WebKit on a Mac.

    The window belongs to this process, so ending Transcript Cleaner (End task, Force Quit) can only end
    Transcript Cleaner, never the member's browser, and browser extensions never see the page. Blocks until
    the window closes and returns True; returns False straight away if a native window isn't possible here,
    so the caller can fall back to a separate Chrome window.
    """
    gui = {"win32": "edgechromium", "darwin": "cocoa"}.get(sys.platform)
    if not gui or os.environ.get("CLEANER_NO_NATIVE_WINDOW"):
        return False
    try:
        import webview
    except Exception:
        return False
    if sys.platform == "win32":
        try:  # its own taskbar button and icon, rather than Python's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TranscriptCleaner")
        except Exception:
            pass
    elif sys.platform == "darwin":
        mac_identity()
    webview.settings["ALLOW_DOWNLOADS"] = True                 # the Download buttons
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True   # outside links (e.g. design.md libraries) go to the browser
    webview.settings["SHOW_DEFAULT_MENUS"] = True               # right-click copy and paste
    webview.settings["REMOTE_DEBUGGING_PORT"] = None            # never open a debugging port
    storage = window_profile().parent / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    try:
        # no js_api: the page can't call into Python; text selection and zoom stay available
        width, height = 1320, 880
        try:  # fit smaller laptop screens, leaving room for the taskbar or dock
            screen = webview.screens[0]
            width, height = min(width, screen.width - 60), min(height, screen.height - 100)
        except Exception:
            pass
        webview.create_window(theme.brand()["name"], url, width=width, height=height, min_size=(720, 520),
                              text_select=True, zoomable=True)
        NATIVE[0] = True
        webview.start(gui=gui, private_mode=False, storage_path=str(storage), icon=str(current_icon()), debug=False)
    except Exception as e:
        NATIVE[0] = False
        print(f"Couldn't open the app's own window ({e}); using a separate Chrome window instead.")
        return False
    return True


def open_window(url):
    """Chrome in app mode (its own window, no tabs, own profile); fall back to the default browser."""
    window_profile().mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin" and Path("/Applications/Google Chrome.app").exists():
        subprocess.Popen(["open", "-na", "Google Chrome", "--args", *window_args(url)])
        return True
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            chrome = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if chrome.exists():
                subprocess.Popen([str(chrome), *window_args(url)])
                return True
    webbrowser.open(url)  # an ordinary browser tab: reloads and tab switches are common, so don't stop on goodbye
    return False


def watchdog(server):
    while True:
        time.sleep(1)
        now = time.time()
        # closed = the page that said goodbye is still the newest one, and nothing at all has asked since
        closed = (WINDOWED and bye_at[0] and now - bye_at[0] > BYE_GRACE
                  and current_page[0] == bye_page[0] and last_request[0] <= bye_at[0])
        # A hidden or covered window can pause its heartbeat (macOS does), so silence only ends a browser window;
        # stopping under the app's own window left it open and saying "Load failed" (Wade's MacBook, 10-21)
        if closed or (not NATIVE[0] and now - last_ping[0] > IDLE_LIMIT):
            server.shutdown()
            return


SERVER = [None]


def quit_app():
    """Close this copy after Restart now has opened the new version: closing the window stops the app as usual."""
    if NATIVE[0]:
        try:
            import webview
            for w in list(webview.windows):
                w.destroy()
            return
        except Exception:
            pass
    if SERVER[0] is not None:
        SERVER[0].shutdown()


def warm_up():
    """Load the name model, then release calls an earlier version held for answers (unless strict mode is on)."""
    clean.get_analyzer()
    con = clean.connect()
    try:
        waiting = not clean.hold_unknown(con) and con.execute("SELECT 1 FROM calls WHERE status='held' LIMIT 1").fetchone()
        waiting = waiting or any(f.is_file() for f in clean.DIRTY.iterdir())  # e.g. calls queued by the one-time stand-in renumbering
    finally:
        con.close()
    if waiting:
        try:
            clean.reclean_all([])  # no RAW call matches an empty change; held calls always run
        except Exception as e:  # the next action retries; never stop the app over it
            print(f"Could not release waiting calls yet: {e}", flush=True)


def main():
    global PORT, ALLOWED_HOSTS, WINDOWED
    # Bind first: the OS reserves a unique port atomically, including parallel launches.
    server = LocalServer(("127.0.0.1", 0), Handler)
    SERVER[0] = server
    PORT = server.server_address[1]
    ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
    clean.init()
    clean.forget_deleted()
    prune_tutorial_folders()
    threading.Thread(target=warm_up, daemon=True).start()
    threading.Thread(target=watchdog, args=(server,), daemon=True).start()
    url = f"http://127.0.0.1:{PORT}/"
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    print(f"Transcript Cleaner is running at {url} (close the app window to stop it)", flush=True)
    if "--no-window" in sys.argv:
        WINDOWED = bool(os.environ.get("CLEANER_TEST_BYE"))  # lets a test prove the window-close shutdown
    elif native_window(url):  # the usual path: runs until the window is closed
        server.shutdown()
        return
    else:
        WINDOWED = open_window(url)
    try:
        while serving.is_alive():
            serving.join(0.5)
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()

"""Pull meeting transcripts from Granola's API, using only Python's built-in modules.

Granola's public API (docs.granola.ai) is read-only and needs a Business or Enterprise
workspace; keys start with grn_ and are created in the Granola desktop app under
Settings > Connectors > API keys. The key lives in the computer's own password store,
like the Fathom key. Transcripts arrive as raw text and go into the private dirty folder
to be cleaned like any call. Only notes that already have a transcript are returned.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import keystore

BASE = os.environ.get("GRANOLA_API_BASE", "https://public-api.granola.ai/v1")
TARGET = os.environ.get("GRANOLA_KEY_TARGET", "TranscriptCleaner/Granola")
PAUSE = float(os.environ.get("GRANOLA_PAUSE", "0.25"))  # stays well under Granola's 5 requests a second


class GranolaError(Exception):
    pass


class _TooLarge(Exception):
    pass


def _get():
    return keystore.get(TARGET, "granola")


def has_key():
    return bool(_get())


def set_key(key):
    key = (key or "").strip()
    if not key.startswith("grn_") or len(key) < 12 or any(c.isspace() for c in key):
        raise ValueError("That doesn't look like a Granola API key. Granola keys start with grn_.")
    keystore.put(TARGET, "granola", key, "Granola")


def clear_key():
    keystore.clear(TARGET, "granola")


def _request(path, params, key):
    url = f"{BASE}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                               "User-Agent": "TranscriptCleaner/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 413:
            raise _TooLarge()
        if e.code in (401, 403):
            raise GranolaError("Granola didn't accept the key. Check it in Granola (Settings, Connectors, API keys) and save it again.")
        if e.code == 404:
            raise GranolaError("Granola couldn't find that note. It may have been deleted or your key can't see it.")
        if e.code == 429:
            raise GranolaError("Granola says to slow down. Try again in a minute.")
        raise GranolaError(f"Granola returned an error ({e.code}). Try again later.")
    except urllib.error.URLError:
        raise GranolaError("Couldn't reach Granola. Check your internet connection.")


def _key():
    key = _get()
    if not key:
        raise GranolaError("Add your Granola API key in Settings first.")
    return key


def file_name(note):
    """A neutral file name: note titles often contain the client's name."""
    day = (note.get("created_at") or "")[:10] or "undated"
    nid = "".join(ch for ch in str(note.get("id") or "").replace("not_", "", 1) if ch.isalnum())[:24] or "note"
    return f"granola-{day}-{nid}.txt"


def list_calls(after="", before="", limit=1, max_items=50):
    """Notes in a window, newest first, WITHOUT transcripts. Returns (calls, more), like fathom.list_calls."""
    key = _key()
    params = {"page_size": 30}
    if after:
        params["created_after"] = after
    if before:
        params["created_before"] = before
    found, cursor, more = [], None, False
    while True:
        if cursor:
            params["cursor"] = cursor
        data = _request("/notes", params, key)
        found.extend(n for n in data.get("notes") or data.get("items") or data.get("data") or [] if not n.get("deleted_at"))
        cursor = data.get("cursor")
        more = bool(data.get("hasMore")) and bool(cursor)
        if not more or len(found) > max_items:
            break
        time.sleep(PAUSE)
    found.sort(key=lambda n: n.get("created_at") or "", reverse=True)
    more = more or len(found) > max_items
    calls = [{
        "id": n.get("id"), "title": n.get("title") or "Untitled note", "when": n.get("created_at") or "",
        "minutes": 0, "people": 0, "file": file_name(n), "meta": n,
    } for n in found[: max(limit, 1) if limit else max_items]]
    return calls, more


def _transcript_pages(note_id, key):
    items, cursor = [], None
    for _ in range(200):
        params = {"page_size": 100}
        if cursor:
            params["cursor"] = cursor
        data = _request(f"/notes/{urllib.parse.quote(note_id)}/transcript", params, key)
        items.extend(data.get("transcript") or [])
        cursor = data.get("cursor")
        if not data.get("hasMore") or not cursor:
            return items
        time.sleep(PAUSE)
    return items


def _clock(start, at):
    """Time since the first line, as HH:MM:SS, so lines read like other transcripts."""
    try:
        a = datetime.fromisoformat(start.replace("Z", "+00:00"))
        b = datetime.fromisoformat(at.replace("Z", "+00:00"))
        s = max(0, int((b - a).total_seconds()))
        return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
    except (AttributeError, ValueError):
        return ""


def as_text(note, transcript):
    """One note as plain transcript text. Names and emails stay in: the cleaner removes them."""
    lines = []
    if note.get("title"):
        lines.append(f"Meeting: {note['title']}")
    event = note.get("calendar_event") or {}
    when = event.get("scheduled_start_time") or note.get("created_at") or ""
    if when:
        lines.append(f"Date: {when}")
    people = [f"{a.get('name') or ''} <{a.get('email') or ''}>".strip() for a in note.get("attendees") or []]
    seen = {a.get("email") for a in note.get("attendees") or []}
    people += [f"<{i.get('email')}>" for i in event.get("invitees") or [] if i.get("email") and i.get("email") not in seen]
    if people:
        lines.append("Attendees: " + "; ".join(people))
    lines.append("")
    owner = ((note.get("owner") or {}).get("name") or "").strip()
    first = next((t.get("start_time") for t in transcript if t.get("start_time")), "")
    for t in transcript:
        sp = t.get("speaker") or {}
        mine = sp.get("attribution") == "me" or (not sp.get("attribution") and sp.get("source") == "microphone")
        who = (sp.get("name") or (owner if mine else "") or sp.get("diarization_label")
               or ("Me" if mine else "Them")).strip()
        stamp = _clock(first, t.get("start_time") or "")
        lines.append(f"{'[' + stamp + '] ' if stamp else ''}{who}: {(t.get('text') or '').strip()}")
    return "\n".join(lines) + "\n"


def fetch(meta):
    """One note's transcript by its id, as (file_name, text)."""
    key = _key()
    note_id = str(meta.get("id") or "")
    if not note_id.startswith("not_"):
        raise GranolaError("That isn't a Granola note.")
    try:
        note = _request(f"/notes/{urllib.parse.quote(note_id)}", {"include": "transcript"}, key)
        transcript = note.get("transcript")
    except _TooLarge:  # long meetings: Granola sends the note without it, and the transcript in pages
        note = _request(f"/notes/{urllib.parse.quote(note_id)}", {}, key)
        time.sleep(PAUSE)
        transcript = _transcript_pages(note_id, key)
    if not transcript:
        raise GranolaError("That note has no transcript yet. Try again once Granola has finished it.")
    note = dict(meta, **note)
    meta.update({k: note.get(k) for k in ("attendees", "calendar_event", "owner")})  # for people(), after the fetch
    return file_name(note), as_text(note, transcript)


def people(meta):
    """Who was in the meeting: attendees with names, plus invitees known only by email. The note-taker is left out."""
    owner = ((meta.get("owner") or {}).get("email") or "").lower()
    out, seen = [], set()
    for a in meta.get("attendees") or []:
        email = (a.get("email") or "").lower()
        if email and email != owner and email not in seen:
            seen.add(email)
            out.append({"name": a.get("name") or "", "email": email})
    for i in (meta.get("calendar_event") or {}).get("invitees") or []:
        email = (i.get("email") or "").lower()
        if email and email != owner and email not in seen:
            seen.add(email)
            out.append({"name": "", "email": email})
    return out

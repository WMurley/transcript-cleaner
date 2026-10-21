"""Pull new call transcripts from Fathom's API, using only Python's built-in modules.

The API key lives in the computer's own password store (Windows Credential
Manager, or the macOS Keychain), never in a file the app or an agent can read.
Only the cleaner reads it, only to talk to Fathom. Transcripts arrive as raw
text and go straight into the private dirty folder to be cleaned like any call.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import keystore

BASE = os.environ.get("FATHOM_API_BASE", "https://api.fathom.ai/external/v1")
TARGET = os.environ.get("FATHOM_KEY_TARGET", "TranscriptCleaner/Fathom")


# ---------- the key, in the computer's password store ----------

def _get():
    return keystore.get(TARGET, "fathom")


def _set(key):
    keystore.put(TARGET, "fathom", key, "Fathom")


def _clear():
    keystore.clear(TARGET, "fathom")


def has_key():
    return bool(_get())


def set_key(key):
    key = (key or "").strip()
    if len(key) < 10 or any(c.isspace() for c in key):
        raise ValueError("That doesn't look like a Fathom API key.")
    _set(key)


def clear_key():
    _clear()


# ---------- pulling calls ----------

class FathomError(Exception):
    pass


def _request(path, params, key):
    url = f"{BASE}{path}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"X-Api-Key": key, "Accept": "application/json",
                                               "User-Agent": "TranscriptCleaner/1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise FathomError("Fathom didn't accept the key. Check it in Fathom's settings and save it again.")
        if e.code == 429:
            raise FathomError("Fathom says to slow down. Try again in a minute.")
        raise FathomError(f"Fathom returned an error ({e.code}). Try again later.")
    except urllib.error.URLError:
        raise FathomError("Couldn't reach Fathom. Check your internet connection.")


def as_text(m):
    """One meeting as plain transcript text. Names and emails stay in: the cleaner removes them."""
    lines = []
    title = m.get("meeting_title") or m.get("title") or ""
    if title:
        lines.append(f"Meeting: {title}")
    when = m.get("recording_start_time") or m.get("created_at") or ""
    if when:
        lines.append(f"Date: {when}")
    invitees = [f"{i.get('name') or ''} <{i.get('email') or ''}>".strip() for i in (m.get("calendar_invitees") or [])]
    if invitees:
        lines.append("Invitees: " + "; ".join(invitees))
    lines.append("")
    for t in m.get("transcript") or []:
        who = ((t.get("speaker") or {}).get("display_name") or "Speaker").strip()
        lines.append(f"[{t.get('timestamp', '')}] {who}: {(t.get('text') or '').strip()}")
    return "\n".join(lines) + "\n"


def file_name(m):
    """A neutral file name: meeting titles often contain the client's name."""
    day = (m.get("recording_start_time") or m.get("created_at") or "")[:10] or "undated"
    rid = "".join(ch for ch in str(m.get("recording_id") or "") if ch.isalnum())[:24] or "call"
    return f"fathom-{day}-{rid}.txt"


def _minutes(m):
    from datetime import datetime
    try:
        a = datetime.fromisoformat((m.get("recording_start_time") or "").replace("Z", "+00:00"))
        b = datetime.fromisoformat((m.get("recording_end_time") or "").replace("Z", "+00:00"))
        return max(0, round((b - a).total_seconds() / 60))
    except ValueError:
        return 0


def list_calls(after="", before="", limit=1, max_items=50):
    """Recent calls in a window, newest first, WITHOUT transcripts (fast, pulls nothing heavy).

    Returns (calls, more): calls are dicts the app shows in a picker; more is True when the
    window holds more than max_items, so the member can narrow it.
    """
    key = _get()
    if not key:
        raise FathomError("Add your Fathom API key in Settings first.")
    params = {"limit": min(max_items, 50)}
    if after:
        params["created_after"] = after
    if before:
        params["created_before"] = before
    found, cursor = [], None
    while True:
        if cursor:
            params["cursor"] = cursor
        data = _request("/meetings", params, key)
        found.extend(data.get("items") or [])
        cursor = data.get("next_cursor")
        if not cursor or len(found) > max_items:
            break
    found.sort(key=lambda m: m.get("recording_start_time") or m.get("created_at") or "", reverse=True)
    more = len(found) > max_items or bool(cursor)
    calls = [{
        "id": m.get("recording_id"), "title": m.get("meeting_title") or m.get("title") or "Untitled call",
        "when": m.get("recording_start_time") or m.get("created_at") or "", "minutes": _minutes(m),
        "people": len(m.get("calendar_invitees") or []), "file": file_name(m), "meta": m,
    } for m in found[: max(limit, 1) if limit else max_items]]
    return calls, more


def people(meta):
    """Who was on the invite: [{name, email, external}] (Fathom marks your own workspace as not external)."""
    return [{"name": i.get("name") or "", "email": i.get("email") or "", "external": i.get("is_external")}
            for i in meta.get("calendar_invitees") or []]


def fetch(meta):
    """One call's transcript by its recording id, as (file_name, text)."""
    key = _get()
    if not key:
        raise FathomError("Add your Fathom API key in Settings first.")
    data = _request(f"/recordings/{int(meta['recording_id'])}/transcript", {}, key)
    m = dict(meta, transcript=data.get("transcript") or [])
    if not m["transcript"]:
        raise FathomError("That call has no transcript yet. Try again once Fathom has finished processing it.")
    return file_name(m), as_text(m)


def pull(since="", known=frozenset(), max_pages=20):
    """Return (list of (file_name, text), newest created_at seen). Skips calls already in the app."""
    key = _get()
    if not key:
        raise FathomError("Add your Fathom API key in Settings first.")
    params = {"include_transcript": "true", "limit": 10}
    if since:
        params["created_after"] = since
    out, newest, cursor = [], since, None
    for _ in range(max_pages):
        if cursor:
            params["cursor"] = cursor
        data = _request("/meetings", params, key)
        for m in data.get("items") or []:
            created = m.get("created_at") or ""
            newest = max(newest, created) if newest else created
            name = file_name(m)
            if name in known or not m.get("transcript"):
                continue
            out.append((name, as_text(m)))
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return out, newest

"""Your team: teammates and tools that are fine to show in every call, shareable as a short plain-text list.

A teammate's full name and first name stay visible everywhere, like the member's own name. Tools join the
same remembered tool list as "It's a tool". The list is plain text so it can be pasted into Slack or saved as
a .txt file, and a teammate pastes or opens it in their own app. It never holds client names: a name that
matches a saved client is refused, so importing someone else's list can't un-hide a client.
"""

import json
import re

import clean

HEADER = "# Transcript Cleaner team list: people and tools that are fine to show in every call"
NAME = re.compile(r"^[^\W\d_](?:[^\W\d_]|[ '.\-’])*$")  # letters, spaces, apostrophes, dots and hyphens
MAX_ITEMS = 300


def _clean_name(value):
    v = " ".join(str(value).replace("’", "'").split()).strip(" ,;")
    return v if 2 <= len(v) <= 80 and NAME.match(v) else ""


def _client_names(con):
    names = set()
    for r in con.execute("SELECT full_name, aliases FROM clients"):
        names.add(r["full_name"].lower())
        names |= {a.lower() for a in clean.split(r["aliases"])}
    for r in con.execute("SELECT names FROM companies"):
        names |= {n.lower() for n in clean.split(r["names"])}
    return names


def _first_names_in_use(con, skip=""):
    """First names kept visible by the member's own name or another teammate."""
    owner = clean.get_setting(con, "owner_name")
    people = [n for n in clean.get_list(con, "team") if n.lower() != skip.lower()] + ([owner] if owner else [])
    return {n.split()[0].lower() for n in people}


def members(con):
    return clean.get_list(con, "team")


def add_member(con, name):
    """Returns (saved name, "") or ("", reason)."""
    name = _clean_name(name)
    if not name:
        return "", "Use a name made of letters, 2 to 80 characters."
    if name.lower() in _client_names(con):
        return "", f"{name} is a saved client or company, so they stay hidden."
    clean.add_to_list(con, "team", name)
    for n in dict.fromkeys([name, name.split()[0]]):
        if len(n) >= 2:
            clean.add_to_list(con, "allow", n)
    return name, ""


def remove_member(con, name):
    first = name.split()[0] if name.split() else ""
    con.execute("DELETE FROM lists WHERE list='team' AND lower(name)=lower(?)", (name,))
    con.execute("DELETE FROM lists WHERE list='allow' AND lower(name)=lower(?)", (name,))
    if first and " " in name.strip() and first.lower() not in _first_names_in_use(con, skip=name):
        con.execute("DELETE FROM lists WHERE list='allow' AND lower(name)=lower(?)", (first,))


def add_tool(con, name):
    name = _clean_name(name)
    if not name:
        return ""
    for lst in ("allow", "context_allow", "tools"):
        clean.add_to_list(con, lst, name)
    return name


def export_text(con):
    lines = [HEADER, "# Paste it into Settings > Your team, or open the saved file there."]
    lines += members(con)
    lines += [f"tool: {t}" for t in clean.get_list(con, "tools")]
    return "\n".join(lines) + "\n"


def parse(text):
    """Read a pasted or opened team list: one name per line, "tool: Name" for tools, # for notes.
    The JSON form {"people": [...], "tools": [...]} is read too. Nothing is saved here."""
    people, tools, skipped = [], [], []
    text = str(text or "")[:200_000]
    try:
        data = json.loads(text)
        rows = [("person", p) for p in data.get("people", [])] + [("tool", t) for t in data.get("tools", [])] if isinstance(data, dict) else []
    except ValueError:
        rows = []
        for line in text.splitlines():
            line = line.strip().lstrip("-*•").strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"(?i)^tools?\s*:\s*(.+)$", line)
            rows += [("tool", m.group(1))] if m else [("person", line)]
    for kind, raw in rows[:MAX_ITEMS]:
        name = _clean_name(raw) if isinstance(raw, str) else ""
        if not name:
            skipped.append(str(raw)[:60])
        elif kind == "tool":
            tools.append(name)
        else:
            people.append(name)
    if len(rows) > MAX_ITEMS:
        skipped.append(f"{len(rows) - MAX_ITEMS} more lines (a team list holds up to {MAX_ITEMS})")
    return {"people": list(dict.fromkeys(people)), "tools": list(dict.fromkeys(tools)), "skipped": skipped}


def preview(con, text):
    """What importing would do, without saving: new, already on the team, or refused (a saved client)."""
    got = parse(text)
    have = {m.lower() for m in members(con)}
    have_tools = {t.lower() for t in clean.get_list(con, "tools")}
    clients = _client_names(con)
    rows = [{"name": p, "kind": "person",
             "status": "client" if p.lower() in clients else "have" if p.lower() in have else "new"} for p in got["people"]]
    rows += [{"name": t, "kind": "tool",
              "status": "client" if t.lower() in clients else "have" if t.lower() in have_tools else "new"} for t in got["tools"]]
    return {"rows": rows, "skipped": got["skipped"]}


def import_text(con, text):
    """Save the new people and tools from a team list. Returns counts and the names that changed."""
    added, tools, refused, terms = 0, 0, [], []
    for row in preview(con, text)["rows"]:
        if row["status"] == "client":
            refused.append(row["name"])
        elif row["status"] == "new":
            if row["kind"] == "person":
                name, _ = add_member(con, row["name"])
                added += bool(name)
            else:
                name = add_tool(con, row["name"])
                tools += bool(name)
            if name:
                terms.append(name)
    return {"people": added, "tools": tools, "refused": refused, "terms": terms}

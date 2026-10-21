"""Undo for one-click decisions (Fine to show, Keep hidden, It's a tool, Which client, On my team, This is me,
the final check's Leave it). Each decision is logged with the exact difference it made to the answer tables,
so Undo can reverse it later, from the pop-up or from Recent decisions. Saving a new client goes through the
Clients page instead and is not logged here."""
import json
import time

import clean


def start(con):
    """Snapshot the small tables a one-click decision can change. Call before the decision, in the same transaction."""
    return {
        "lists": {(r["list"], r["name"]) for r in con.execute("SELECT list, name FROM lists")},
        "resolutions": {(r["file"], r["name"]): r["value"] for r in con.execute("SELECT file, name, value FROM resolutions")},
        "final_ok": {(r["file"], r["phrase"]) for r in con.execute("SELECT file, phrase FROM final_ok")},
        "owner": clean.get_setting(con, "owner_name", "") or "",
        "reviewed": {r["id"] for r in con.execute("SELECT id FROM review WHERE reviewed=1")},
    }


def record(con, before, action, label, file="", terms=()):
    """Log what changed since start(). Returns the decision id for Undo, or None when nothing changed."""
    after = start(con)
    res_b, res_a = before["resolutions"], after["resolutions"]
    diff = {
        "lists_added": sorted(after["lists"] - before["lists"]),
        "lists_removed": sorted(before["lists"] - after["lists"]),
        "res_set": [[f, n, res_b.get((f, n))] for (f, n), v in sorted(res_a.items()) if res_b.get((f, n)) != v],
        "res_removed": [[f, n, v] for (f, n), v in sorted(res_b.items()) if (f, n) not in res_a],
        "ok_added": sorted(after["final_ok"] - before["final_ok"]),
        "owner": before["owner"] if after["owner"] != before["owner"] else None,
        "reviewed": sorted(after["reviewed"] - before["reviewed"]),
    }
    if not any(v for k, v in diff.items() if k != "owner") and diff["owner"] is None:
        return None
    names = {n for _, n in diff["lists_added"] + diff["lists_removed"]} | {n for _, n, _ in diff["res_set"] + diff["res_removed"]}
    owners = [before["owner"], after["owner"]] if diff["owner"] is not None else []
    diff["terms"] = sorted({t for t in [*terms, *names, *owners] if t})
    diff["file0"] = file  # the call's name when decided; a later rename moves decisions.file, and undo follows it
    cur = con.execute("INSERT INTO decisions (at, action, label, file, undo) VALUES (?,?,?,?,?)",
                      (time.strftime("%Y-%m-%dT%H:%M:%S"), action, label, file, json.dumps(diff)))
    con.execute("DELETE FROM decisions WHERE id <= ?", (cur.lastrowid - 500,))  # keep the last 500
    return cur.lastrowid


def undo(con, decision_id):
    """Reverse one logged decision. Returns (row, names to re-check); the caller re-cleans the calls they appear in."""
    row = con.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
    if not row:
        raise ValueError("That decision is no longer in the list.")
    if row["undone"]:
        raise ValueError("That decision was already undone.")
    d = json.loads(row["undo"])
    calls = {r["file"] for r in con.execute("SELECT file FROM calls")}

    def here(f):  # a renamed call keeps its decisions; a deleted call's per-call answers are not brought back
        f = row["file"] if f == d.get("file0") and row["file"] else f
        return f if f in calls else None

    d["res_set"] = [[here(f), n, old] for f, n, old in d["res_set"] if here(f)]
    d["res_removed"] = [[here(f), n, v] for f, n, v in d["res_removed"] if here(f)]
    d["ok_added"] = [[here(f), p] for f, p in d["ok_added"] if here(f)]
    for lst, name in d["lists_added"]:
        con.execute("DELETE FROM lists WHERE list=? AND name=?", (lst, name))
    for lst, name in d["lists_removed"]:
        clean.add_to_list(con, lst, name)
    for f, n, old in d["res_set"]:
        if old is None:
            con.execute("DELETE FROM resolutions WHERE file=? AND name=?", (f, n))
        else:
            con.execute("INSERT OR REPLACE INTO resolutions (file, name, value) VALUES (?,?,?)", (f, n, old))
    for f, n, v in d["res_removed"]:
        con.execute("INSERT OR REPLACE INTO resolutions (file, name, value) VALUES (?,?,?)", (f, n, v))
    for f, phrase in d["ok_added"]:
        con.execute("DELETE FROM final_ok WHERE file=? AND phrase=?", (f, phrase))
    if d["owner"] is not None:
        clean.set_setting(con, "owner_name", d["owner"])
    con.executemany("UPDATE review SET reviewed=0 WHERE id=?", [(i,) for i in d["reviewed"]])
    con.execute("UPDATE decisions SET undone=1 WHERE id=?", (decision_id,))
    return row, d["terms"]


def recent(con, limit=100):
    return [{k: r[k] for k in ("id", "at", "action", "label", "file", "undone")}
            for r in con.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,))]

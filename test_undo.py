"""Undo for one-click decisions: each decision is logged with the difference it made and can be reversed exactly.
Synthetic data in a throwaway vault."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="tc-undo-"))
os.environ["CLEANER_HOME"] = str(TMP / "vault")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean  # noqa: E402  (reads CLEANER_HOME at import)
import decisions  # noqa: E402
import identities  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label)


def review(con, name):
    return con.execute("SELECT * FROM review WHERE lower(name)=lower(?) AND reviewed=0", (name,)).fetchone()


try:
    clean.init()
    con = clean.connect()
    with con:
        clean.set_setting(con, "owner_name", "Morgan Reyes")
        clean.add_to_list(con, "allow", "Morgan Reyes")
        clean.add_client(con, "Mike Alvarez")
        clean.add_client(con, "Mike Chen")
    con.close()
    clean.run(texts=[("one.txt", "Morgan Reyes: Lena Haugen sent the quote. Mike will sign it.\n"),
                     ("two.txt", "Morgan Reyes: Ruth Okafor checked the numbers.\n")])

    # Fine to show, then Undo: the name is hidden again and back in Review names
    con = clean.connect()
    row = review(con, "Lena Haugen")
    with con:
        before = decisions.start(con)
        identities.save(con, {"review_id": row["id"], "kind": "person", "action": "keep"})
        did = decisions.record(con, before, "keep", "Lena Haugen shows in every call")
    con.close()
    clean.reclean_all(["Lena Haugen"])
    con = clean.connect()
    check("Fine to show makes the name visible and leaves the list",
          "Lena Haugen" in clean.read_text(clean.clean_path(con, "one.txt")) and not review(con, "Lena Haugen"))
    with con:
        _, terms = decisions.undo(con, did)
    con.close()
    clean.reclean_all(terms)
    con = clean.connect()
    check("Undo hides the name again", "Lena Haugen" not in clean.read_text(clean.clean_path(con, "one.txt")))
    check("...puts it back in Review names", review(con, "Lena Haugen") is not None)
    check("...and takes it off the fine-to-keep list", "Lena Haugen" not in clean.get_list(con, "allow"))
    check("...and keeps the owner's own name on the list", "Morgan Reyes" in clean.get_list(con, "allow"))
    try:
        with con:
            decisions.undo(con, did)
        check("the same decision can't be undone twice", False)
    except ValueError:
        check("the same decision can't be undone twice", True)

    # Which client: the answer lands in the re-check, so the log compares before the answer with after it.
    # The call is already clean (names hidden by default), so it must be re-checked, as /api/decide-group does.
    mike = review(con, "Mike")
    code = mike["candidates"].split(" or ")[1]
    with con:
        before = decisions.start(con)
        clean.set_decision(con, mike["id"], code)
    con.close()
    clean.reclean_all(["Mike"])
    con = clean.connect()
    with con:
        did = decisions.record(con, before, "which", "Mike is Mike Chen", "one.txt", ["Mike"])
    check("a Which client answer gives the call that client's code", code in clean.read_text(clean.clean_path(con, "one.txt")))
    with con:
        _, terms = decisions.undo(con, did)
    con.close()
    clean.reclean_all(terms)
    con = clean.connect()
    check("Undo brings the Which client question back", review(con, "Mike") is not None
          and code not in clean.read_text(clean.clean_path(con, "one.txt")))

    # Keep hidden, then Undo
    ruth = review(con, "Ruth Okafor")
    with con:
        before = decisions.start(con)
        con.execute("UPDATE review SET reviewed=1 WHERE id=?", (ruth["id"],))
        did = decisions.record(con, before, "keep_hidden", "Ruth Okafor stays hidden", "two.txt")
        decisions.undo(con, did)
    check("Undo of Keep hidden puts the name back in the list", review(con, "Ruth Okafor") is not None)

    # final check Leave it, then Undo
    with con:
        before = decisions.start(con)
        clean.final_ok(con, "two.txt", "Tidewater Freight")
        did = decisions.record(con, before, "final_ok", "Tidewater Freight shows in this call", "two.txt")
        decisions.undo(con, did)
    check("Undo of a final-check answer removes it",
          not con.execute("SELECT 1 FROM final_ok WHERE file='two.txt'").fetchone())

    # This is me: Undo restores the previous name
    with con:
        before = decisions.start(con)
        clean.set_setting(con, "owner_name", "Ruth Okafor")
        clean.add_to_list(con, "allow", "Ruth Okafor")
        did = decisions.record(con, before, "owner", "Your name is Ruth Okafor")
        decisions.undo(con, did)
    check("Undo of This is me restores the previous name and list",
          clean.get_setting(con, "owner_name") == "Morgan Reyes" and "Ruth Okafor" not in clean.get_list(con, "allow"))

    # nothing changed: nothing logged
    with con:
        before = decisions.start(con)
        check("a decision that changes nothing isn't logged", decisions.record(con, before, "keep", "x") is None)
    con.close()

    # a renamed call keeps its per-call decisions; a deleted call takes them with it, global ones stay
    con = clean.connect()
    with con:
        before = decisions.start(con)
        clean.final_ok(con, "two.txt", "Greenline Grocers")
        per_call = decisions.record(con, before, "final_ok", "Greenline Grocers shows in this call", "two.txt")
        before = decisions.start(con)
        clean.add_to_list(con, "allow", "Ruth Okafor")
        everywhere = decisions.record(con, before, "keep", "Ruth Okafor shows in every call")
    con.close()
    clean.rename_call("two.txt", "renamed.txt")
    con = clean.connect()
    with con:
        decisions.undo(con, per_call)
    check("Undo follows a renamed call", not con.execute("SELECT 1 FROM final_ok WHERE file='renamed.txt'").fetchone())
    with con:
        before = decisions.start(con)
        clean.final_ok(con, "renamed.txt", "Greenline Grocers")
        per_call = decisions.record(con, before, "final_ok", "Greenline Grocers shows in this call", "renamed.txt")
        clean.forget_call(con, "renamed.txt")
    ids = {d["id"] for d in decisions.recent(con)}
    check("deleting a call removes decisions about that call only", per_call not in ids and everywhere in ids)
    con.close()
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

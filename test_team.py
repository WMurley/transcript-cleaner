"""Your team: teammates and tools stay visible in every call, the list round-trips as plain text, and a
team list can never un-hide a saved client. Synthetic data only.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

VAULT = Path(tempfile.mkdtemp(prefix="tc-team-"))
os.environ["CLEANER_HOME"] = str(VAULT)
sys.path.insert(0, str(Path(__file__).parent))

import clean  # noqa: E402
import team  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


def body(con, file):
    return clean.read_text(clean.clean_path(con, file)).split("\n\n", 1)[1]


try:
    clean.init()
    con = clean.connect()
    with con:
        con.execute("INSERT INTO clients (code, full_name) VALUES ('C001', 'Jane Whitfield')")
    clean.run(texts=[
        ("standup.txt", "Morgan Reyes: Quick one. Priya Shah and Omar Haddad are joining.\nPriya Shah: Hi all. Omar, can you share?\n"
                        "Omar Haddad: Sure. Jane Whitfield signed, and Hermes ran the import overnight.\n"),
        ("other.txt", "Morgan Reyes: Nothing about anyone. The van schedule moved.\n"),
    ])
    check("before: unsure names are hidden", "Priya" not in body(con, "standup.txt") and "Omar" not in body(con, "standup.txt"))

    name, why = team.add_member(con, "Priya Shah")
    con.commit()
    clean.reclean_all(["Priya Shah"])
    text = body(con, "standup.txt")
    check("a teammate's full name and first name stay visible", name == "Priya Shah" and "Priya Shah" in text and "Hi all" in text)
    check("...and they leave the review list",
          not con.execute("SELECT 1 FROM review WHERE file='standup.txt' AND name LIKE 'Priya%' AND reviewed=0").fetchone())
    check("a saved client can't be added to the team", team.add_member(con, "jane whitfield")[0] == "" and "client" in team.add_member(con, "Jane Whitfield")[1])
    check("names that aren't names are refused", team.add_member(con, "C001")[0] == "" and team.add_member(con, "<b>x</b>")[0] == "")

    shared = team.export_text(con)
    check("the shared list is plain text: one name per line, tools marked", "Priya Shah" in shared.splitlines() and shared.startswith("#"))

    pasted = "# from Morgan\nOmar Haddad\n- Jane Whitfield\ntool: Hermes\n\nnot a name 123\n"
    pv = team.preview(con, pasted)
    st = {r["name"]: r["status"] for r in pv["rows"]}
    check("preview sorts new, already saved and client names, and saves nothing",
          st == {"Omar Haddad": "new", "Jane Whitfield": "client", "Hermes": "new"} and pv["skipped"] == ["not a name 123"]
          and "Omar Haddad" not in team.members(con))
    got = team.import_text(con, pasted)
    con.commit()
    clean.reclean_all(got["terms"])
    text = body(con, "standup.txt")
    check("importing adds the new teammate and tool", got["people"] == 1 and got["tools"] == 1 and "Omar Haddad" in text and "Hermes" in text)
    check("...and never un-hides the saved client", got["refused"] == ["Jane Whitfield"] and "Jane" not in text and "C001" in text)
    check("the JSON form is read too", {r["name"] for r in team.preview(con, '{"people": ["Lena Berg"], "tools": ["Gamma"]}')["rows"]} == {"Lena Berg", "Gamma"})

    team.remove_member(con, "Omar Haddad")
    con.commit()
    clean.reclean_all(["Omar Haddad"])
    check("removing a teammate hides them again", "Omar" not in body(con, "standup.txt") and "Priya Shah" in body(con, "standup.txt"))
    clean.set_setting(con, "owner_name", "Priya Lane")
    team.remove_member(con, "Priya Shah")
    con.commit()
    check("removing keeps a first name the member's own name still uses",
          "Priya" in clean.get_list(con, "allow") and "Priya Shah" not in clean.get_list(con, "allow"))
    con.close()
finally:
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

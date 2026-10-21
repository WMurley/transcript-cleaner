"""End-to-end test with synthetic transcripts only.

Builds a fresh vault in ./ClientVault-test from test-fixtures/ and test-calls/,
runs the cleaner, answers the review list like a member would (through the
same database the app uses), runs again, and checks every expected result.
"""
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / "ClientVault-test"
os.environ["CLEANER_HOME"] = str(VAULT)
if VAULT.exists():
    shutil.move(str(VAULT), str(HERE / f"_old-{VAULT.name}-{os.getpid()}"))
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)

sys.path.insert(0, str(HERE))
import clean  # noqa: E402  (reads CLEANER_HOME at import)

results = []


def check(label, ok):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + label)


def text(name):
    c = clean.connect()
    path = clean.clean_path(c, name)
    c.close()
    return path.read_text(encoding="utf-8")


# ---- pass 1
s1 = clean.run(paths=[HERE / "test-calls"])
print("pass 1:", {k: s1[k] for k in ("cleaned", "held", "replaced", "new_names", "ambiguous")},
      f"{s1['words']} words in {s1['secs']:.1f}s")
con = clean.connect()
review = con.execute("SELECT * FROM review").fetchall()
names = {(r["kind"], r["name"]) for r in review}
check("pass 1: two files clean, three held", s1["cleaned"] == 2 and s1["held"] == 3)
check("unlisted Derek Olsen held for review", ("unknown", "Derek Olsen") in names)
check("lowercase 'dana' held for review", ("unknown", "dana") in names)
check("bare 'mike' held as unclear (two clients named Mike)", ("ambiguous", "mike") in names)
check("unlisted company 'Olsen Builds' held for review", ("company", "Olsen Builds") in names)
check("no timestamps or extra noise in the review list", len(review) == 4)
k = text("zoom-2026-09-14-bluefern-kickoff.txt")
check("Jane, Janie, her email and phone all coded", all(x not in k for x in ("Jane", "Janie", "bluefernbakery", "214-8890"))
      and "C001-EMAIL" in k and "C001-PHONE" in k)
check("company coded (Bluefern -> O001)", "Bluefern" not in k and "O001" in k)
check("owner's own name kept", "Morgan Reyes" in k)
n = text("fathom-2026-09-18-northgate-checkin.txt")
check("two clients at one company keep separate codes", "C002" in n and "C004" in n and "O002" in n)
check("allowed public figure kept", "Simon Sinek" in n)
call = con.execute("SELECT codes FROM calls WHERE file='fathom-2026-09-18-northgate-checkin.txt'").fetchone()
check("call linked to its clients in the database", ",C002," in call["codes"] and ",C004," in call["codes"])

# ---- answer the review list like a member would
decisions = {"Derek Olsen": "client", "dana": "oneoff", "mike": "C003", "Olsen Builds": "company"}
for r in review:
    clean.set_decision(con, r["id"], decisions[r["name"]])
con.commit()
con.close()

# ---- pass 2
s2 = clean.run()
print("pass 2:", {k: s2[k] for k in ("cleaned", "held", "replaced", "decided")})
con = clean.connect()
check("pass 2: everything clean, nothing held", s2["held"] == 0 and len(list((VAULT / "clean").iterdir())) == 5)
check("review list empty", con.execute("SELECT COUNT(*) FROM review").fetchone()[0] == 0)
check("Derek Olsen added as new client C005",
      con.execute("SELECT 1 FROM clients WHERE code='C005' AND full_name='Derek Olsen'").fetchone() is not None)
h = text("fathom-2026-09-22-harbor-lane.txt")
check("Derek coded, his email intact as one placeholder", "Derek" not in h and "C005" in h and "EMAIL-1" in h and "@" not in h)
check("Mike Chen's known phone coded", "C003-PHONE" in h)
check("'Olsen Builds' coded as new company O004", "Olsen" not in h and "O004" in h)
g = text("zoom-2026-09-25-group-session.txt")
check("lowercase 'jane' and 'bluefern' coded", "jane" not in g.lower() and "O001" in g)
check("bare 'mike' resolved to C003 in that file", "mike" not in g.lower() and "C003" in g)
check("same unknown phone in two files -> same PHONE-1", "PHONE-1" in h and "PHONE-1" in g
      and con.execute("SELECT COUNT(*) FROM placeholders WHERE kind='PHONE'").fetchone()[0] == 1)
check("only one unknown email placeholder exists",
      con.execute("SELECT COUNT(*) FROM placeholders WHERE kind='EMAIL'").fetchone()[0] == 1)
nt = text("notes-2026-09-29-followups.md")
check("one-off 'dana' replaced with [PERSON]", "dana" not in nt.lower() and "[PERSON]" in nt)
check("every clean file starts with the 'cleaned locally' note",
      all(p.read_text(encoding="utf-8").startswith("[Cleaned locally") for p in (VAULT / "clean").iterdir()))
c3 = con.execute("SELECT COUNT(*) FROM calls WHERE codes LIKE '%,C003,%'").fetchone()[0]
check("Mike Chen (C003) linked to his three calls", c3 == 3)

# ---- add an alias later and re-clean everything from the originals
con.execute("UPDATE clients SET aliases='Pri' WHERE code='C004'")
con.commit()
con.close()
s3 = clean.reclean_all()
check("re-clean from originals: all five still clean", s3["cleaned"] == 5 and s3["held"] == 0)

# ---- what was removed, per call
import json  # noqa: E402
con = clean.connect()
rem = json.loads(con.execute("SELECT removed FROM calls WHERE file='zoom-2026-09-14-bluefern-kickoff.txt'").fetchone()["removed"])
check("'what was removed' tallies the Bluefern call (people, company, email, phone)",
      rem["people"] >= 4 and rem["companies"] == 2 and rem["emails"] == 1 and rem["phones"] == 1)

# ---- common first names: "John" only becomes John Smith when the call confirms it
clean.add_client(con, "John Smith", company_code="O003")
con.commit()
con.close()
(VAULT / "dirty" / "call-john-alone.txt").write_text("Morgan Reyes: John said the budget is approved.\n", encoding="utf-8")
(VAULT / "dirty" / "call-john-harbor.txt").write_text(
    "Morgan Reyes: John from Harbor Lane said the budget is approved.\n", encoding="utf-8")
clean.run()
con = clean.connect()
q = con.execute("SELECT * FROM review WHERE file='call-john-alone.txt'").fetchall()
check("a bare 'John' with nothing else to go on is held: 'Is this John Smith?'",
      len(q) == 1 and q[0]["kind"] == "ambiguous" and q[0]["candidates"] == "C006")
check("'John from Harbor Lane' is confirmed by his company and coded",
      "C006" in text("call-john-harbor.txt") and "John" not in text("call-john-harbor.txt"))
clean.set_decision(con, q[0]["id"], "person")  # "Someone else"
con.commit()
con.close()
clean.run()
check("answering 'Someone else' hides the name without calling him a client",
      "[PERSON]" in text("call-john-alone.txt") and "C006" not in text("call-john-alone.txt"))

# ---- the output folder: clean copies land where you choose, never the originals
out = VAULT.parent / f"_library-{os.getpid()}"
out.mkdir()
con = clean.connect()
clean.set_setting(con, "output_dir", str(out))
clean.set_setting(con, "review_before_export", "0")  # test the optional automatic delivery mode
con.commit()
con.close()
check("existing clean calls can be sent to the output folder", clean.deliver_all() == 7)
(VAULT / "dirty" / "call-new.txt").write_text("Morgan Reyes: Quick note for Priya Nair.\n", encoding="utf-8")
s4 = clean.run()
c = clean.connect()
new_export = out / clean.clean_path(c, "call-new.txt").name
c.close()
check("a newly cleaned call lands in the output folder by itself", s4["delivered"] == 1 and new_export.exists()
      and "Priya" not in new_export.read_text(encoding="utf-8"))
check("nothing raw ever reaches the output folder",
      all(p.read_text(encoding="utf-8").startswith("[Cleaned locally") for p in out.iterdir()))

# ---- change a past answer: forget the one-off "dana", and that call asks again
con = clean.connect()
clean.forget_answer(con, "oneoff", "dana")
con.commit()
con.close()
s5 = clean.reclean_all()
con = clean.connect()
check("forgetting a past answer re-asks it", s5["held"] == 1 and
      con.execute("SELECT 1 FROM review WHERE name='dana'").fetchone() is not None)
con.close()

# ---- file names: nothing hidden in a call survives in its clean copy's file name
con = clean.connect()
names = {r["file"]: r["clean_name"] for r in con.execute("SELECT file, clean_name FROM calls WHERE status='clean'")}
con.close()
import re
check("exports use a neutral ID independent of the original title",
      all(re.fullmatch(r"call-[a-f0-9]{32}\.(txt|md|vtt|srt)", n) for n in names.values()))
check("different calls keep distinct neutral export names", len(set(names.values())) == len(names))
check("no clean file name contains a client or company name",
      not any(w in n.lower() for n in names.values() for w in ("bluefern", "harbor", "northgate", "derek", "olsen", "jane", "mike")))
check("the clean folder holds only cleaned names", all(p.name in names.values() for p in (VAULT / "clean").iterdir()))

# ---- choose what to hide: keep companies visible, then keep people visible
def set_hide(**kw):
    c = clean.connect()
    clean.set_setting(c, "hide", json.dumps({**clean.HIDE_DEFAULT, **kw}))
    c.commit()
    c.close()
    return clean.reclean_all()


set_hide(companies=False)
k = text("zoom-2026-09-14-bluefern-kickoff.txt")
con = clean.connect()
row = con.execute("SELECT codes, removed, clean_name FROM calls WHERE file='zoom-2026-09-14-bluefern-kickoff.txt'").fetchone()
con.close()
check("companies switched off: 'Bluefern' stays, Jane is still C001",
      "Bluefern" in k and "O001" not in k and "Jane" not in k and "C001" in k)
check("companies switched off: the call is still linked to O001 and counts no companies removed",
      ",O001," in row["codes"] and json.loads(row["removed"])["companies"] == 0)
check("companies switched off: the clean copy says what was hidden", "Hidden: names, emails and phone numbers" in k)
check("companies switched off: export names remain neutral", "bluefern" not in row["clean_name"])
s6 = set_hide(people=False)
k = text("zoom-2026-09-14-bluefern-kickoff.txt")
con = clean.connect()
row = con.execute("SELECT codes FROM calls WHERE file='zoom-2026-09-14-bluefern-kickoff.txt'").fetchone()
waiting = con.execute("SELECT COUNT(*) FROM review WHERE kind IN ('unknown', 'ambiguous')").fetchone()[0]
con.close()
check("people switched off: names stay, companies are coded, call still linked to C001",
      "Jane" in k and "O001" in k and ",C001," in row["codes"])
check("people switched off: no call is held for an unknown person", waiting == 0 and s6["held"] == 0)
set_hide()
check("everything back on: names hidden again", "Jane" not in text("zoom-2026-09-14-bluefern-kickoff.txt"))

# ---- noise: tools, abbreviations and ordinary words are never questions; a real new person still is
(clean.DIRTY / "call-noise.txt").write_text(
    "[00:00:02] Morgan Reyes: So the LLM drafts it, then we track it on the Kanban board.\n"
    "[00:00:09] Morgan Reyes: Push it to GitHub, log it in Notion, and the API does the rest.\n"
    "[00:00:15] Morgan Reyes: Obsidian keeps the notes, n8n runs the Zapier replacement, SOPs live in Airtable.\n"
    "[00:00:21] Morgan Reyes: Our kanban columns are simple. Talk Monday.\n"
    "[00:00:30] Morgan Reyes: Oh, and Theo Marchetti from Lindqvist Partners wants an intro.\n", encoding="utf-8")
clean.run()
con = clean.connect()
asked = {(r["kind"], r["name"]) for r in con.execute("SELECT kind, name FROM review WHERE file='call-noise.txt'")}
con.close()
noisy = {"LLM", "Kanban", "GitHub", "Notion", "API", "Obsidian", "n8n", "Zapier", "SOPs", "Airtable", "Monday"}
check("tools, abbreviations and ordinary words are not asked about",
      not any(n in noisy for _, n in asked))
check("a real new person in the same call still is ('Theo Marchetti')", ("unknown", "Theo Marchetti") in asked)
check("an unlisted company in the same call still is ('Lindqvist Partners')", ("company", "Lindqvist Partners") in asked)

# ---- move the private files to a folder the member picks
before = len(list((VAULT / "raw").iterdir()))
import tempfile  # noqa: E402
new_home = Path(tempfile.mkdtemp(prefix="tc-moved-vault-")) / "TranscriptCleaner-Vault"
clean.move_vault(new_home)
check("the vault moves to the chosen folder and the app follows it",
      clean.HOME == new_home and len(list((new_home / "raw").iterdir())) == before and not (VAULT / "raw").exists())
con = clean.connect()
check("the moved database still knows every client and call",
      con.execute("SELECT COUNT(*) FROM clients").fetchone()[0] >= 6 and con.execute("SELECT COUNT(*) FROM calls").fetchone()[0] >= 8)
con.close()
try:
    clean.move_vault(HERE / "inside-app")
    check("a folder inside the app is refused", False)
except ValueError:
    check("a folder inside the app is refused", True)

shutil.rmtree(out, ignore_errors=True)  # the test's own output folder; nothing else lives there
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)

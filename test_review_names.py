"""Safe by default: unsure names are hidden behind stand-ins (one per name, the same in every call) and listed for
review; nothing blocks a call.

Also: speakers and mention counts, tool-like names (Claude), "works at" companies, the strict mode, and
re-checking only the calls a change can affect. Synthetic data only.
"""
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-reviewnames-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
os.environ.pop("CLEANER_HOLD_UNKNOWN", None)
sys.path.insert(0, str(HERE))
import clean  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


def body(con, file):
    return clean.read_text(clean.clean_path(con, file)).split("\n\n", 1)[1]


try:
    s = clean.run(texts=[
        ("referral.txt", "[00:00:02] Morgan Reyes: Mike Chen, good to see you.\n"
                         "[00:00:05] Mike Chen: Before we start, Derek Olsen from Olsen Builds referred someone. Derek is great.\n"),
        ("two-people.txt", "Morgan Reyes: Thanks for joining, Taylor.\nTaylor Brooks: Happy to. Taylor Brooks here from the ops side.\n"
                           "Morgan Reyes: Rowan Pike said the same. Rowan Pike will join next week. She works at Cedar Health now.\n"),
        ("tools.txt", "Morgan Reyes: I set up Claude Code and Claude wrote the script. Hermes runs it nightly.\n"),
        ("claude-person.txt", "Morgan Reyes: Hi Claude, thanks for joining.\nClaude: Happy to be here. Claude's company signed the lease.\n"),
        ("unrelated.txt", "Morgan Reyes: Nothing to see. We talked about the van schedule.\n"),
        ("greeting.txt", "Morgan Reyes: Hi, this is the ops line. Hey everyone, this works. Hi Priya, good to see you.\n"),
        ("tool-people.txt", "Morgan Reyes: Claude from accounting called back. He wants the PO number.\n"
                            "Morgan Reyes: Jasper said his team can install the cabinets next week.\n"),
        ("tool-it.txt", "Morgan Reyes: Lindy books the meetings, then it emails a summary. We pay for Claude Max too.\n"),
    ])
    con = clean.connect()
    check("nothing is held: every call is clean straight away", s["held"] == 0 and {r["status"] for r in con.execute("SELECT status FROM calls")} == {"clean"})
    ref = body(con, "referral.txt")
    tok = lambda name: con.execute("SELECT token FROM standins WHERE name=?", (name,)).fetchone()["token"]
    derek, olsen = tok("derek olsen"), tok("olsen builds")  # numbers depend on cleaning order; one per name
    check("a person and their company in one sentence get separate stand-ins (the company's short form doesn't split the name)",
          f"{derek} from {olsen}" in ref and "Olsen" not in ref and derek.startswith("PERSON-") and olsen.startswith("COMPANY-"))
    check("a bare first name follows the hidden full name", f"{derek} is great" in ref)
    header = clean.read_text(clean.clean_path(con, "referral.txt")).split("\n\n", 1)[0]
    check("the clean copy's header names no real code (Put names back would fill it in)",
          "PERSON and COMPANY codes" in header and not re.search(r"(PERSON|COMPANY)-\d", header))
    rows = {r["name"]: dict(r) for r in con.execute("SELECT * FROM review WHERE file='two-people.txt'")}
    check("each unsure name is listed with its stand-in and how often it's mentioned",
          rows["Rowan Pike"]["token"].startswith("PERSON-") and rows["Rowan Pike"]["mentions"] == 2)
    check("someone speaking on the call is marked as a speaker", rows["Taylor Brooks"]["speaker"] == 1 and rows["Rowan Pike"]["speaker"] == 0)
    check("'works at' catches a company without a telltale suffix", "Cedar Health" in rows and "Cedar Health" not in body(con, "two-people.txt"))
    tools = body(con, "tools.txt")
    check("tool-like names stay visible when the call talks about the tools", "Claude Code" in tools and "Hermes" in tools)
    check("...and are listed as kept tools, so a real person by that name is one click away",
          {r["name"] for r in con.execute("SELECT name FROM review WHERE file='tools.txt' AND kind='tool'")} >= {"Claude", "Hermes"})
    person = body(con, "claude-person.txt")
    check("a Claude greeted and speaking on the call is a person, and is hidden", "Claude" not in person and re.search(r"PERSON-\d+", person))
    check("a call with no unsure names has nothing to review",
          not con.execute("SELECT 1 FROM review WHERE file='unrelated.txt'").fetchone())
    greet = body(con, "greeting.txt")
    check("'Hi, this is' and 'Hey everyone' never turn ordinary words into names",
          greet.count("this") == 2 and "everyone" in greet and "Priya" not in greet)
    tp = body(con, "tool-people.txt")
    check("a tool-like name used for a person ('from accounting', he/his) is hidden, even when the detector missed it",
          "Claude" not in tp and "Jasper" not in tp)
    check("...while a tool referred to as 'it' stays visible", "Lindy" in body(con, "tool-it.txt") and "Claude Max" in body(con, "tool-it.txt"))

    # keep hidden survives re-cleaning
    rid = rows["Rowan Pike"]["id"]
    con.execute("UPDATE review SET reviewed=1 WHERE id=?", (rid,))
    con.commit()
    clean.reclean_all()
    check("'Keep hidden' sticks when calls are cleaned again",
          con.execute("SELECT reviewed FROM review WHERE file='two-people.txt' AND name='Rowan Pike'").fetchone()["reviewed"] == 1)
    check("stand-ins stay the same when a call is cleaned again", f"{derek} from {olsen}" in body(con, "referral.txt"))

    # the member's own name stays visible
    clean.add_to_list(con, "allow", "Taylor Brooks")
    con.commit()
    clean.reclean_all(["Taylor Brooks"])
    check("a name marked fine to show comes back as written", "Taylor Brooks here" in body(con, "two-people.txt"))

    # re-checking only the calls a change can affect
    before = {r["file"]: r["updated"] for r in con.execute("SELECT file, updated FROM calls")}
    import time
    time.sleep(1.1)
    s2 = clean.reclean_all(["Derek Olsen"])
    after = {r["file"]: r["updated"] for r in con.execute("SELECT file, updated FROM calls")}
    changed = {f for f in after if after[f] != before[f]}
    check("a change re-checks only the calls that mention it", changed == {"referral.txt"} and s2["cleaned"] == 1)

    # the strict mode still holds calls
    clean.set_setting(con, "hold_unknown", "1")
    con.commit()
    s3 = clean.reclean_all()
    check("strict mode: calls with unsure names wait until answered",
          con.execute("SELECT status FROM calls WHERE file='referral.txt'").fetchone()["status"] == "held"
          and con.execute("SELECT status FROM calls WHERE file='unrelated.txt'").fetchone()["status"] == "clean")
    clean.set_setting(con, "hold_unknown", "0")
    con.commit()
    clean.reclean_all()
    check("turning strict mode off releases them with stand-ins",
          con.execute("SELECT status FROM calls WHERE file='referral.txt'").fetchone()["status"] == "clean")
    check("stand-ins are never flagged by the final check",
          not any(re.match(r"(PERSON|COMPANY)-\d", i["phrase"]) for i in clean.final_check(con, "referral.txt")))

    # one code per name, the same in every call (Wade, 10-21: "why would every single person be person one?")
    import restore
    answer = f"Hi {derek}, thanks for sending {olsen} over."
    back = "".join(s["text"] for s in restore.restore(con, answer))
    check("Put names back fills stand-ins without asking which call", back == "Hi Derek, thanks for sending Olsen Builds over.")
    con.close()
    clean.run(texts=[("second-derek.txt", "Morgan Reyes: Derek Olsen called again. Quinn Abara joined too.\n")])
    con = clean.connect()
    tokens = {r["file"]: r["token"] for r in con.execute("SELECT file, token FROM standins WHERE name='derek olsen'")}
    check("the same name gets the same stand-in in every call", tokens.get("referral.txt") == tokens.get("second-derek.txt") == derek)
    quinn = con.execute("SELECT token FROM standins WHERE name='quinn abara'").fetchone()["token"]
    taken = {r["token"] for r in con.execute("SELECT token FROM standins WHERE name != 'quinn abara'")}
    check("a new name gets a number no one else has", quinn.startswith("PERSON-") and quinn not in taken)
    con.close()
    clean.delete_call("second-derek.txt")
    clean.run(texts=[("third.txt", "Morgan Reyes: Imani Okoro sent the plans.\n")])
    con = clean.connect()
    imani = con.execute("SELECT token FROM standins WHERE name='imani okoro'").fetchone()["token"]
    check("a deleted call's numbers are never given to someone new", imani != quinn
          and int(imani.split("-")[1]) > int(quinn.split("-")[1]))

    # a vault from before 10-21 numbered stand-ins per call: the first open renumbers it once
    con.execute("DELETE FROM standins")
    con.execute("DELETE FROM settings WHERE key IN ('standins_global', 'standin_last_person', 'standin_last_company')")
    con.executemany("INSERT INTO standins (file, name, kind, token) VALUES (?,?,?,?)",
                    [("referral.txt", "derek olsen", "person", "PERSON-1"), ("third.txt", "imani okoro", "person", "PERSON-1")])
    con.commit()
    con.close()
    clean.init()
    con = clean.connect()
    check("an old vault's per-call codes are cleared and its calls queued once",
          not con.execute("SELECT 1 FROM standins").fetchone() and (clean.DIRTY / "referral.txt").exists()
          and clean.get_setting(con, "standins_global") == "1")
    con.close()
    clean.run()
    con = clean.connect()
    old = {r["name"]: r["token"] for r in con.execute("SELECT name, token FROM standins WHERE name IN ('derek olsen', 'imani okoro')")}
    check("...and after cleaning, two different people no longer share PERSON-1", len(old) == 2 and len(set(old.values())) == 2
          and old["derek olsen"] in body(con, "referral.txt") and old["imani okoro"] in body(con, "third.txt"))
    con.close()
finally:
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

"""A bare short form of an unsure company follows the company's stand-in instead of becoming a new person.
Found on Wade's MacBook (10-21): the guided tutorial's "Bluefern will send the notes" made "Bluefern" PERSON-2
next to "Bluefern Bakery" COMPANY-1. Uses the tutorial's own sample in a fresh vault with nothing saved."""
import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="tc-shortforms-"))
os.environ["CLEANER_HOME"] = str(TMP / "vault")
os.environ.pop("CLEANER_HOLD_UNKNOWN", None)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean  # noqa: E402  (reads CLEANER_HOME at import)
from app import TUTORIAL_SAMPLE  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + label)


try:
    clean.init()
    con = clean.connect()
    with con:
        clean.add_to_list(con, "allow", "Morgan Reyes")
    con.close()
    clean.run(texts=[("guided-first-call.txt", TUTORIAL_SAMPLE)])
    con = clean.connect()
    text = clean.read_text(clean.clean_path(con, "guided-first-call.txt")).split("\n\n", 1)[1]
    company = con.execute("SELECT token FROM standins WHERE name='bluefern bakery'").fetchone()
    check("the company gets a stand-in", company is not None)
    check("a bare 'Bluefern' is not made a person", not con.execute("SELECT 1 FROM standins WHERE name='bluefern'").fetchone()
          and not con.execute("SELECT 1 FROM review WHERE name='Bluefern' AND kind='unknown'").fetchone())
    check("...it follows the company's stand-in instead", company and f"{company['token']} will send the notes" in text)
    check("nothing of the name is left visible", "bluefern" not in text.lower())
    check("the person in the same call still gets their own stand-in",
          con.execute("SELECT token FROM standins WHERE name='derek olsen'").fetchone()["token"].startswith("PERSON-"))
    con.close()
finally:
    shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

"""Put names back: codes in an agent's answer become real names, emails and phones. Synthetic only."""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-restore-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
sys.path.insert(0, str(HERE))
import clean  # noqa: E402
import restore  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


def plain(con, text):
    return "".join(s["text"] for s in restore.restore(con, text))


try:
    # a real cleaning run, so one-off contacts get EMAIL-n / PHONE-n codes the way they do in use
    clean.run(texts=[("restore-call.txt", "Morgan Reyes: Jane Whitfield from Bluefern Bakery confirmed. "
                                          "Her assistant is at ops@frontdesk.example and 555-909-1212.\n")])
    con = clean.connect()
    cleaned = clean.read_text(clean.clean_path(con, "restore-call.txt"))
    email_code = next(t for t in cleaned.split() if t.startswith("EMAIL-")).strip(".,")
    phone_code = next(t for t in cleaned.replace(".", " ").split() if t.startswith("PHONE-")).strip(".,")
    out = plain(con, f"Hi C001, thanks for the update on O001's van schedule. I'll send C001 the proposal at C001-EMAIL.")
    check("a greeting gets the first name; elsewhere the full name; companies and possessives read naturally",
          out == "Hi Jane, thanks for the update on Bluefern Bakery's van schedule. I'll send Jane Whitfield the proposal at jane@bluefernbakery.com.")
    check("a saved phone comes back formatted", plain(con, "Call C001-PHONE.") == "Call (555) 214-8890.")
    check("one-off contacts the cleaner replaced come back too",
          plain(con, f"Loop in {email_code} or {phone_code}.") == "Loop in ops@frontdesk.example or (555) 909-1212.")
    segs = restore.restore(con, "Thanks C001. Ask C099 and [PERSON] about it, and Dear C003,")
    codes = [s for s in segs if "code" in s]
    check("each code is reported: restored, not saved (C099), or hidden without a record ([PERSON])",
          [s["status"] for s in codes] == ["restored", "unknown", "hidden", "restored"] and codes[1]["text"] == "C099" and codes[2]["text"] == "[PERSON]")
    check("'Thanks' and 'Dear' count as greetings", codes[0]["text"] == "Jane" and codes[3]["text"] == "Mike")
    check("codes inside other words are left alone", plain(con, "Order AC001 and C0012 and XO001.") == "Order AC001 and C0012 and XO001.")
    check("plain text with no codes comes back unchanged", plain(con, "Nothing to restore here.") == "Nothing to restore here.")
    con.close()
finally:
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

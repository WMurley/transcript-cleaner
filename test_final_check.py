"""The final check before export: leftovers in a clean copy are flagged; codes, weekdays and ordinary words aren't.

Synthetic only. A clean copy is cleaned for real, then leftovers are planted in it to stand in for detector misses.
"""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-finalcheck-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
sys.path.insert(0, str(HERE))
import clean  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


try:
    clean.run(texts=[("check-call.txt", "Morgan Reyes: Jane Whitfield confirmed the Bluefern Bakery order for Friday.\n"
                                        "Morgan Reyes: Great. I'll send the invoice on Monday.\n")])
    con = clean.connect()
    row = con.execute("SELECT status FROM calls WHERE file='check-call.txt'").fetchone()
    check("the sample call cleans", row and row["status"] == "clean")
    path = clean.clean_path(con, "check-call.txt")
    base = clean.read_text(path)
    check("a properly cleaned copy passes the check", clean.final_check(con, "check-call.txt") == [])
    planted = base + ("\nMorgan Reyes: Also, Jane said to copy jane.w@bluefernbakery.com and call 555-214-8890.\n"
                      "Morgan Reyes: The quote from Tidewater Freight came in on Tuesday. C001 and O001 agreed.\n"
                      "# Follow-ups from this week\n- Send C001 the checklist.\n* Ask the print shop about menus.\n"
                      "2. Read the next chapter.\n- Odile Brandt wants the quote by Friday.\n")
    path.write_text(planted, encoding="utf-8")
    items = {i["phrase"]: i for i in clean.final_check(con, "check-call.txt")}
    kinds = {p: i["kind"] for p, i in items.items()}
    check("a saved client's first name left in the copy is flagged as saved", kinds.get("Jane") == "saved")
    check("a leftover email address is flagged", kinds.get("jane.w@bluefernbakery.com") == "contact")
    check("a leftover phone number is flagged", kinds.get("555-214-8890") == "contact")
    check("an unknown company the detector missed is flagged as a maybe", kinds.get("Tidewater Freight") == "maybe")
    check("codes, weekdays, the member and ordinary sentence starts are not flagged",
          not any(p in items for p in ("C001", "O001", "Tuesday", "Monday", "Friday", "Morgan Reyes", "Morgan", "Also", "The", "Great")))
    check("ordinary words starting a list item or heading are not flagged (Follow, Send, Ask, Read)",
          not any(p in items for p in ("Follow", "Send", "Ask", "Read")))
    check("...but a full name starting a list item still is", kinds.get("Odile Brandt") == "maybe")
    check("each item shows where it is", items.get("Tidewater Freight", {}).get("match") == "Tidewater Freight"
          and "quote from" in items["Tidewater Freight"]["before"])
    clean.final_ok(con, "check-call.txt", "Tidewater Freight")
    con.commit()
    left = {i["phrase"] for i in clean.final_check(con, "check-call.txt")}
    check("'It's fine here' clears that phrase for this call only", "Tidewater Freight" not in left and "Jane" in left)
    clean.set_setting(con, "hide", '{"people": true, "companies": true, "emails": false, "phones": false}')
    con.commit()
    left = {i["phrase"] for i in clean.final_check(con, "check-call.txt")}
    check("contacts you chose to keep visible (What to hide) aren't flagged",
          "jane.w@bluefernbakery.com" not in left and "555-214-8890" not in left)
    con.close()
finally:
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

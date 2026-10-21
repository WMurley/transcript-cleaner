"""Adding clients without typing: pasted lists and CSV exports, company guesses, and invite suggestions. Synthetic only."""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-intake-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
sys.path.insert(0, str(HERE))
import clean  # noqa: E402
import intake  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


try:
    clean.init()
    con = clean.connect()
    # --- reading lists ---
    plain = intake.parse("Rosa Delgado, Tidewater Freight, rosa@tidewaterfreight.com, 555-410-2290\nSam Ito\n")
    check("a plain pasted list: name, company, email, phone in any order of cells",
          plain[0] == {"name": "Rosa Delgado", "company": "Tidewater Freight", "email": "rosa@tidewaterfreight.com", "phone": "555-410-2290"}
          and plain[1]["name"] == "Sam Ito")
    google = intake.parse('First Name,Middle Name,Last Name,Organization Name,Organization Title,E-mail 1 - Label,E-mail 1 - Value,Phone 1 - Value\n'
                          'Rosa,,Delgado,Tidewater Freight,Owner,* Work,rosa@tidewaterfreight.com,(555) 410-2290\n')
    check("a Google Contacts export: first + last joined, title and label columns ignored",
          google == [{"name": "Rosa Delgado", "company": "Tidewater Freight", "email": "rosa@tidewaterfreight.com", "phone": "(555) 410-2290"}])
    sheets = intake.parse("Name\tCompany\tEmail\nOmar Haddad\tCedar Labs\tomar@cedarlabs.io\n")
    check("a paste from Google Sheets or Excel (tab-separated with a header)",
          sheets == [{"name": "Omar Haddad", "company": "Cedar Labs", "email": "omar@cedarlabs.io", "phone": ""}])
    semi = intake.parse("Full name;Company;Email\nLena Berg;Nordlys AS;lena@nordlys.no\n")
    check("a semicolon CSV (European Excel)", semi[0]["name"] == "Lena Berg" and semi[0]["email"] == "lena@nordlys.no")
    check("an email-only line gets a name guessed from the address",
          intake.parse("first.last@acme.com")[0]["name"] == "First Last")
    # --- company guesses ---
    check("personal mail services suggest no company", intake.company_from_email(con, "rosa@gmail.com") == ("", ""))  # public-ok: invented address
    check("a domain matching a saved company links to it", intake.company_from_email(con, "pat@bluefernbakery.com")[1] == "O001")
    check("a new domain becomes a readable company name", intake.company_from_email(con, "rosa@tidewaterfreight.com") == ("Tidewater Freight", ""))
    check("country domains are read correctly", intake.company_from_email(con, "a@harbourhomes.co.uk")[0] == "Harbour Homes")
    # --- preview and save ---
    rows = intake.preview(con, intake.parse("Jane Whitfield, Bluefern Bakery, jane@bluefernbakery.com\n"
                                            "Rosa Delgado, , rosa@tidewaterfreight.com\n, Nameless Co, x@nameless.co\n"))
    check("preview marks saved, new and nameless rows, and fills a missing company from the email",
          [r["status"] for r in rows] == ["saved", "new", "no-name"] and rows[1]["company"] == "Tidewater Freight"
          and rows[2]["company"] == "Nameless Co")
    rows = intake.preview(con, [{"name": "", "company": "Nameless Co", "email": ""}])
    check("a row with no name and no email can't be saved", rows[0]["status"] == "no-name")
    codes = intake.save(con, intake.parse("Rosa Delgado, Tidewater Freight, rosa@tidewaterfreight.com\n"
                                          "Priya Shah, Bluefern Bakery, priya@bluefernbakery.com\nJane Whitfield, Bluefern Bakery\n"))
    con.commit()
    saved = {r["full_name"]: dict(r) for r in con.execute("SELECT * FROM clients")}
    check("saving creates new people only (Jane already exists)", len(codes) == 2 and "Rosa Delgado" in saved and "Priya Shah" in saved)
    check("a new company is created, and an existing one is reused",
          saved["Priya Shah"]["company_code"] == "O001" and saved["Rosa Delgado"]["company_code"] not in ("", "O001"))
    # --- suggestions from meeting invites ---
    added = intake.suggest(con, [{"name": "Omar Haddad", "email": "omar@cedarlabs.io"},
                                 {"name": "Rosa Delgado", "email": "rosa@tidewaterfreight.com"},
                                 {"name": "Morgan Reyes", "email": "morgan@example.com"},
                                 {"name": "Teammate", "email": "pat@myagency.com", "external": False},
                                 {"name": "", "email": "lena.berg@nordlys.no"}], "granola-2026-10-01-x.txt")
    pend = {p["email"]: p for p in intake.pending(con)}
    check("invitees already saved, on your keep list, or inside your own workspace aren't suggested",
          added == 2 and set(pend) == {"omar@cedarlabs.io", "lena.berg@nordlys.no"})
    check("a suggestion carries a guessed company and a name from the address when the invite had none",
          pend["omar@cedarlabs.io"]["company"] == "Cedar Labs" and pend["lena.berg@nordlys.no"]["name"] == "Lena Berg")
    intake.dismiss(con, ["lena.berg@nordlys.no"])
    again = intake.suggest(con, [{"name": "Lena Berg", "email": "lena.berg@nordlys.no"}], "next.txt")
    check("someone you said isn't a client isn't suggested again", again == 0 and len(intake.pending(con)) == 1)
    intake.save(con, [{"name": "Omar Haddad", "company": "Cedar Labs", "email": "omar@cedarlabs.io"}])
    check("saving a suggestion clears it from the list", intake.pending(con) == [])
    con.close()
finally:
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

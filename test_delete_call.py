"""Deleting a call clears its stand-ins, final-check approvals and waiting invite suggestions but keeps saved contacts;
renaming carries them along. Synthetic only."""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VAULT = HERE / f"ClientVault-delete-{os.getpid()}"
(VAULT / "private").mkdir(parents=True)
for f in ("clients.csv", "companies.csv", "allow.txt"):
    shutil.copy(HERE / "test-fixtures" / f, VAULT / "private" / f)
os.environ["CLEANER_HOME"] = str(VAULT)
os.environ.pop("CLEANER_HOLD_UNKNOWN", None)
sys.path.insert(0, str(HERE))
import clean  # noqa: E402
import intake  # noqa: E402
import restore  # noqa: E402

ok = []


def check(label, cond):
    ok.append(bool(cond))
    print(("PASS  " if cond else "FAIL  ") + label)


def rows(con, table, file):
    return con.execute(f"SELECT COUNT(*) FROM {table} WHERE file=?", (file,)).fetchone()[0]


CALL = "Morgan Reyes: I spoke with Theo Castellanos yesterday. Theo Castellanos wants the order moved to Thursday. Reach him at theo@castellanos.example.\n"

try:
    clean.run(texts=[("sync-a.txt", CALL), ("sync-b.txt", CALL)])
    con = clean.connect()
    clean.final_ok(con, "sync-a.txt", "Thursday")
    intake.suggest(con, [{"name": "Wren Abbott", "email": "wren@pending.example"},
                         {"name": "Ivo Lund", "email": "ivo@turned-down.example"},
                         {"name": "Ash Moreno", "email": "ash@both.example"}], "sync-a.txt")
    intake.suggest(con, [{"name": "Ash Moreno", "email": "ash@both.example"}], "sync-b.txt")  # on both calls' invites
    intake.dismiss(con, ["ivo@turned-down.example"])
    con.commit()
    clients_before = con.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    placeholders_before = con.execute("SELECT COUNT(*) FROM placeholders").fetchone()[0]
    check("setup: the call has stand-ins, a final-check approval and invite suggestions",
          rows(con, "standins", "sync-a.txt") and rows(con, "final_ok", "sync-a.txt") and rows(con, "suggested_people", "sync-a.txt") == 3)
    con.close()

    clean.delete_call("sync-a.txt")
    con = clean.connect()
    check("delete clears the call's stand-ins, so Put names back no longer lists it", rows(con, "standins", "sync-a.txt") == 0)
    check("delete clears the call's final-check approvals", rows(con, "final_ok", "sync-a.txt") == 0)
    check("invite suggestions still waiting from that call go with it",
          not con.execute("SELECT 1 FROM suggested_people WHERE email='wren@pending.example'").fetchone())
    check("someone also on another call's invite stays suggested, now pointing at that call",
          con.execute("SELECT status, file FROM suggested_people WHERE email='ash@both.example'").fetchone()[:] == ("", "sync-b.txt"))
    check("a suggestion already turned down stays turned down",
          con.execute("SELECT status FROM suggested_people WHERE email='ivo@turned-down.example'").fetchone()[0] == "dismissed")
    check("contacts stay: saved clients and the EMAIL-n / PHONE-n codes are untouched",
          con.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == clients_before
          and con.execute("SELECT COUNT(*) FROM placeholders").fetchone()[0] == placeholders_before > 0)
    segs = restore.restore(con, "PERSON-1 said yes.")
    check("a stand-in another call still uses still turns back into its name (one code per name)", segs[0]["text"] == "Theo Castellanos")
    check("the other call keeps its stand-ins", rows(con, "standins", "sync-b.txt") > 0)
    token = con.execute("SELECT token FROM standins WHERE file='sync-b.txt'").fetchone()[0]
    con.close()

    clean.rename_call("sync-b.txt", "sync-renamed.txt")
    con = clean.connect()
    check("rename moves the stand-ins with the call", rows(con, "standins", "sync-b.txt") == 0
          and con.execute("SELECT token FROM standins WHERE file='sync-renamed.txt'").fetchone()[0] == token)
    check("the renamed call still restores its stand-in",
          restore.restore(con, f"{token} said yes.")[0]["text"] == "Theo Castellanos")
    check("rename moves the invite suggestions' source with the call",
          [tuple(r) for r in con.execute("SELECT file FROM suggestion_sources WHERE email='ash@both.example'")] == [("sync-renamed.txt",)])

    # a vault from before suggestions knew every call: the first open records each waiting one's call
    con.execute("DELETE FROM suggestion_sources")
    con.execute("INSERT INTO suggested_people (email, name, company, company_code, file, status, added) "
                "VALUES ('old@legacy.example', 'Old Invitee', '', '', 'old-gone.txt', '', '')")
    con.commit()
    con.close()
    con = clean.connect()
    check("an older vault's suggestions get their call recorded on first open",
          {tuple(r) for r in con.execute("SELECT email, file FROM suggestion_sources")}
          == {("ash@both.example", "sync-renamed.txt"), ("old@legacy.example", "old-gone.txt")})

    # leftovers from calls deleted by an older version, and a call still waiting to be cleaned
    con.execute("INSERT INTO standins (file, name, kind, token) VALUES ('old-gone.txt', 'someone', 'person', 'PERSON-1')")
    con.execute("INSERT INTO final_ok (file, phrase) VALUES ('old-gone.txt', 'Thursday')")
    con.execute("INSERT INTO standins (file, name, kind, token) VALUES ('queued.txt', 'someone', 'person', 'PERSON-1')")
    (clean.DIRTY / "queued.txt").write_text("Morgan Reyes: hello.\n", encoding="utf-8")
    con.commit()
    con.close()
    clean.forget_deleted()
    con = clean.connect()
    check("startup clears leftovers of calls deleted earlier", rows(con, "standins", "old-gone.txt") == 0 and rows(con, "final_ok", "old-gone.txt") == 0
          and not con.execute("SELECT 1 FROM suggested_people WHERE email='old@legacy.example'").fetchone())
    check("startup keeps calls that exist or are waiting to be cleaned",
          rows(con, "standins", "queued.txt") == 1 and rows(con, "standins", "sync-renamed.txt") > 0
          and con.execute("SELECT 1 FROM suggested_people WHERE email='ash@both.example'").fetchone())
    con.close()
finally:
    shutil.rmtree(VAULT, ignore_errors=True)
print(f"\n{sum(ok)}/{len(ok)} checks passed")
sys.exit(0 if all(ok) else 1)

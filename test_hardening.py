"""Regression tests for privacy, original integrity, identity decisions and exports.

All source text is invented. Each test uses a new isolated vault.
"""
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="tc-hardening-"))
os.environ["CLEANER_HOME"] = str(ROOT / "bootstrap")
os.environ["CLEANER_THEMES"] = str(ROOT / "themes")
import clean
import identities
import app


@contextmanager
def database():
    con = clean.connect()
    try:
        with con:
            yield con
    finally:
        con.close()


class Hardening(unittest.TestCase):
    def test_parallel_servers_reserve_different_addresses(self):
        first = app.LocalServer(('127.0.0.1', 0), app.Handler)
        try:
            second = app.LocalServer(('127.0.0.1', 0), app.Handler)
            try:
                self.assertNotEqual(first.server_address, second.server_address)
                with self.assertRaises(OSError):
                    app.LocalServer(first.server_address, app.Handler)
            finally:
                second.server_close()
        finally:
            first.server_close()

    def setUp(self):
        clean.set_home(ROOT / self._testMethodName / "vault")
        clean.init()
        with database() as con:
            clean.add_to_list(con, "allow", "Morgan Reyes")

    def output(self, file="call.txt"):
        con = clean.connect()
        try:
            return clean.clean_path(con, file).read_text(encoding="utf-8")
        finally:
            con.close()

    def test_output_overlap_rejected(self):
        for path in [clean.HOME, clean.RAW, clean.PRIVATE, clean.HOME.parent]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                clean.validate_output(path)
        self.assertEqual(clean.validate_output(clean.HOME.parent / "exports"), (clean.HOME.parent / "exports").resolve())

    def test_legacy_unsafe_output_never_overwrites_original(self):
        with database() as con:
            clean.add_client(con, "Jane Whitfield")
            clean.set_setting(con, "output_dir", str(clean.RAW))
            clean.set_setting(con, "review_before_export", "0")
        source = "Jane Whitfield: Original scope is approved."
        clean.run(texts=[("call.txt", source)])
        self.assertEqual((clean.RAW / "call.txt").read_text(), source)
        con = clean.connect()
        try:
            self.assertIsNone(clean.output_dir(con))
        finally:
            con.close()

    def test_same_filename_preserves_both_originals(self):
        one, two = "Morgan Reyes: First scope approved.", "Morgan Reyes: Second scope approved."
        clean.run(texts=[("notes.txt", one), ("notes.txt", two)])
        self.assertEqual((clean.RAW / "notes.txt").read_text(), one)
        self.assertEqual((clean.RAW / "notes-2.txt").read_text(), two)
        clean.run(texts=[("notes.txt", one)])
        self.assertEqual(len(list(clean.RAW.iterdir())), 2)
        self.assertEqual(len(list(clean.CLEAN.iterdir())), 2)

    def test_reclean_preserves_original_and_stable_export_id(self):
        source = "Morgan Reyes: The scope is approved."
        clean.run(texts=[("call.txt", source)])
        before = list(clean.CLEAN.iterdir())[0].name
        raw = (clean.RAW / "call.txt").read_bytes()
        clean.reclean_all()
        self.assertEqual(raw, (clean.RAW / "call.txt").read_bytes())
        self.assertEqual(before, list(clean.CLEAN.iterdir())[0].name)

    def test_filename_only_identifiers_never_export(self):
        clean.run(texts=[("Derek-Olsen-Bluefern-Bakery-555-214-8890.txt", "Morgan Reyes: Scope approved.")])
        p = list(clean.CLEAN.iterdir())[0]
        self.assertRegex(p.name, r"^call-[a-f0-9]{32}\.txt$")
        self.assertNotIn("Derek", p.name)

    def test_company_context_holds_lowercase_acronym_and_glossary_collision(self):
        clean.run(texts=[("lower.txt", "Morgan Reyes: the team at bluefern bakery approved the scope."),
                         ("acronym.txt", "Morgan Reyes: Our client is ACME. Their team approved the scope."),
                         ("tool.txt", "Morgan Reyes: Our new client is Signal. Their team approved the scope.")])
        con = clean.connect()
        try:
            self.assertEqual({r[0] for r in con.execute("SELECT status FROM calls")}, {"held"})
            questions = {r[0].lower() for r in con.execute("SELECT name FROM review WHERE kind='company'")}
            self.assertTrue({"bluefern bakery", "acme", "signal"} <= questions)
        finally:
            con.close()

    def test_oneoff_company_short_form_is_hidden_in_same_call(self):
        with database() as con:
            clean.add_to_list(con, "oneoff_company", "Quarry Hill Studio")
        clean.run(texts=[("call.txt", "Morgan Reyes: The team at Quarry Hill Studio asked. Quarry Hill approved the scope.")])
        self.assertNotIn("Quarry", self.output())

    def test_word_names_preserve_sentence_meaning(self):
        with database() as con:
            clean.add_client(con, "Will Nair")
            clean.add_client(con, "Mark Whitfield")
            clean.add_client(con, "Bill Olsen")
        clean.run(texts=[("call.txt", "Will Nair: I will send notes.\nMark Whitfield: Please mark the invoice paid.\nBill Olsen: The bill is due Friday.")])
        text = self.output()
        for s in ["I will send", "mark the invoice", "The bill is due"]:
            self.assertIn(s, text)
        for s in ["Will Nair", "Mark Whitfield", "Bill Olsen"]:
            self.assertNotIn(s, text)

    def test_phone_shaped_value_hidden_without_valid_numbering_range(self):
        clean.run(texts=[("call.txt", "Morgan Reyes: My phone is 459-928-8815 ext. 4321.")])
        text = self.output()
        self.assertNotIn("8815", text)
        self.assertNotIn("4321", text)

    def test_short_client_name_does_not_consume_another_person_full_name(self):
        with database() as con:
            clean.add_client(con, "Victor")
        clean.run(texts=[("call.txt", "Morgan Reyes: Victor Fairbanks approved the scope.")])
        con = clean.connect()
        try:
            self.assertIn("Victor Fairbanks", {r[0] for r in con.execute("SELECT name FROM review")})
        finally:
            con.close()

    def test_company_surname_does_not_consume_unregistered_person(self):
        with database() as con:
            clean.add_company(con, "Olsen Builds;Olsen")
        clean.run(texts=[("call.txt", "Morgan Reyes: Derek Olsen from Olsen Builds approved the scope.")])
        con = clean.connect()
        try:
            self.assertIn("Derek Olsen", {r[0] for r in con.execute("SELECT name FROM review")})
        finally:
            con.close()

    def test_new_client_company_and_aliases_saved_together(self):
        clean.run(texts=[("call.txt", "Derek Olsen: The team at Bluefern Bakery approved it.\nMorgan Reyes: Hi Deky.")])
        con = clean.connect()
        try:
            row = con.execute("SELECT * FROM review WHERE name='Derek Olsen'").fetchone()
            with con:
                code = identities.save(con, {"review_id": row["id"], "kind": "person", "action": "new", "full_name": "Derek Olsen", "aliases": "Deky",
                                             "company_names": "Bluefern Bakery, Bluefern", "emails": "derek@bluefern.example", "phones": "555-214-8890"})
            client = con.execute("SELECT * FROM clients WHERE code=?", (code,)).fetchone()
            self.assertTrue(client["company_code"])
            self.assertEqual(client["aliases"], "Deky")
        finally:
            con.close()
        clean.reclean_all()
        self.assertNotIn("Deky", self.output())
        self.assertNotIn("Bluefern", self.output())

    def test_duplicate_identity_requires_distinct_confirmation(self):
        clean.run(texts=[("call.txt", "Derek Olsen: Scope approved.")])
        with database() as con:
            clean.add_client(con, "Derek Olsen")
        con = clean.connect()
        try:
            row = con.execute("SELECT * FROM review LIMIT 1").fetchone()
            body = {"review_id": row["id"], "kind": "person", "action": "new", "full_name": "Derek Olsen", "company_names": "Copperline Studio"}
            with self.assertRaises(ValueError), con:
                identities.save(con, body)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM companies").fetchone()[0], 0)
            with con:
                identities.save(con, {**body, "distinct": True})
            self.assertEqual(con.execute("SELECT COUNT(*) FROM clients").fetchone()[0], 2)
        finally:
            con.close()

    def test_call_only_choice_does_not_hide_name_globally(self):
        clean.run(texts=[("one.txt", "Derek Olsen: Scope approved."), ("two.txt", "Derek Olsen: Scope pending.")])
        con = clean.connect()
        try:
            row = con.execute("SELECT * FROM review WHERE file='one.txt'").fetchone()
            with con:
                identities.save(con, {"review_id": row["id"], "kind": "person", "action": "hide_call"})
        finally:
            con.close()
        clean.run()
        self.assertNotIn("Derek", self.output("one.txt"))
        con = clean.connect()
        try:
            self.assertEqual(con.execute("SELECT status FROM calls WHERE file='two.txt'").fetchone()[0], "held")
        finally:
            con.close()

    def test_review_gate_and_changed_content_revoke_export(self):
        out = clean.HOME.parent / "exports"
        out.mkdir()
        with database() as con:
            code = clean.add_client(con, "Jane Whitfield")
            clean.set_setting(con, "output_dir", str(out))
        clean.run(texts=[("call.txt", "Jane Whitfield: Ask Janie about the scope.")])
        # Resolve an alias locally; regardless of its NER label it gets registered.
        with database() as con:
            con.execute("UPDATE clients SET aliases='Janie' WHERE code=?", (code,))
        clean.reclean_all()
        self.assertEqual(list(out.iterdir()), [])
        con = clean.connect()
        try:
            with con:
                self.assertTrue(clean.approve_export(con, "call.txt"))
            self.assertEqual(len(list(out.iterdir())), 1)
            con.execute("UPDATE clients SET aliases='' WHERE code=?", (code,))
            con.commit()
        finally:
            con.close()
        clean.reclean_all()
        self.assertEqual(list(out.iterdir()), [])

    def test_missed_entity_can_be_tagged_without_detector_question(self):
        clean.run(texts=[("call.txt", "Morgan Reyes: the scope for bramblewood is approved.")])
        con = clean.connect()
        try:
            with con:
                identities.save(con, {"file": "call.txt", "detected": "bramblewood", "kind": "company", "action": "hide_call"})
        finally:
            con.close()
        clean.reclean_all()
        self.assertNotIn("bramblewood", self.output())

    def test_merge_preserves_identifiers_and_relinks_calls(self):
        with database() as con:
            keep = clean.add_client(con, "Derek Olsen", emails="derek@bluefern.example")
            remove = clean.add_client(con, "Deky Olsen", aliases="Deky", phones="555-214-8890")
        clean.run(texts=[("call.txt", "Deky Olsen: Scope approved.\nMorgan Reyes: Hi Deky.")])
        with database() as con:
            identities.merge(con, keep, remove)
            row = con.execute("SELECT * FROM clients WHERE code=?", (keep,)).fetchone()
            self.assertIn("Deky", row["aliases"])
            self.assertEqual(row["phones"], "555-214-8890")
            self.assertIsNone(con.execute("SELECT 1 FROM clients WHERE code=?", (remove,)).fetchone())
        clean.reclean_all()
        self.assertIn(keep, self.output())
        self.assertNotIn(remove, self.output())

    def test_revocation_removes_unchanged_exports_from_previous_destinations(self):
        first, second = clean.HOME.parent / "first", clean.HOME.parent / "second"
        first.mkdir(); second.mkdir()
        with database() as con:
            clean.add_client(con, "Jane Whitfield")
            clean.set_setting(con, "output_dir", str(first))
        clean.run(texts=[("call.txt", "Jane Whitfield: Scope approved.")])
        with database() as con:
            clean.approve_export(con, "call.txt")
            clean.set_setting(con, "output_dir", str(second))
        clean.deliver_all()
        self.assertEqual(len(list(first.iterdir())), 1)
        self.assertEqual(len(list(second.iterdir())), 1)
        with database() as con:
            clean.set_setting(con, "hide", '{"people": false}')
        clean.reclean_all()
        self.assertEqual(list(first.iterdir()), [])
        self.assertEqual(list(second.iterdir()), [])

    def test_user_edited_export_is_preserved_and_conflict_is_reported(self):
        out = clean.HOME.parent / "exports"
        out.mkdir()
        with database() as con:
            clean.set_setting(con, "review_before_export", "0")
            clean.set_setting(con, "output_dir", str(out))
        clean.run(texts=[("call.txt", "Morgan Reyes: Scope approved.")])
        target = list(out.iterdir())[0]
        target.write_text("User edited this file.")
        summary = clean.reclean_all()
        self.assertEqual(target.read_text(), "User edited this file.")
        self.assertEqual(summary["export_failed"], 1)
        self.assertTrue((clean.RAW / "call.txt").exists())
        con = clean.connect()
        try:
            self.assertEqual(con.execute("SELECT status FROM calls").fetchone()[0], "clean")
            self.assertTrue(con.execute("SELECT export_error FROM calls").fetchone()[0])
        finally:
            con.close()

    def test_rename_preserves_original_and_export_identifier(self):
        clean.run(texts=[('call.txt', 'Morgan Reyes: Scope approved.')])
        original = (clean.RAW / 'call.txt').read_bytes()
        with database() as con:
            old = clean.clean_path(con, 'call.txt').name
        clean.rename_call('call.txt', 'Private-client-name.txt')
        with database() as con:
            self.assertEqual(clean.clean_path(con, 'Private-client-name.txt').name, old)
        self.assertEqual((clean.RAW / 'Private-client-name.txt').read_bytes(), original)

    def test_legacy_export_migrates_only_when_exactly_owned(self):
        out = clean.HOME.parent / 'exports'
        out.mkdir()
        clean.run(texts=[('call.txt', 'Morgan Reyes: Scope approved.')])
        with database() as con:
            current = clean.clean_path(con, 'call.txt')
            legacy = clean.CLEAN / 'client-name.txt'
            current.rename(legacy)
            con.execute("UPDATE calls SET clean_name='client-name.txt' WHERE file='call.txt'")
            clean.set_setting(con, 'output_dir', str(out))
            (out / legacy.name).write_bytes(legacy.read_bytes())
        clean.reclean_all()
        self.assertFalse((out / legacy.name).exists())
        self.assertTrue((clean.RAW / 'call.txt').exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

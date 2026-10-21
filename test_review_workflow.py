"""Saved-copy comparisons and explicit batch scopes, with invented transcripts."""
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import tempfile
import unittest
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='tc-review-tests-'))
os.environ['CLEANER_HOME'] = str(root / 'bootstrap')
os.environ['CLEANER_THEMES'] = str(root / 'themes')
import clean
import identities
import comparison


class ReviewWorkflow(unittest.TestCase):
    def setUp(self):
        clean.set_home(root / self._testMethodName)
        clean.init()
        con = clean.connect()
        with con:
            clean.add_to_list(con, 'allow', 'Morgan Reyes')
        con.close()

    def test_comparison_preserves_exact_text_in_both_columns(self):
        before = 'Jane Whitfield:\nCall jane@example.test.\nMark the invoice paid.\n'
        after = '[Cleaned locally today. Hidden: names.]\n\nC001:\nCall C001-EMAIL.\nMark the invoice paid.\n'
        result = comparison.compare(before, after)
        self.assertEqual(''.join(s['text'] for s in result['original']), before)
        self.assertEqual(''.join(s['text'] for s in result['clean']), after)
        self.assertEqual(len(result['changes']), 2)
        self.assertFalse(any('Mark' in c['original'] for c in result['changes']))

    def test_comparison_handles_unicode_empty_and_literal_html(self):
        for a, b in [('', ''), ('Zoë García <script>', 'C001 <script>'), ('only original', ''), ('', 'only clean')]:
            r = comparison.compare(a, b)
            self.assertEqual(''.join(s['text'] for s in r['original']), a)
            self.assertEqual(''.join(s['text'] for s in r['clean']), b)

    def test_selected_call_hiding_does_not_resolve_unselected_call(self):
        clean.run(texts=[('one.txt', 'Derek Olsen: Scope approved.'), ('two.txt', 'Derek Olsen: Scope pending.')])
        con = clean.connect()
        try:
            rows = con.execute('SELECT * FROM review ORDER BY file').fetchall()
            with con:
                identities.save_group(con, {'review_ids':[rows[0]['id']], 'kind':'person', 'action':'hide_call'})
        finally:
            con.close()
        clean.run()
        con = clean.connect()
        try:
            self.assertEqual(con.execute("SELECT status FROM calls WHERE file='one.txt'").fetchone()[0], 'clean')
            self.assertEqual(con.execute("SELECT status FROM calls WHERE file='two.txt'").fetchone()[0], 'held')
        finally:
            con.close()

    def test_group_creates_one_shared_record(self):
        clean.run(texts=[('one.txt', 'Derek Olsen: Scope approved.'), ('two.txt', 'Derek Olsen: Scope pending.')])
        con = clean.connect()
        try:
            ids = [r[0] for r in con.execute('SELECT id FROM review')]
            with con:
                identities.save_group(con, {'review_ids':ids, 'kind':'person', 'action':'new', 'full_name':'Derek Olsen'})
            self.assertEqual(con.execute('SELECT COUNT(*) FROM clients').fetchone()[0], 1)
        finally:
            con.close()
        clean.reclean_all()

    def test_mixed_and_stale_groups_are_rejected_atomically(self):
        clean.run(texts=[('one.txt', 'Derek Olsen: Scope approved.'), ('two.txt', 'Theo Marchetti: Scope pending.')])
        con = clean.connect()
        try:
            ids = [r[0] for r in con.execute('SELECT id FROM review')]
            with self.assertRaises(ValueError), con:
                identities.save_group(con, {'review_ids':ids, 'kind':'person', 'action':'new', 'full_name':'Wrong Merge'})
            self.assertEqual(con.execute('SELECT COUNT(*) FROM clients').fetchone()[0], 0)
            with self.assertRaises(ValueError):
                identities.group_rows(con, [ids[0], 999999])
            with self.assertRaises(ValueError):
                identities.group_rows(con, [ids[0], ids[0]])
        finally:
            con.close()

    def test_call_specific_correction_preserves_saved_record(self):
        con = clean.connect()
        with con:
            wrong = clean.add_client(con, 'Jane Whitfield')
            right = clean.add_client(con, 'Jane Other', aliases='Janie')
        con.close()
        clean.run(texts=[('one.txt', 'Jane Whitfield: Scope approved.'), ('two.txt', 'Jane Whitfield: Scope pending.')])
        con = clean.connect()
        try:
            with con:
                identities.save(con, {'file':'one.txt', 'detected':'Jane Whitfield', 'kind':'person', 'action':'link_call', 'code':right})
        finally:
            con.close()
        clean.reclean_all()
        con = clean.connect()
        try:
            self.assertIn(right, clean.read_text(clean.clean_path(con, 'one.txt')))
            self.assertIn(wrong, clean.read_text(clean.clean_path(con, 'two.txt')))
            self.assertEqual(con.execute('SELECT full_name FROM clients WHERE code=?', (wrong,)).fetchone()[0], 'Jane Whitfield')
        finally:
            con.close()

    def test_contact_corrections_use_contact_codes_and_only_this_call(self):
        con = clean.connect()
        with con:
            original = clean.add_client(con, 'Jane Whitfield', emails='jane@example.test', phones='555-214-8890')
            corrected = clean.add_client(con, 'Derek Olsen')
        con.close()
        raw = 'Morgan Reyes: Email jane@example.test or call 555-214-8890.'
        clean.run(texts=[('one.txt', raw), ('two.txt', raw)])
        con = clean.connect()
        try:
            with con:
                for phrase in ('jane@example.test', '555-214-8890'):
                    identities.save(con, {'file':'one.txt', 'detected':phrase, 'kind':'person', 'action':'link_call', 'code':corrected})
        finally:
            con.close()
        clean.reclean_all()
        con = clean.connect()
        try:
            one = clean.read_text(clean.clean_path(con, 'one.txt'))
            two = clean.read_text(clean.clean_path(con, 'two.txt'))
            self.assertIn(corrected + '-EMAIL', one)
            self.assertIn(corrected + '-PHONE', one)
            self.assertIn(original + '-EMAIL', two)
            self.assertIn(original + '-PHONE', two)
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)

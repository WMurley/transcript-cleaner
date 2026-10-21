"""Regression coverage for demonstrated gaps, using invented transcripts only."""
import os
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix='tc-adversarial-tests-'))
os.environ['CLEANER_HOME'] = str(ROOT / 'bootstrap')
os.environ['CLEANER_THEMES'] = str(ROOT / 'themes')
import clean
import identities
from eval_adversarial import load_cases, present

CASES = {c['id']:c for c in load_cases()}


class Adversarial(unittest.TestCase):
    def setUp(self):
        clean.set_home(ROOT / self._testMethodName)
        clean.init()
        con = clean.connect()
        with con:
            clean.add_to_list(con, 'allow', 'Morgan Reyes')
        con.close()

    def run_case(self, name):
        case = CASES[name]
        con = clean.connect()
        with con:
            for names in case.get('companies',[]):
                clean.add_company(con, names)
            for p in case.get('people',[]):
                clean.add_client(con, p['name'], phones=p.get('phones',''))
        con.close()
        file = case.get('file', name+'.txt')
        clean.run(texts=[(file,case['text'])])
        return case, file

    def assert_clean(self, case, file):
        con = clean.connect()
        try:
            self.assertEqual(con.execute('SELECT status FROM calls WHERE file=?',(file,)).fetchone()[0],'clean')
            output = clean.read_text(clean.clean_path(con,file))
            for h in case['hide']:
                self.assertFalse(present(h['text'], output), h)
            for keep in case['keep']:
                self.assertTrue(present(keep, output), keep)
            self.assertEqual(clean.read_text(clean.RAW/file), case['text'])
            return output
        finally:
            con.close()

    def test_registered_typography_uses_existing_codes_without_questions(self):
        for name in ['curly-apostrophe','unicode-normalization','nonbreaking-hyphen','smart-apostrophe-company']:
            with self.subTest(name=name):
                case,file = self.run_case(name)
                self.assertRegex(self.assert_clean(case,file),r'\b[CO]\d{3}\b')
                con=clean.connect()
                try:
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM review WHERE file=?',(file,)).fetchone()[0],0)
                finally:
                    con.close()

    def test_contacts_hide_all_fragments_and_preserve_business_text(self):
        for name in ['phone-digits-only','international-phone','phone-extension-word','phone-extension-hash','apostrophe-email','plus-email-uppercase']:
            with self.subTest(name=name):
                case,file = self.run_case(name)
                self.assert_clean(case,file)

    def test_phone_context_does_not_hide_numbers_elsewhere(self):
        text='Morgan Reyes: Invoice number 4599288815. The budget is $48,000. Delivery date is 2026-10-03.'
        clean.run(texts=[('numbers.txt',text)])
        self.assert_clean({'text':text,'hide':[],'keep':['4599288815','$48,000','2026-10-03']},'numbers.txt')

    def test_contact_switches_remain_respected(self):
        text="Morgan Reyes: Email o'brien@ember.example or phone 4599288815."
        con=clean.connect()
        with con:
            clean.set_setting(con,'hide',json.dumps({'emails':False,'phones':False}))
        con.close()
        clean.run(texts=[('visible.txt',text)])
        self.assert_clean({'text':text,'hide':[],'keep':["o'brien@ember.example",'4599288815']},'visible.txt')

    def test_vtt_voice_is_held_and_can_be_resolved_normally(self):
        case,file=self.run_case('vtt-speaker-labels')
        con=clean.connect()
        try:
            q=con.execute("SELECT * FROM review WHERE name='Nika Velloren'").fetchone()
            self.assertIsNotNone(q)
            with con:
                identities.save(con,{'review_id':q['id'],'kind':'person','action':'hide_call'})
        finally:
            con.close()
        clean.run()
        self.assert_clean(case,file)

    def test_public_tool_employer_requires_a_company_question(self):
        case,file=self.run_case('work-for-tool-name')
        con=clean.connect()
        try:
            q=con.execute("SELECT * FROM review WHERE name='Signal' AND kind='company'").fetchone()
            self.assertIsNotNone(q)
            with con:
                identities.save(con,{'review_id':q['id'],'kind':'company','action':'hide_call'})
        finally:
            con.close()
        clean.run()
        self.assert_clean(case,file)

    def test_oracle_detects_partial_contact_and_canonical_unicode(self):
        self.assertTrue(present("o'", "Email o'EMAIL-1"))
        self.assertTrue(present('Zoë García','Zoë García'))
        self.assertFalse(present('Mira','mirage'))
        self.assertTrue(present('742','[PERSON], 742'))

    def test_full_address_correction_wins_over_earlier_street_answer(self):
        case,file=self.run_case('address')
        con=clean.connect()
        try:
            q=con.execute("SELECT * FROM review WHERE name='Wrenwick Avenue'").fetchone()
            with con:
                identities.save(con,{'review_id':q['id'],'kind':'person','action':'hide_call'})
        finally:
            con.close()
        clean.run()
        con=clean.connect()
        try:
            with con:
                identities.save(con,{'file':file,'detected':'742 Wrenwick Avenue, Suite 6','kind':'person','action':'hide_call'})
        finally:
            con.close()
        clean.reclean_all()
        self.assert_clean(case,file)

    def test_selected_number_is_hidden_even_before_a_capitalized_name(self):
        text='Morgan Reyes: Our mailing address is 742 Wrenwick Avenue.'
        con=clean.connect()
        with con:
            clean.add_to_list(con,'allow','Wrenwick Avenue')
        con.close()
        clean.run(texts=[('number.txt',text)])
        con=clean.connect()
        with con:
            identities.save(con,{'file':'number.txt','detected':'742','kind':'person','action':'hide_call'})
        con.close()
        clean.reclean_all()
        self.assert_clean({'text':text,'hide':[{'text':'742'}],'keep':['Wrenwick Avenue']},'number.txt')


if __name__=='__main__':
    unittest.main(verbosity=2)

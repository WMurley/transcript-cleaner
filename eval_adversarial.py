"""Independent, hand-written synthetic eval. Never opens the user's vault or keychain.

Stages are reported separately: initial detector output, answering only questions
the app actually asks, then an exhaustive simulated human review. The last stage
uses the fixture's answer key and is NOT a detector accuracy score.
Usage: python eval_adversarial.py [--report-only] [--output PATH]
Default exit is nonzero for automatic misses, meaning loss or workflow failures.
"""
import argparse
import hashlib
import json
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import re
import tempfile
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent


def normalized(value):
    return unicodedata.normalize('NFC', value).casefold()


def present(phrase, text):
    phrase, text = normalized(phrase), normalized(text)
    left = r'(?<![\w])' if phrase[:1].isalnum() else ''
    right = r'(?![\w])' if phrase[-1:].isalnum() else ''
    return bool(re.search(left + re.escape(phrase).replace(r'\ ', r'\s+') + right, text))


def load_cases(fixtures=None):
    cases = json.loads((fixtures or HERE / 'test-fixtures' / 'adversarial_calls.json').read_text(encoding='utf-8'))['cases']
    assert len({c['id'] for c in cases}) == len(cases), 'Duplicate case ID'
    for c in cases:
        for item in c['hide']:
            assert present(item['text'], c['text']), (c['id'], 'hidden expectation not in source', item)
        for text in c['keep']:
            assert present(text, c['text']), (c['id'], 'retained expectation not in source', text)
    return cases


def evaluate(work, fixtures=None):
    # Set both paths before imports: real app settings and raw calls stay unopened.
    os.environ['CLEANER_HOME'] = str(work / 'bootstrap')
    os.environ['CLEANER_THEMES'] = str(work / 'themes')
    import clean
    import identities

    def state(file):
        con = clean.connect()
        try:
            row = dict(con.execute('SELECT * FROM calls WHERE file=?', (file,)).fetchone())
            questions = [dict(r) for r in con.execute('SELECT * FROM review WHERE file=? ORDER BY id', (file,))]
            path = clean.clean_path(con, file)
            text = clean.read_text(path) if row['status'] == 'clean' and path.exists() else None
            return row, questions, text
        finally:
            con.close()

    def score(case, file):
        row, questions, text = state(file)
        body = text.split('\n\n', 1)[-1] if text is not None else None
        return {'status': row['status'], 'questions': [{'name':q['name'], 'kind':q['kind']} for q in questions],
                'misses': [h for h in case['hide'] if body is not None and present(h['text'], body)],
                'meaning_loss': [s for s in case['keep'] if body is not None and not present(s, body)],
                'owner_lost': body is not None and 'Morgan Reyes' in case['text'] and not present('Morgan Reyes', body)}

    def answer_questions(case, file, log):
        noise, answered = [], set()
        for _ in range(16):
            _, questions, _ = state(file)
            changed = False
            for q in questions:
                key = (q['kind'], normalized(q['name']))
                if key in answered:
                    continue
                hits = [h for h in case['hide'] if present(q['name'], h['text'])]
                keep = present(q['name'], ' '.join(case['keep'])) or normalized(q['name']) == 'morgan reyes'
                con = clean.connect()
                try:
                    with con:
                        if hits:
                            kind = 'company' if all(h['kind'] == 'company' for h in hits) else 'person'
                            if q['kind'] == 'ambiguous':
                                clean.set_decision(con, q['id'], 'person')
                            else:
                                identities.save(con, {'review_id':q['id'], 'kind':kind, 'action':'hide_call'})
                            action = 'hide_call'
                        elif keep:
                            if q['kind'] == 'ambiguous':
                                noise.append(q['name'])
                                continue  # No UI keep option for this ambiguous-name question.
                            identities.save(con, {'review_id':q['id'], 'kind':'company' if q['kind']=='company' else 'person', 'action':'keep'})
                            noise.append(q['name'])
                            action = 'keep'
                        else:
                            noise.append(q['name'])
                            continue  # Unmapped questions stay held, never silently approved.
                    log.append({'question':q['name'], 'action':action})
                    answered.add(key)
                    changed = True
                finally:
                    con.close()
            if not changed:
                break
            clean.run()
        return sorted(set(noise))

    results = []
    for case in load_cases(fixtures):
        clean.set_home(work / case['id'] / 'vault')
        clean.init()
        exports = work / case['id'] / 'exports'
        exports.mkdir(parents=True)
        con = clean.connect()
        try:
            with con:
                clean.add_to_list(con, 'allow', 'Morgan Reyes')
                clean.set_setting(con, 'output_dir', str(exports))
                for names in case.get('companies', []):
                    clean.add_company(con, names)
                for p in case.get('people', []):
                    clean.add_client(con, p['name'], aliases=p.get('aliases',''), phones=p.get('phones',''))
        finally:
            con.close()
        file = case.get('file', case['id'] + '.txt')
        clean.run(texts=[(file, case['text'])])
        initial = score(case, file)
        decisions = []
        noise = answer_questions(case, file, decisions)
        prompted = score(case, file)
        withheld = not list(exports.iterdir())
        # Exhaustive review: tag source phrases using the same public save operation
        # as selecting a missed phrase in Before / after. No answer-key changes to NER.
        manual = []
        for h in sorted(case['hide'], key=lambda h:len(h['text']), reverse=True):
            _, _, output = state(file)
            if output is not None and not present(h['text'], output):
                # A partial answer can hide the street name but leave the house
                # number. The reviewer can still select the full original span.
                partial = any(present(part['text'], output) and present(part['text'], h['text']) for part in case['hide'])
                if not partial:
                    continue
            con = clean.connect()
            try:
                with con:
                    identities.save(con, {'file':file, 'detected':h['text'],
                        'kind':'company' if h['kind']=='company' else 'person', 'action':'hide_call'})
                manual.append(h['text'])
            except ValueError as e:
                manual.append({'phrase':h['text'], 'error':str(e)})
            finally:
                con.close()
        clean.reclean_all()
        noise += answer_questions(case, file, decisions)
        reviewed = score(case, file)
        workflow = {'export_withheld_before_approval':withheld, 'exported':False,
                    'export_misses':[], 'original_preserved':False}
        row, _, text = state(file)
        original = next((d / file for d in (clean.RAW,clean.HELD) if (d / file).exists()), None)
        workflow['original_preserved'] = bool(original and clean.read_text(original)==case['text'])
        if row['status'] == 'clean':
            con = clean.connect()
            try:
                with con:
                    workflow['exported'] = clean.approve_export(con, file)
            finally:
                con.close()
            copied = exports / row['clean_name']
            if copied.exists():
                workflow['export_misses'] = [h for h in case['hide'] if present(h['text'], clean.read_text(copied))]
                workflow['neutral_filename'] = bool(re.fullmatch(r'call-[a-f0-9]{32}\.(?:txt|vtt|srt|md)', copied.name))
        results.append({'id':case['id'], 'category':case['category'], 'initial':initial, 'prompted':prompted,
            'reviewed':reviewed, 'noise_questions':sorted(set(noise)), 'decisions':decisions,
            'manual_tags':manual, 'workflow':workflow})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-only', action='store_true', help='Write measurements without treating detector limitations as a failing exit')
    parser.add_argument('--output', type=Path, default=HERE / '_eval' / 'adversarial.json')
    parser.add_argument('--fixtures', type=Path, default=HERE / 'test-fixtures' / 'adversarial_calls.json')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='tc-independent-eval-') as folder:
        results = evaluate(Path(folder), args.fixtures)
    summary = {'cases':len(results), 'initial_held':sum(r['initial']['status']=='held' for r in results),
        'prompted_cases_with_misses':sum(bool(r['prompted']['misses']) for r in results),
        'prompted_held':sum(r['prompted']['status']=='held' for r in results),
        'reviewed_cases_with_misses':sum(bool(r['reviewed']['misses']) for r in results),
        'reviewed_held':sum(r['reviewed']['status']=='held' for r in results),
        'meaning_loss_cases':sum(bool(r['reviewed']['meaning_loss']) or r['reviewed']['owner_lost'] for r in results),
        'workflow_failures':sum(not r['workflow']['export_withheld_before_approval'] or not r['workflow']['original_preserved']
                                or not r['workflow']['exported'] or bool(r['workflow']['export_misses'])
                                or not r['workflow'].get('neutral_filename') for r in results)}
    sources = ['clean.py','identities.py']
    hashes = {n:hashlib.sha256((HERE/n).read_bytes()).hexdigest() for n in sources}
    hashes[str(args.fixtures.resolve())] = hashlib.sha256(args.fixtures.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'summary':summary,'source_sha256':hashes,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary))
    for r in results:
        print(f"{r['id']}: prompted {r['prompted']['status']}, misses {len(r['prompted']['misses'])}; exhaustive review {r['reviewed']['status']}, misses {len(r['reviewed']['misses'])}; meaning loss {len(r['reviewed']['meaning_loss'])}")
    print(f'Report: {args.output}')
    bad = any(summary[k] for k in summary if k not in ('cases','initial_held'))
    return 1 if bad and not args.report_only else 0


if __name__ == '__main__':
    raise SystemExit(main())

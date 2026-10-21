"""Review harness, synthetic only. Exercises existing UI decision values after detection."""
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import json
import re
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sys.argv = [str(HERE / 'eval_client_calls.py'), '20', str(seed)]
g = runpy.run_path(str(HERE / 'eval_client_calls.py'))
clean, calls = g['clean'], g['calls']
truths = {n: truth for n, _, truth in calls}
decisions, unmapped = [], []
for round_no in range(8):
    con = clean.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM review WHERE kind != 'tool' ORDER BY id")]  # tool rows are a glance, never a hold
    con.close()
    if not rows:
        break
    for r in rows:
        con = clean.connect()
        if not con.execute('SELECT 1 FROM review WHERE id=?', (r['id'],)).fetchone():
            con.close()
            continue
        t = truths[r['file']]
        name = r['name'].casefold()
        own_people = {s.casefold() for s in t['client_people']}
        own_cos = {s.casefold() for s in t['client_cos']}
        third = {s.casefold() for s in t['unknown_people']}
        third_cos = {s.casefold() for s in t['unknown_cos']}
        if r['kind'] == 'ambiguous':
            matches = [c for c in con.execute('SELECT * FROM clients')
                       if c['full_name'].casefold() in own_people
                       and c['code'] in r['candidates'].split(' or ')]
            d = matches[0]['code'] if len(matches) == 1 else 'person'
        elif name in third or name in third_cos or any(name in s.casefold().split() for s in t['unknown_people']):
            d = 'oneoff'
        elif name in own_people:
            matches = [c for c in con.execute('SELECT * FROM clients')
                       if c['full_name'].casefold() in own_people
                       and (name == c['full_name'].casefold() or name in c['full_name'].casefold().split()
                            or name in {a.casefold() for a in clean.split(c['aliases'])})]
            d = ('same:' + matches[0]['code'] if len(matches) == 1 else 'client') if r['kind'] == 'unknown' else 'oneoff'
        elif any(name in s.casefold().split() for s in t['client_people']):
            # A surviving surname is safe to hide, without creating a second client.
            d = 'oneoff'
        elif name in own_cos:
            matches = [c for c in con.execute('SELECT * FROM companies')
                       if any(n.casefold() in own_cos for n in clean.split(c['names']))]
            d = ('same:' + matches[0]['code'] if len(matches) == 1 else 'company') if r['kind'] == 'company' else 'oneoff'
        else:
            unmapped.append(r)
            con.close()
            continue
        clean.set_decision(con, r['id'], d)
        con.commit()
        con.close()
        decisions.append({'round': round_no + 1, **r, 'answer': d})
        clean.run()
con = clean.connect()
status = {r['file']: r['status'] for r in con.execute('SELECT * FROM calls')}
remaining = [dict(r) for r in con.execute("SELECT * FROM review WHERE kind != 'tool'")]
leaks, released = [], 0
for name, _, truth in calls:
    if status[name] != 'clean':
        continue
    released += 1
    p = clean.clean_path(con, name)
    out = p.read_text(encoding='utf-8').split('\n', 2)[-1]
    for s in set(truth['known'] + truth['unknown_people'] + truth['unknown_cos']):
        if g['present'](s, out):
            leaks.append({'file': name, 'detail': s, 'kind': 'body'})
        if g['present'](s, p.stem.replace('-', ' ')):
            leaks.append({'file': name, 'detail': s, 'kind': 'filename'})
con.close()
result = {'seed': seed, 'calls': len(calls), 'released': released, 'held': len(calls)-released,
          'decisions': len(decisions), 'leaks': leaks, 'remaining': remaining,
          'unmapped': unmapped, 'decision_log': decisions}
(HERE / '_eval' / f'after-approval-{seed}.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(f'AFTER APPROVAL seed {seed}: released {released}/{len(calls)}, decisions {len(decisions)}, leaks {len(leaks)}, held {len(calls)-released}')
for leak in leaks[:20]:
    print(' ', leak)
for r in remaining[:10]:
    print(' STILL HELD', r['file'], r['kind'], r['name'])
sys.exit(1 if leaks or released != len(calls) or remaining else 0)

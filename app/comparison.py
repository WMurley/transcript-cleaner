"""Compare saved copies locally. Never re-run detection or change an export."""
import difflib
import re


def compare(original, cleaned):
    prefix, body = ('', cleaned)
    if cleaned.startswith('[Cleaned locally ') and '\n\n' in cleaned:
        header, body = cleaned.split('\n\n', 1)
        prefix = header + '\n\n'
    a = list(re.finditer(r'\S+', original))
    b = list(re.finditer(r'\S+', body))
    changes = []
    before, after = [], []
    pa = pb = 0
    matcher = difflib.SequenceMatcher(None, [m.group() for m in a], [m.group() for m in b])
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == 'equal':
            continue
        start_a = a[i].start() if i < len(a) else len(original)
        end_a = a[j - 1].end() if j > i else start_a
        start_b = b[k].start() if k < len(b) else len(body)
        end_b = b[l - 1].end() if l > k else start_b
        cid = len(changes)
        changes.append({'id': cid, 'original': original[start_a:end_a], 'replacement': body[start_b:end_b]})
        before.extend([{'text': original[pa:start_a]}, {'text': original[start_a:end_a], 'change': cid}])
        after.extend([{'text': body[pb:start_b]}, {'text': body[start_b:end_b], 'change': cid}])
        pa, pb = end_a, end_b
    before.append({'text': original[pa:]})
    after.append({'text': body[pb:]})
    return {'original': before, 'clean': [{'text': prefix}] + after, 'changes': changes}

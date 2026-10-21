# GLiNER detector trial, 10-10-2026

**Decision: not adopted.** A cheaper fix to the app's own rules closed the gap GLiNER was meant to close, without a download, extra memory or a slower clean. GLiNER stays a candidate if surname-only names or unusual punctuation turn out to matter on real calls.

## What was tested

GLiNER is a small named-entity model that takes the labels you ask for ("person", "company", "software"), so in principle it can tell Claude the tool from Claude the person. Microsoft Presidio, which the app already uses, supports it.

- Library: `gliner` 0.2.29 (Apache 2.0, released 09-08-2026). It requires PyTorch.
- Model: `gliner-community/gliner_small-v2.5` (Apache 2.0), half-precision weights, run at full precision on the CPU.
- Not tested: NVIDIA's GLiNER-PII (1.8 GB, NVIDIA's own licence) and re-packaged "edge" builds from small publishers (unknown provenance).
- Run in a throwaway environment outside the app. Nothing in the app depended on it.
- Machine: Ryzen 7 7700X, 32 GB. To approximate a 16 GB laptop, GLiNER was capped at 4 threads (also measured at 2).

The current detector is spaCy `en_core_web_lg` inside Presidio, plus the app's rules.

## Results

### Compute

| | Today (spaCy) | GLiNER |
|---|---|---|
| Extra download | none | about 0.8 GB (PyTorch 481 MB installed, model 332 MB) |
| Memory for the model | about 0.7 GB | about 1.1 GB on top, 1.6 GB peak on its own |
| Load time | about 2 s | about 12 s |
| 11,518-word synthetic call, detector only | 2.7 s | 25 s (4 threads), 34 s (2 threads) |
| A real 20,574-word call | | 43 s (4 threads) |

On a typical laptop, GLiNER would add roughly a minute or more to a long call and about 1 GB of memory. Running alongside spaCy, the app would need about 2.5 to 3 GB.

### Accuracy

| Test | Today | GLiNER |
|---|---|---|
| Hand-written hard cases, names not already saved (18) | 15 found | 18 found |
| Tool or person, first set (26, used to tune the new rule) | 19 before the fix, 26 after | 24 |
| Tool or person, fresh set (16, written after tuning, never tuned on) | 16 | 10 |
| Synthetic calls, unlisted names found (120) | 119 | 120 |
| Synthetic calls, raw false alarms before the app's filters | 270 (timestamps, "LLM", tool names) | 18 |

The app's filters already remove nearly all of spaCy's raw false alarms. With safe-by-default on, the default-mode evaluation shows 0 leaks and 0 ordinary words hidden.

GLiNER's misses on the fresh tool-or-person set run both ways. It hid four tools (Claude, Devin and Julius used as software) and left two real people visible ("Hermes, our landlord", "Pepper from the bakery").

The hard cases GLiNER found and today's detector missed: a surname used alone, two names in VTT speaker labels, a name with a non-breaking hyphen and curly apostrophe, a saved company name with odd spacing, and a client company named like a tool ("Notion"). Several of these are already caught by the app's other rules or by the client table when the person is saved.

### Real calls (counts only; no names were printed or stored)

Across the member's six real calls, today's app would list 60 names on Review names and GLiNER 60. They agree on 34. On the longest call (20,574 words), today's app lists 57 and GLiNER 58:
- Of the 23 names only today's app listed, GLiNER called 13 software and found nothing for 12.
- GLiNER listed 26 names the app didn't, 20 of them single words.

So GLiNER would change which names appear, not shorten the list. Which side is right can only be judged by someone allowed to read the call.

## What changed in the app instead

The tool rule now also treats a tool-like name as a person when the call says "my brother-in-law Claude", "Devin, our accountant", or "Claude from accounting". The same applies when he or she refers back to the name before anyone else is named, since tools are "it". The rule also runs when spaCy never flagged the name at all ("Jasper said his team..."). Product tiers such as Claude Max and ChatGPT Plus joined the glossary. Covered by `test_review_names.py`.

## Side finding: speed

On a 23,036-word synthetic call, cleaning takes about 9.7 s:
- About 5.4 s is spaCy's full pipeline (tagger, parser, lemmatizer and NER). The app mainly needs NER.
- About 2.3 s is Presidio's phone-number finder parsing every timestamp as a possible phone number.

Both can likely be trimmed without changing results. Not done yet; needs its own measured change.

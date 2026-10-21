"""Synthetic client-call evaluation: generate realistic client calls with known answers, clean them, score.

Every name, company, email and phone number is invented. Each call is a one-to-one or small client call
(the tool's real use), in Fathom, Zoom or notes format, with nicknames, bare first names, lowercase
speech-to-text names, names that are ordinary words, tool talk, and a third party mentioned in passing.

Scores per run:
  LEAKS            a known client detail, or an unknown person/company, visible in a CLEAN copy (must be 0)
  NOISE QUESTIONS  a question about something that is not a person or company in the call
  QUESTIONS/CALL   how much the member is asked
Usage: python eval_client_calls.py [calls] [seed]
"""
import os
os.environ.setdefault("CLEANER_HOLD_UNKNOWN", "1")  # this suite checks the strict mode (calls wait until every name is answered); test_review_names.py covers the default
import json
import os
import random
import re
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SEED = int(sys.argv[2]) if len(sys.argv) > 2 else 1
rng = random.Random(SEED)

FIRST = ["Jane", "Priya", "Derek", "Ava", "Tomas", "Lena", "Marcus", "Keiko", "Rafael", "Nadia", "Owen", "Imani",
         "Sofia", "Elliot", "Hana", "Victor", "Chloe", "Dmitri", "Aaliyah", "Benedict"]
WORD_FIRST = ["Mark", "Will", "Grace", "Hope", "Rose", "Bill", "June", "Faith", "Hunter", "Summer"]  # names that are words
LAST = ["Whitfield", "Nair", "Olsen", "Lindqvist", "Marchetti", "Okafor", "Brennan", "Castellano", "Haddad", "Novak",
        "Ellison", "Tanaka", "Abernathy", "Delacroix", "Fairbanks", "Quintero", "Rasmussen", "Sorensen", "Vance", "Wexley"]
CO_HEAD = ["Bluefern", "Pinecrest", "Copperline", "Harbor Lane", "Northgate", "Silverbirch", "Redwood Row", "Kestrel",
           "Brightwater", "Oakhaven", "Lumen Ridge", "Stonebridge", "Juniper Hollow", "Ironwood", "Maple & Main",
           "Tidewater", "Cobalt Peak", "Fernhill", "Granite Bay", "Wildrose", "Bramblewood", "Crescent Hill",
           "Driftwood", "Elmstead", "Foxglove", "Glenmore", "Hawthorne", "Ivybridge", "Larkspur", "Meridian Oak",
           "Northwind", "Orchard Lane", "Pebblebrook", "Quarry Hill", "Riverbend", "Saltmarsh", "Thornfield",
           "Upland Grove", "Valewood", "Willowmere"]
CO_TAIL = ["Bakery", "Dental", "Logistics", "Realty", "Consulting", "Builds", "Fitness", "Legal", "Studio", "Partners"]
TOOLS = ["the LLM", "our Kanban board", "HubSpot", "Calendly", "Notion", "Zapier", "the API", "GitHub", "Airtable",
         "ChatGPT", "Claude", "the CRM", "our SOPs", "Slack", "Google Sheets", "QuickBooks", "n8n", "Loom"]
DAYS = ["Monday", "Tuesday", "Thursday", "Friday", "next week", "end of month"]
OWNER = "Morgan Reyes"


def person(word_name=False):
    for _ in range(50):
        f = rng.choice(WORD_FIRST if word_name else FIRST)
        full = f"{f} {rng.choice(LAST)}"
        if full not in _used_people:
            break
    _used_people.add(full)
    return f, full


_used_heads, _used_people = set(), set()


def company():
    free = [h for h in CO_HEAD if h not in _used_heads] or CO_HEAD
    head = rng.choice(free)
    _used_heads.add(head)
    return head, f"{head} {rng.choice(CO_TAIL)}"


def phone():
    a, b, c = rng.randint(200, 989), rng.randint(200, 989), rng.randint(1000, 9999)
    return rng.choice([f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}"])


def make_call(i, clients_table):
    """Return (file_name, text, truth). truth lists every string that must not survive in a clean copy."""
    kind = rng.choice(["known", "known", "known", "prospect"])  # mostly existing clients, some new prospects
    head, coname = company()
    f1, p1 = person(word_name=rng.random() < 0.3)
    email = f"{f1.lower()}@{head.lower().replace(' ', '').replace('&', 'and')}.com"
    ph = phone()
    nick = f1[:3] + "y" if len(f1) > 4 and rng.random() < 0.4 else ""
    second = person() if rng.random() < 0.4 else None
    third_f, third = person()                 # mentioned in passing, never on the list
    ref_head, ref_co = company()              # a referred company, never on the list
    if kind == "known":
        clients_table.append({"name": p1, "aliases": nick, "company": coname, "short": head, "email": email, "phone": ph})
        if second:
            clients_table.append({"name": second[1], "aliases": "", "company": coname, "short": head, "email": "", "phone": ""})
    lines = [
        (OWNER, f"Hi {f1}, thanks for making time today."),
        (p1, f"Of course. {rng.choice(['Things at', 'Everyone at', 'The team at'])} {coname} has been busy."),
        (OWNER, f"Last time we said {rng.choice(TOOLS)} was the bottleneck. Is that still true?"),
        (p1, f"Mostly. We moved intake into {rng.choice(TOOLS)} and the follow-ups into {rng.choice(TOOLS)}."),
        (OWNER, f"Got it. Can you send the export to me, or should I email {email}?"),
        (p1, f"Email is fine. If it's urgent call my cell, {ph}."),
        (OWNER, f"Perfect. Who else should be in the loop at {head}?"),
    ]
    if second:
        lines.append((p1, f"{second[1]} runs operations, so {second[0]} should see it too."))
    if nick:
        lines.append((OWNER, f"Sounds good, {nick}."))
    lines += [
        (p1, f"Also, {third} from {ref_co} asked about working with you."),
        (OWNER, f"Happy to talk to {third_f}. Let's revisit the SOPs {rng.choice(DAYS)}."),
        (p1, f"talked to {f1.lower()} {rng.choice(['and', '-'])} we agreed the LLM drafts first, a human signs off."),
        (OWNER, f"Great. I'll update {rng.choice(TOOLS)} and send notes {rng.choice(DAYS)}."),
    ]
    fmt = rng.choice(["fathom", "zoom", "notes"])
    if fmt == "fathom":
        body = "\n".join(f"[00:{i // 6:02d}:{(i * 10) % 60:02d}] {w}: {t}" for i, (w, t) in enumerate(lines))
        text = f"Meeting: {coname} check-in\nInvitees: {p1} <{email}>\n\n" + body
    elif fmt == "zoom":
        text = "\n\n".join(f"00:{i // 6:02d}:{(i * 10) % 60:02d} --> 00:{i // 6:02d}:{(i * 10 + 8) % 60:02d}\n{w}: {t}"
                           for i, (w, t) in enumerate(lines))
    else:
        text = f"# Notes: {coname}\n\n" + "\n".join(f"- {t}" for _, t in lines)
    known = [p1, f1, email, ph, coname, head] + ([nick] if nick else []) + (list(second) if second else [])
    truth = {"kind": kind, "format": fmt, "known": known, "unknown_people": [third, third_f], "unknown_cos": [ref_co, ref_head],
             "client_people": [p1, f1] + (list(second) if second else []) + ([nick] if nick else []),
             "client_cos": [coname, head]}
    return f"call-{SEED}-{i:03d}-{fmt}.txt", text, truth


# ---- build a fresh vault outside the app folder
work = Path(tempfile.mkdtemp(prefix="tc-eval-"))
os.environ["CLEANER_HOME"] = str(work / "vault")
os.environ["CLEANER_THEMES"] = str(work / "themes")
sys.path.insert(0, str(HERE))
import clean  # noqa: E402

table, calls = [], []
for i in range(N):
    calls.append(make_call(i, table))
clean.init()
con = clean.connect()
clean.add_to_list(con, "allow", OWNER)
companies = {}
for c in table:
    if c["company"] not in companies:
        companies[c["company"]] = clean.add_company(con, f"{c['company']};{c['short']}")
    clean.add_client(con, c["name"], aliases=c["aliases"], company_code=companies[c["company"]],
                     emails=c["email"], phones=c["phone"])
con.commit()
con.close()
summary = clean.run(texts=[(n, t) for n, t, _ in calls])

# ---- score
con = clean.connect()
questions = [dict(r) for r in con.execute("SELECT kind, file, name FROM review")]
status = {r["file"]: r["status"] for r in con.execute("SELECT file, status FROM calls")}


def present(s, text):
    return bool(re.search(r"(?<![\w@.])" + re.escape(s) + r"(?![\w])", text, flags=re.IGNORECASE))


leaks, noise, missed_unknown = [], [], []
for name, text, truth in calls:
    entity_words = {w.lower() for s in truth["known"] + truth["unknown_people"] + truth["unknown_cos"] for w in re.split(r"[\s@.()-]+", s) if w}
    for q in [q for q in questions if q["file"] == name]:
        if not any(w in entity_words for w in re.split(r"\s+", q["name"].lower())):
            noise.append(f"{name}: asked about '{q['name']}' ({q['kind']})")
    if status.get(name) != "clean":
        continue
    out = clean.clean_path(con, name).read_text(encoding="utf-8").split("\n", 2)[-1]
    for s in truth["known"]:
        if present(s, out):
            leaks.append(f"{name}: known client detail '{s}' left in clean copy")
    for s in truth["unknown_people"] + truth["unknown_cos"]:
        if present(s, out):
            missed_unknown.append(f"{name}: unlisted '{s}' left in clean copy without a question")
con.close()

held = sum(1 for v in status.values() if v == "held")
per_kind = {k: sum(1 for q in questions if q["kind"] == k) for k in ("unknown", "company", "ambiguous")}
print(f"seed {SEED}: {N} client calls | clean {N - held}, held {held} | questions {len(questions)} "
      f"({len(questions) / N:.1f} per call: {per_kind}) | {summary['secs']:.1f}s")
print(f"  LEAKS (known client details in clean copies): {len(leaks)}")
for x in leaks[:12]:
    print("   ", x)
print(f"  UNLISTED PEOPLE/COMPANIES visible in clean copies: {len(missed_unknown)}")
for x in missed_unknown[:12]:
    print("   ", x)
print(f"  NOISE QUESTIONS: {len(noise)}")
for x in noise[:12]:
    print("   ", x)
(HERE / "_eval").mkdir(exist_ok=True)
(HERE / "_eval" / f"seed-{SEED}.json").write_text(json.dumps({"leaks": leaks, "missed_unknown": missed_unknown, "noise": noise,
                                                              "questions": questions, "status": status}, indent=1), encoding="utf-8")
print(f"  work folder: {work}")

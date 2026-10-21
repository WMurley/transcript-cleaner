"""Put names back: turn the codes in an agent's answer into real names, emails and phone numbers.

Runs on this computer against private storage. The text is never saved. Codes the app can't map
([PERSON] hidden without a record, or a code that isn't saved) are left as they are and flagged.
"""

import re

import clean

CODE = re.compile(r"(?<![\w-])(?:([CO])(\d{3})(?:-(EMAIL|PHONE))?|(EMAIL|PHONE)-(\d+)|(PERSON|COMPANY)-(\d+)|\[(PERSON|COMPANY)\])(?![\w-])", re.IGNORECASE)
GREETING = re.compile(r"(?:^|[\s,(])(?:hi|hello|hey|dear|thanks|thank you|morning|good morning|good afternoon|welcome|congrats|congratulations)[,!]?\s+$", re.IGNORECASE)


def _phone(value):
    d = clean.digits(value)
    if len(d) == 10:
        return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    if len(d) == 11 and d[0] == "1":
        return f"+1 ({d[1:4]}) {d[4:7]}-{d[7:]}"
    return value


def _tables(con):
    people = {r["code"]: dict(r) for r in con.execute("SELECT * FROM clients")}
    companies = {r["code"]: clean.split(r["names"])[0] for r in con.execute("SELECT * FROM companies") if clean.split(r["names"])}
    oneoff = {r["token"].upper(): (r["kind"], r["value"]) for r in con.execute("SELECT * FROM placeholders")}
    return people, companies, oneoff


def restore(con, text):
    """Split text into segments: plain text, and codes with what they stand for.

    Each code segment: {code, text (the restored value or the code itself), status: restored | unknown | hidden}.
    PERSON-1 / COMPANY-1 mean the same name in every call, so an answer about several calls comes back whole.
    """
    people, companies, oneoff = _tables(con)
    named = {r["name"].lower(): r["name"] for r in con.execute("SELECT name FROM review")}  # spelled as in the call
    standins = {}
    for r in con.execute("SELECT name, token FROM standins"):
        standins[r["token"].upper()] = named.get(r["name"]) or " ".join(w.capitalize() for w in r["name"].split())
    out, last = [], 0
    for m in CODE.finditer(text):
        code = m.group(0)
        value, status = None, "restored"
        if m.group(1):
            key = f"{m.group(1).upper()}{m.group(2)}"
            kind = (m.group(3) or "").upper()
            if key[0] == "C" and key in people:
                p = people[key]
                if kind == "EMAIL":
                    value = (clean.split(p["emails"]) or [None])[0]
                elif kind == "PHONE":
                    value = _phone((clean.split(p["phones"]) or [""])[0]) or None
                else:  # after a greeting, the first name reads naturally ("Hi Jane,")
                    value = p["full_name"].split()[0] if GREETING.search(text[max(0, m.start() - 40):m.start()]) else p["full_name"]
            elif key[0] == "O" and key in companies and not kind:
                value = companies[key]
        elif m.group(4):
            hit = oneoff.get(f"{m.group(4).upper()}-{m.group(5)}")
            if hit:
                value = hit[1] if hit[0] == "EMAIL" else _phone(hit[1])
        elif m.group(6):
            value = standins.get(f"{m.group(6).upper()}-{m.group(7)}")
            if value and m.group(6).upper() == "PERSON" and GREETING.search(text[max(0, m.start() - 40):m.start()]):
                value = value.split()[0]
            if not value:
                status = "unknown"
        else:
            status = "hidden"
        if value is None and status == "restored":
            status = "unknown"
        if m.start() > last:
            out.append({"text": text[last:m.start()]})
        out.append({"code": code, "text": value if value else code, "status": status})
        last = m.end()
    if last < len(text):
        out.append({"text": text[last:]})
    return out

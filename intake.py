"""Adding clients without typing them one by one.

Two ways in: people on a meeting's invite (Fathom and Granola send names and emails), suggested after a
pull for one-click saving; and a pasted list or CSV export from a CRM, Google Contacts or Excel, previewed
before anything is saved. Everything stays in private storage.
"""

import csv
import io
import re
from datetime import datetime

import clean
import identities

FREE_MAIL = {"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "yahoo.com", "ymail.com",
             "icloud.com", "me.com", "mac.com", "aol.com", "proton.me", "protonmail.com", "gmx.com", "gmx.net", "zoho.com",
             "mail.com", "fastmail.com", "hey.com", "comcast.net", "att.net", "verizon.net", "sbcglobal.net", "duck.com"}
TRADE_WORDS = sorted({"bakery", "dental", "dentistry", "realty", "realestate", "builds", "builders", "construction", "consulting",
                      "studio", "studios", "partners", "group", "labs", "media", "design", "designs", "health", "law", "legal",
                      "solutions", "tech", "digital", "agency", "capital", "ventures", "fitness", "logistics", "homes", "coaching",
                      "marketing", "systems", "software", "foods", "cafe", "clinic", "insurance", "financial", "advisors",
                      "roofing", "plumbing", "electric", "landscaping", "freight", "properties", "creative", "events", "travel",
                      "wellness", "therapy", "accounting", "cleaning", "services", "company", "co", "inc", "llc"}, key=len, reverse=True)
MAX_ROWS = 2000


def _stem(domain):
    parts = domain.lower().split(".")
    if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "net", "ac", "gov") and len(parts[-1]) == 2:
        return parts[-3]  # bluefern.co.uk -> bluefern
    return parts[-2] if len(parts) >= 2 else parts[0]


def _flat(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def company_from_email(con, email):
    """(company_name, company_code) guessed from an email's domain; nothing for personal mail services."""
    domain = email.rsplit("@", 1)[-1].strip().lower() if "@" in email else ""
    if not domain or domain in FREE_MAIL:
        return "", ""
    stem = _stem(domain)
    for co in con.execute("SELECT code, names FROM companies"):
        flats = [_flat(n) for n in clean.split(co["names"])]
        if any(f and (f == stem or (len(f) >= 4 and stem.startswith(f))) for f in flats):
            return clean.split(co["names"])[0], co["code"]
    words = stem.replace("-", " ").replace("_", " ")
    if " " not in words:
        for w in TRADE_WORDS:
            if words.endswith(w) and len(words) - len(w) >= 3:
                words = words[: -len(w)] + " " + ("real estate" if w == "realestate" else w)
                break
    return " ".join(p.upper() if p in ("llc", "inc") else p.capitalize() for p in words.split()), ""


def name_from_email(email):
    local = email.split("@", 1)[0]
    parts = [p for p in re.split(r"[._-]+", re.sub(r"\d+", "", local)) if len(p) > 1]
    return " ".join(p.capitalize() for p in parts) if len(parts) >= 2 else ""


def _known(con):
    emails, names = set(), set()
    for c in con.execute("SELECT full_name, aliases, emails FROM clients"):
        emails |= {e.lower() for e in clean.split(c["emails"])}
        names |= {n.casefold() for n in [c["full_name"]] + clean.split(c["aliases"])}
    names |= {a.casefold() for a in clean.get_list(con, "allow")}
    return emails, names


# ---------- suggestions from meeting invites ----------

def suggest(con, people, file):
    """Remember invitees who aren't saved yet. people: [{name, email, external?}]. Returns how many are new."""
    emails, names = _known(con)
    added = 0
    for p in people:
        email = (p.get("email") or "").strip().lower()
        name = (p.get("name") or "").strip() or name_from_email(email)
        if not email or "@" not in email or p.get("external") is False:
            continue  # someone inside your own workspace, or no email to go on
        if email in emails or (name and name.casefold() in names):
            continue
        # every call they were invited to, so deleting one call keeps them while another still has them
        con.execute("INSERT OR IGNORE INTO suggestion_sources (email, file) VALUES (?, ?)", (email, file))
        if con.execute("SELECT 1 FROM suggested_people WHERE email=?", (email,)).fetchone():
            continue  # already suggested (or already turned down)
        company, code = company_from_email(con, email)
        con.execute("INSERT INTO suggested_people (email, name, company, company_code, file, status, added) VALUES (?,?,?,?,?,'',?)",
                    (email, name, company, code, file, datetime.now().isoformat(timespec="seconds")))
        added += 1
    return added


def pending(con):
    emails, names = _known(con)
    out = []
    for r in con.execute("SELECT * FROM suggested_people WHERE status='' ORDER BY added, email"):
        if r["email"] in emails or (r["name"] and r["name"].casefold() in names):
            con.execute("UPDATE suggested_people SET status='saved' WHERE email=?", (r["email"],))
            continue  # saved some other way since
        out.append({k: r[k] for k in ("email", "name", "company", "company_code", "file")})
    return out


def dismiss(con, emails):
    for e in emails:
        con.execute("UPDATE suggested_people SET status='dismissed' WHERE email=?", (str(e).strip().lower(),))


# ---------- a pasted list or CSV export ----------

HEADER_WORDS = re.compile(r"name|first|last|given|family|surname|company|organi[sz]ation|employer|account|business|e-?mail|phone|mobile|cell|tel", re.I)


def _kind(header):
    h = header.strip().lower()
    if re.search(r"type|label|title|department|note|address|website|url|birthday|group", h):
        return ""
    if re.search(r"e-?mail", h):
        return "email"
    if re.search(r"phone|mobile|cell|\btel", h):
        return "phone"
    if re.search(r"company|organi[sz]ation|employer|account|business", h):
        return "company"
    if re.search(r"first|given", h):
        return "first"
    if re.search(r"last|family|surname", h):
        return "last"
    if re.search(r"middle", h):
        return ""
    if re.search(r"name|contact|person|client", h):
        return "name"
    return ""


def parse(text):
    """Rows of {name, company, email, phone} from a pasted list or a CSV/TSV export, header or not."""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    first = text.split("\n", 1)[0]
    delim = "\t" if "\t" in first else ";" if first.count(";") > first.count(",") else ","
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)][: MAX_ROWS + 1]
    if not rows:
        return []
    cols = [_kind(h) for h in rows[0]]
    has_header = sum(1 for h in rows[0] if HEADER_WORDS.search(h) and "@" not in h) >= 1 and any(cols)
    out = []
    for r in rows[1:] if has_header else rows:
        cells = [c.strip() for c in r]
        p = {"name": "", "company": "", "email": "", "phone": ""}
        if has_header:
            first = last = ""
            for kind, value in zip(cols, cells):
                if not value or not kind:
                    continue
                if kind == "first":
                    first = first or value
                elif kind == "last":
                    last = last or value
                elif not p[kind]:
                    p[kind] = value
            p["name"] = p["name"] or " ".join(x for x in (first, last) if x)
        else:  # no header: work out each cell from what it looks like
            texts = []
            for i, value in enumerate(cells):
                if not value:
                    continue
                if "@" in value and clean.EMAIL_RE.search(value) and not p["email"]:
                    p["email"] = clean.EMAIL_RE.search(value).group(0)
                elif len(clean.digits(value)) >= 7 and not re.search(r"[A-Za-z]{2,}", value) and not p["phone"]:
                    p["phone"] = value
                else:
                    texts.append((i, value))
            # the first cell is the name; a blank first cell means no name (the next text is the company, not a person)
            p["name"] = texts[0][1] if texts and texts[0][0] == 0 else ""
            others = [v for i, v in texts if i != 0]
            p["company"] = others[0] if others else ""
        p["email"] = p["email"].lower()
        if not p["name"] and p["email"]:
            p["name"] = name_from_email(p["email"])
        if any(p.values()):
            out.append(p)
    return out[:MAX_ROWS]


def preview(con, rows):
    """Each row with what will happen to it: new, already saved, or missing a name."""
    emails, names = _known(con)
    seen = set()
    out = []
    for p in rows:
        name = (p.get("name") or "").strip()
        email = (p.get("email") or "").strip().lower()
        if not name:
            status = "no-name"
        elif (email and email in emails) or name.casefold() in names or (name.casefold(), email) in seen:
            status = "saved"
        else:
            status = "new"
        seen.add((name.casefold(), email))
        company = (p.get("company") or "").strip()
        if not company and email:
            company = company_from_email(con, email)[0]
        out.append({"name": name, "company": company, "email": email, "phone": (p.get("phone") or "").strip(), "status": status})
    return out


def save(con, rows):
    """Save people as clients, linking or creating their companies. Skips anyone already saved. Returns codes."""
    codes = []
    for p in preview(con, rows):
        if p["status"] != "new":
            continue
        company_code = ""
        if p["company"]:
            matches = identities.duplicate(con, "company", p["company"])
            company_code = matches[0]["code"] if matches else clean.add_company(con, identities.names(p["company"]))
        codes.append(clean.add_client(con, p["name"], "", company_code, identities.names(p["email"]), identities.names(p["phone"])))
        if p["email"]:
            con.execute("UPDATE suggested_people SET status='saved' WHERE email=?", (p["email"],))
    return codes

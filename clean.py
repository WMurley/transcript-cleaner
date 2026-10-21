"""Local Transcript Cleaner: the cleaning engine.

Cleans call transcripts on this computer before any agent reads them.
Clients become stable codes from a private database; Presidio finds names,
emails and phone numbers the database does not know; spaCy flags unknown
company names; any file with an unknown or unclear name is held for one
approval. No AI model is used and nothing leaves the computer.

Usage (the app, app.py, calls the same functions):
  python clean.py                 clean everything waiting in dirty/ and held/
  python clean.py FILE_OR_FOLDER  copy those in, then clean (drag-and-drop)
  python clean.py --init          create the folders and the database
  python clean.py --stats         also print timing and memory

The console and the log show counts only, never names or transcript text.
"""

import csv
import json
import os
import re
import shutil
import sqlite3
import sys
import threading
import time
import uuid
import hashlib
import unicodedata
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The vault (calls, clients, database) lives OUTSIDE the app folder, so an agent asked to
# restyle or improve the app can never see a single call. An older vault inside the app
# folder keeps working until it is moved.
LEGACY_HOME = HERE / "ClientVault"
DEFAULT_HOME = Path.home() / "TranscriptCleaner-Vault"


def chosen_vault():
    """The vault folder picked in Settings, if any (kept with the app's settings, not inside the vault)."""
    try:
        import theme
        v = theme._settings().get("vault", "")
        return Path(v) if v else None
    except Exception:
        return None


HOME = Path(os.environ.get("CLEANER_HOME") or chosen_vault() or (LEGACY_HOME if LEGACY_HOME.exists() else DEFAULT_HOME))
DIRTY, CLEAN, HELD, RAW = HOME / "dirty", HOME / "clean", HOME / "held", HOME / "raw"
PRIVATE, LOG = HOME / "private", HOME / "log"
DB_PATH = PRIVATE / "vault.db"
TEXT_TYPES = {".txt", ".md", ".vtt", ".srt"}
EMAIL_RE = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_EXTENSION = r"(?:[ \t]*(?:ext(?:ension)?\.?|x|#)[ \t]*\d+)?"
OURS = re.compile(r"^(?:[CO]\d{3}(?:-EMAIL|-PHONE)?|EMAIL-\d+|PHONE-\d+|PERSON-\d+|COMPANY-\d+|\[PERSON\]|\[COMPANY\])$")
SPEAKER_RE = re.compile(r"(?m)^[ \t]*(?:\[?\d{1,2}:\d{2}(?::\d{2})?\]?[ \t]+)?([A-Z][\w.'’-]*(?:[ \t]+[A-Z][\w.'’-]*){0,3})[ \t]*:[ \t]")
STARTER_ALLOW = ["Fathom", "Zoom", "Granola", "Google Meet", "Microsoft Teams", "Teams", "Slack", "Gmail",
                 "Outlook", "Microsoft", "Google", "ChatGPT", "Claude", "Codex", "Otter", "Calendly", "Stripe"]
# Built-in glossary: tools, products and terms that come up in calls and are never people or clients.
# Never hidden, never asked about. Kept out of the member's own "fine to keep" list so it stays readable.
GLOSSARY = {g.lower() for g in """
AI|LLM|LLMs|GPT|RAG|API|APIs|MCP|SDK|CLI|UI|UX|CRM|ERP|SaaS|SOP|SOPs|KPI|KPIs|OKR|OKRs|ROI|FAQ|PDF|CSV|JSON|YAML|HTML|CSS|SQL|URL|VPS|DNS|SSH|AWS|GCP|IDE|PR|PRs|QA|MVP|B2B|B2C|CEO|COO|CTO|CFO|HR|PII|DPA|ZDR|HIPAA|SOC|GDPR|NDA
ChatGPT|ChatGPT Plus|ChatGPT Pro|OpenAI|Claude|Claude Code|Claude Max|Claude Pro|Claude Desktop|Claude Projects|Gemini Advanced|Anthropic|Codex|Cowork|Gemini|Google Gemini|Grok|xAI|DeepSeek|Kimi|Qwen|Llama|Mistral|Perplexity|Copilot|GitHub Copilot|Cursor|Windsurf|Lovable|Bolt|Replit|v0|Fable|Opus|Sonnet|Haiku|Sol|Ollama|Hugging Face|OpenRouter|LangChain|Langfuse|LangGraph|CrewAI|AutoGen
Midjourney|DALL-E|Sora|Veo|Runway|Higgsfield|ElevenLabs|HeyGen|Synthesia|Suno|Descript|Riverside|Loom|OBS|Remotion|Canva|Figma|Framer|Webflow|Squarespace|Wix|WordPress|Shopify|Kajabi|Skool|Teachable|Thinkific|Maven|Substack|Beehiiv|ConvertKit|Mailchimp|Klaviyo
Fathom|Granola|Otter|Fireflies|tl;dv|Zoom|Google Meet|Microsoft Teams|Teams|Slack|Discord|Telegram|WhatsApp|Signal|Mattermost|Calendly|Cal.com|Gmail|Outlook|Google|Google Drive|Google Docs|Google Sheets|Google Calendar|Microsoft|Microsoft 365|Office 365|Excel|PowerPoint|OneDrive|SharePoint|Dropbox|Box|iCloud
Notion|Obsidian|Airtable|Coda|Evernote|Asana|Trello|Jira|ClickUp|Monday.com|Basecamp|Miro|Kanban|Scrum|Agile|Zapier|n8n|Pipedream|IFTTT|HubSpot|Salesforce|Pipedrive|GoHighLevel|Stripe|PayPal|QuickBooks|Xero|FreshBooks|Gusto|DocuSign|PandaDoc
GitHub|GitLab|Bitbucket|Git|Docker|Kubernetes|Python|JavaScript|TypeScript|Node|React|Next.js|Markdown|Vercel|Netlify|Cloudflare|Supabase|Firebase|Postgres|PostgreSQL|MongoDB|Neo4j|Tailscale|Hostinger|DigitalOcean|Azure|Infisical|1Password|Bitwarden|LastPass|Apify|Firecrawl|Exa|Composio|Twilio|SendGrid
YouTube|LinkedIn|Instagram|TikTok|Facebook|Meta|Twitter|Reddit|Pinterest|Threads|Bluesky|Apple|iPhone|iPad|Mac|MacBook|Mac Mini|Mac Studio|Windows|Linux|Android|Chrome|Safari|Firefox|Edge
Hermes
NotebookLM|Gamma|Genspark|Manus|OpenClaw|Nous|Devin|Jasper|Alexa|Siri|Harvey|Lindy|Julius|Clay|Typeform|Jotform|Instantly|Smartlead|Lemlist|ManyChat|CapCut|Opus Clip|Napkin|Krea|Ideogram|Leonardo|Pika|Kling|Luma
Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|September|October|November|December
""".replace("\n", "|").split("|") if g.strip()}
GLOSSARY |= {w.lower() for w in """Email Emails Text Call Calls Cell Phone Thanks Thank Okay Ok Sure Great Perfect Hi Hello Hey
Yes Yeah Yep No Nope Sounds Got Mostly Also Happy Awesome Cool Right Well Anyway Absolutely Totally Exactly Agreed Noted
Today Tomorrow Yesterday Morning Afternoon Evening Team Client Clients Customer Customers Everyone Things""".split()}
# Names that are also AI tools. They're tools unless the call itself shows a person by that name:
# speaking on the call, greeted ("Hi Claude"), or with family or business ("Claude's wife", "Claude's company").
DUAL_USE = {"claude", "gemini", "hermes", "devin", "jasper", "alexa", "siri", "harvey", "lindy", "julius", "clay", "luma", "kling", "leonardo", "maven"}
ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9&]{1,5}s?$")  # LLM, API, SOPs: abbreviations, not names
CODE_RE = re.compile(r"\b([CO]\d{3})(?:-EMAIL|-PHONE)?\b")

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
  code TEXT PRIMARY KEY, full_name TEXT NOT NULL, aliases TEXT DEFAULT '',
  company_code TEXT DEFAULT '', emails TEXT DEFAULT '', phones TEXT DEFAULT '', notes TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS companies (code TEXT PRIMARY KEY, names TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS lists (list TEXT, name TEXT, PRIMARY KEY (list, name));
CREATE TABLE IF NOT EXISTS review (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, file TEXT, name TEXT,
  candidates TEXT DEFAULT '', decision TEXT DEFAULT '', UNIQUE (kind, file, name));
CREATE TABLE IF NOT EXISTS placeholders (kind TEXT, value TEXT, token TEXT, PRIMARY KEY (kind, value));
CREATE TABLE IF NOT EXISTS resolutions (file TEXT, name TEXT, value TEXT, PRIMARY KEY (file, name));
CREATE TABLE IF NOT EXISTS calls (
  file TEXT PRIMARY KEY, status TEXT, codes TEXT DEFAULT '', words INTEGER DEFAULT 0,
  survivors TEXT DEFAULT '', updated TEXT, removed TEXT DEFAULT '', clean_name TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS call_ids (file TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS export_approvals (file TEXT PRIMARY KEY, digest TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS final_ok (file TEXT, phrase TEXT, PRIMARY KEY (file, phrase));
CREATE TABLE IF NOT EXISTS standins (file TEXT, name TEXT, kind TEXT, token TEXT, PRIMARY KEY (file, name));
CREATE TABLE IF NOT EXISTS suggested_people (email TEXT PRIMARY KEY, name TEXT, company TEXT, company_code TEXT,
  file TEXT, status TEXT DEFAULT '', added TEXT);
CREATE TABLE IF NOT EXISTS deliveries (file TEXT, name TEXT, path TEXT, digest TEXT, PRIMARY KEY(file, path));
CREATE TABLE IF NOT EXISTS suggestion_sources (email TEXT, file TEXT, PRIMARY KEY (email, file));
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, action TEXT, label TEXT,
  file TEXT DEFAULT '', undo TEXT, undone INTEGER DEFAULT 0);
"""

_lock = threading.RLock()  # one cleaning run at a time (the app is multi-threaded)
_analyzer = None           # Presidio loads once per process
PRACTICE = False           # practice mode: sample data, nothing delivered to the output folder


def set_home(path, practice=False):
    """Point the cleaner at a different vault (used for practice mode)."""
    global HOME, DIRTY, CLEAN, HELD, RAW, PRIVATE, LOG, DB_PATH, PRACTICE
    HOME = Path(path)
    DIRTY, CLEAN, HELD, RAW = HOME / "dirty", HOME / "clean", HOME / "held", HOME / "raw"
    PRIVATE, LOG = HOME / "private", HOME / "log"
    DB_PATH = PRIVATE / "vault.db"
    PRACTICE = practice


# ---------- helpers ----------

def read_text(path):
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")  # Windows line endings confuse the name-spotter


def split(value):
    return [v.strip() for v in (value or "").split(";") if v.strip()]


def digits(s):
    return re.sub(r"\D", "", s)


def word_re(name):
    # Canonically equivalent accents and typographic punctuation are spellings
    # of the same saved name. Match them without altering the stored original.
    def escaped(value):
        return ''.join(r"\s+" if c.isspace() else "['‘’ʼ]" if c in "'‘’ʼ"
                       else "[-‐‑]" if c in '-‐‑' else re.escape(c) for c in value)
    forms = dict.fromkeys(escaped(unicodedata.normalize(form, name)) for form in ('NFC', 'NFD'))
    return r"(?<![\w@.])(?:" + '|'.join(forms) + r")(?![\w])"


COMPANY_SUFFIXES = {"bakery", "dental", "logistics", "realty", "consulting", "builds", "fitness", "legal", "studio", "partners", "llc", "ltd", "inc", "corp", "corporation"}
WORD_NAMES = {"mark", "will", "bill", "grace", "hope", "rose", "june", "faith", "hunter", "summer",
              "april", "may", "august", "dawn", "joy", "sky", "art", "rich", "pat", "max", "drew", "chase"}
# words that follow "Hi" or "Hey" without being anyone's name
GREETING_FILLER = {"both", "all", "there", "again", "folks", "guys", "you", "good", "for", "to", "everyone", "everybody",
                   "team", "y'all", "yall", "yeah", "yes", "ok", "okay", "thanks", "thank", "sorry", "um", "uh", "so",
                   "man", "buddy", "friend", "sir", "ma'am", "mate", "gang", "hi", "hello", "hey", "welcome", "real"}
CALENDAR = ("(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|January|February|March|April|May|June|July|August|"
            "September|October|November|December)")
# "my brother-in-law Claude", "Devin, our accountant": a tool-like name used for a person
PEOPLE_WORDS = ("brother|sister|wife|husband|partner|son|daughter|mom|dad|mother|father|cousin|uncle|aunt|friend|neighbou?r|"
                "boss|manager|colleague|coworker|co-worker|assistant|accountant|bookkeeper|lawyer|attorney|contractor|client|"
                "landlord|tenant|doctor|coach|mentor|intern|employee|nephew|niece|grandson|granddaughter")


def company_variants(name):
    """Suggest a distinctive short form; only use it automatically in a call with the full name."""
    parts = name.split()
    out = [name.strip()]
    while len(parts) > 1 and parts[-1].lower().strip(".,") in COMPANY_SUFFIXES:
        parts.pop()
    short = " ".join(parts)
    if short != name and len(short) >= 4 and short.lower() not in GLOSSARY and short.lower() not in WORD_NAMES:
        out.append(short)
    return out


def mention_re(name):
    """Protect ordinary uses of word names, without hiding an unrelated surname."""
    return word_re(name)


def connect():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute("PRAGMA table_info(calls)")}
    if "removed" not in cols:  # vaults made before "what was removed" existed
        con.execute("ALTER TABLE calls ADD COLUMN removed TEXT DEFAULT ''")
    if "clean_name" not in cols:  # vaults made before file names were cleaned too
        con.execute("ALTER TABLE calls ADD COLUMN clean_name TEXT DEFAULT ''")
    if "export_error" not in cols:
        con.execute("ALTER TABLE calls ADD COLUMN export_error TEXT DEFAULT ''")
    rcols = {r[1] for r in con.execute("PRAGMA table_info(review)")}
    for col, decl in (("mentions", "INTEGER DEFAULT 0"), ("speaker", "INTEGER DEFAULT 0"), ("token", "TEXT DEFAULT ''"),
                      ("reviewed", "INTEGER DEFAULT 0")):
        if col not in rcols:  # vaults made before names were hidden by default
            con.execute(f"ALTER TABLE review ADD COLUMN {col} {decl}")
    waiting = "FROM suggested_people WHERE file<>'' AND status=''"
    if not con.execute("SELECT 1 FROM suggestion_sources LIMIT 1").fetchone() and con.execute(f"SELECT 1 {waiting} LIMIT 1").fetchone():
        # vaults made before suggestions knew every call; committed now so a read-only caller holds no write lock
        con.execute(f"INSERT OR IGNORE INTO suggestion_sources (email, file) SELECT email, file {waiting}")
        con.commit()
    return con


def hold_unknown(con):
    """The strict mode: hold a call until every unsure name is answered (off by default)."""
    return get_setting(con, "hold_unknown", os.environ.get("CLEANER_HOLD_UNKNOWN", "0")) == "1"


def standin(con, file, name, kind):
    """The stand-in for an unsure name: PERSON-1, COMPANY-2... One per name, the same in every call, and a number
    is never given to anyone else, even after its calls are deleted. Rows stay per call so a deleted call's go too."""
    key = name.lower()
    row = con.execute("SELECT token FROM standins WHERE file=? AND name=?", (file, key)).fetchone()
    if row:
        return row["token"]
    prefix = "COMPANY" if kind == "company" else "PERSON"
    row = con.execute("SELECT token FROM standins WHERE name=? AND token LIKE ? LIMIT 1", (key, prefix + "-%")).fetchone()
    if row:
        token = row["token"]
    else:
        last = f"standin_last_{prefix.lower()}"
        used = [int(r["token"].split("-")[1]) for r in con.execute("SELECT token FROM standins WHERE token LIKE ?", (prefix + "-%",))]
        n = max(used + [int(get_setting(con, last, "0") or 0)]) + 1
        set_setting(con, last, str(n))
        token = f"{prefix}-{n}"
    con.execute("INSERT INTO standins (file, name, kind, token) VALUES (?,?,?,?)", (file, key, kind, token))
    return token


def _renumber_standins(con):
    """Once per vault: stand-ins used to be numbered per call (every call had its own PERSON-1). Clear them and
    queue every call to be cleaned again, so each unsure name gets one code shared by every call."""
    if get_setting(con, "standins_global") == "1":
        return
    with _lock:  # never while a cleaning run is handing out codes
        if con.execute("SELECT 1 FROM standins LIMIT 1").fetchone():
            con.execute("DELETE FROM standins")
            for f in RAW.iterdir():
                if f.is_file() and not (DIRTY / f.name).exists():
                    shutil.copy2(f, DIRTY / f.name)
        set_setting(con, "standins_global", "1")


HIDE_DEFAULT = {"people": True, "companies": True, "emails": True, "phones": True}


def hide_settings(con):
    try:
        saved = json.loads(get_setting(con, "hide") or "{}")
    except ValueError:
        saved = {}
    return {k: bool(saved.get(k, v)) for k, v in HIDE_DEFAULT.items()}


def category(token):
    if token.endswith("-EMAIL") or token.startswith("EMAIL-"):
        return "emails"
    if token.endswith("-PHONE") or token.startswith("PHONE-"):
        return "phones"
    if token.startswith("O") or token == "[COMPANY]" or token.startswith("COMPANY-"):
        return "companies"
    return "people"


def get_setting(con, key, default=""):
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(con, key, value):
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))


def get_list(con, name):
    return [r["name"] for r in con.execute("SELECT name FROM lists WHERE list=? ORDER BY name", (name,))]


def add_to_list(con, name, value):
    con.execute("INSERT OR IGNORE INTO lists (list, name) VALUES (?, ?)", (name, value.strip()))


# ---------- setup ----------

def init():
    for d in (DIRTY, CLEAN, HELD, RAW, PRIVATE, LOG):
        d.mkdir(parents=True, exist_ok=True)
    con = connect()
    import_legacy(con)
    if not get_list(con, "meta"):
        for tool in STARTER_ALLOW:
            add_to_list(con, "allow", tool)
        add_to_list(con, "meta", "seeded")
        set_setting(con, "review_before_export", "1")
    _renumber_standins(con)
    con.commit()
    con.close()


def forget_deleted():
    """Once at startup: drop per-call records left behind by calls deleted before delete_call cleared them all."""
    with _lock:
        con = connect()
        _forget_deleted(con)
        con.commit()
        con.close()


def _forget_deleted(con):
    files = {r[0] for r in con.execute("SELECT file FROM calls")}
    files |= {f.name for d in (DIRTY, HELD, RAW) if d.exists() for f in d.iterdir()}  # queued, not yet cleaned
    for table in ("standins", "final_ok", "suggestion_sources"):
        for (f,) in con.execute(f"SELECT DISTINCT file FROM {table}").fetchall():
            if f and f not in files:
                forget_call(con, f)


def forget_call(con, name):
    """Remove what the app remembers about one call, including invite suggestions waiting only on it
    (someone also on another call's invite stays suggested). Contacts stay: saved clients and companies,
    the EMAIL-n / PHONE-n codes, and suggestions already decided."""
    for q in ("DELETE FROM review WHERE file=?", "DELETE FROM resolutions WHERE file=?", "DELETE FROM calls WHERE file=?",
              "DELETE FROM call_ids WHERE file=?", "DELETE FROM export_approvals WHERE file=?",
              "DELETE FROM standins WHERE file=?", "DELETE FROM final_ok WHERE file=?",
              # decisions about this call only; decisions that apply to every call (Fine to show, team) stay
              "DELETE FROM decisions WHERE file=? AND action IN ('which', 'final_ok', 'keep_hidden', 'hide_call', 'link_call')"):
        con.execute(q, (name,))
    invited = [r[0] for r in con.execute("SELECT email FROM suggestion_sources WHERE file=?", (name,))]
    con.execute("DELETE FROM suggestion_sources WHERE file=?", (name,))
    for email in invited:
        other = con.execute("SELECT file FROM suggestion_sources WHERE email=? LIMIT 1", (email,)).fetchone()
        if other:
            con.execute("UPDATE suggested_people SET file=? WHERE email=? AND file=?", (other[0], email, name))
        else:
            con.execute("DELETE FROM suggested_people WHERE email=? AND status=''", (email,))


def import_legacy(con):
    """One-time import of spreadsheet-era files, if present and the database is empty."""
    if con.execute("SELECT COUNT(*) FROM clients").fetchone()[0] == 0 and (PRIVATE / "clients.csv").exists():
        with (PRIVATE / "clients.csv").open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                con.execute("INSERT OR IGNORE INTO clients (code, full_name, aliases, company_code, emails, phones) "
                            "VALUES (?,?,?,?,?,?)", (r["code"], r["full_name"], r.get("aliases", ""),
                                                     r.get("company_code", ""), r.get("emails", ""), r.get("phones", "")))
    if con.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0 and (PRIVATE / "companies.csv").exists():
        with (PRIVATE / "companies.csv").open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                con.execute("INSERT OR IGNORE INTO companies (code, names) VALUES (?,?)", (r["code"], r["names"]))
    for list_name, fname in (("allow", "allow.txt"), ("oneoff", "oneoff.txt"), ("oneoff_company", "oneoff-companies.txt")):
        p = PRIVATE / fname
        if p.exists() and not get_list(con, list_name):
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.startswith("#"):
                    add_to_list(con, list_name, line)


# ---------- the lookup table ----------

def phone_pattern(raw):
    d = digits(raw)
    if len(d) == 11 and d.startswith("1"):
        d = d[1:]
    if len(d) == 10:
        sep = r"[\s.\-]?"
        return rf"(?:\+?1{sep})?\(?{d[:3]}\)?{sep}{d[3:6]}{sep}{d[6:]}" + PHONE_EXTENSION
    return re.escape(raw)


def build_table(con):
    """Return a dict: replacements, ambiguous, email_map, first_names, company_of.

    Full names, nicknames, emails, phones and company names are matched everywhere.
    A bare first name ("John") is different: it only becomes a client's code when the
    same call also confirms that client (their full name, email, phone or company).
    Otherwise the call is held to ask "Is this John Smith?".
    """
    owners, phones, email_map, first_names, company_of = {}, [], {}, {}, {}
    for c in con.execute("SELECT * FROM clients"):
        code = c["code"]
        company_of[code] = c["company_code"] or ""
        names = [c["full_name"]] + split(c["aliases"])
        for n in names:
            owners.setdefault(n.strip().lower(), set()).add(code)
        if len(c["full_name"].split()) > 1:
            first_names.setdefault(c["full_name"].split()[0].lower(), set()).add(code)
        for e in split(c["emails"]):
            email_map[e.lower()] = f"{code}-EMAIL"
        for p in split(c["phones"]):
            phones.append((phone_pattern(p), f"{code}-PHONE"))
    for co in con.execute("SELECT * FROM companies"):
        for n in split(co["names"]):
            owners.setdefault(n.lower(), set()).add(co["code"])
    replacements, ambiguous = [], {}
    for name, codes in owners.items():
        if len(codes) == 1:
            code = next(iter(codes))
            replacements.append((mention_re(name) if code.startswith("C") else word_re(name), code))
        else:
            ambiguous[name] = sorted(codes)
    replacements.sort(key=lambda r: len(r[0]), reverse=True)
    first_names = {k: sorted(v) for k, v in first_names.items() if k not in owners}
    return {"replacements": phones + replacements, "ambiguous": ambiguous, "email_map": email_map,
            "first_names": first_names, "company_of": company_of,
            "companies": [dict(r) for r in con.execute("SELECT code, names FROM companies")],
            "hide": hide_settings(con), "owner_names": {k: sorted(v) for k, v in owners.items()}}


# ---------- codes and review decisions ----------

def next_code(con, prefix):
    table = "clients" if prefix == "C" else "companies"
    used = [int(r[0][1:]) for r in con.execute(f"SELECT code FROM {table} WHERE code LIKE ?", (prefix + "%",))]
    return f"{prefix}{(max(used) + 1 if used else 1):03d}"


def add_client(con, full_name, aliases="", company_code="", emails="", phones="", notes=""):
    code = next_code(con, "C")
    con.execute("INSERT INTO clients (code, full_name, aliases, company_code, emails, phones, notes) VALUES (?,?,?,?,?,?,?)",
                (code, full_name.strip(), aliases, company_code, emails, phones, notes))
    return code


def add_company(con, names):
    code = next_code(con, "O")
    con.execute("INSERT INTO companies (code, names) VALUES (?,?)", (code, names.strip()))
    return code


def set_decision(con, review_id, decision):
    con.execute("UPDATE review SET decision=? WHERE id=?", (decision, review_id))


def apply_review(con):
    """Apply decided review rows; leave undecided ones."""
    applied = 0
    for r in con.execute("SELECT * FROM review WHERE decision != ''").fetchall():
        d, low = r["decision"].strip(), r["decision"].strip().lower()
        ok = True
        if r["kind"] == "unknown":
            if low == "client":
                match = con.execute("SELECT code FROM clients WHERE lower(full_name)=lower(?)", (r["name"],)).fetchone()
                if not match:
                    add_client(con, r["name"])
            elif low == "allow":
                add_to_list(con, "allow", r["name"])
            elif low == "oneoff":
                add_to_list(con, "oneoff", r["name"])
            elif low.startswith("same:"):
                code = d.split(":", 1)[1].strip().upper()
                row = con.execute("SELECT aliases FROM clients WHERE code=?", (code,)).fetchone()
                ok = row is not None
                if ok:
                    con.execute("UPDATE clients SET aliases=? WHERE code=?",
                                (";".join(split(row["aliases"]) + [r["name"]]), code))
            else:
                ok = False
        elif r["kind"] == "company":
            if low == "company":
                add_company(con, r["name"])
            elif low == "allow":
                add_to_list(con, "allow", r["name"])
                add_to_list(con, "context_allow", r["name"])
            elif low == "oneoff":
                add_to_list(con, "oneoff_company", r["name"])
            elif low.startswith("same:"):
                code = d.split(":", 1)[1].strip().upper()
                row = con.execute("SELECT names FROM companies WHERE code=?", (code,)).fetchone()
                ok = row is not None
                if ok:
                    con.execute("UPDATE companies SET names=? WHERE code=?",
                                (";".join(split(row["names"]) + [r["name"]]), code))
            else:
                ok = False
        elif r["kind"] == "ambiguous":
            value = "[PERSON]" if low == "person" else d.upper()
            if value != "[PERSON]" and value not in r["candidates"].split(" or "):
                raise ValueError("Choose one of this question's suggested people, or Someone else.")
            con.execute("INSERT OR REPLACE INTO resolutions (file, name, value) VALUES (?,?,?)",
                        (r["file"], r["name"].lower(), value))
        if ok:
            con.execute("DELETE FROM review WHERE id=?", (r["id"],))
            applied += 1
    return applied


# ---------- cleaning one file ----------

def get_analyzer():
    global _analyzer
    with _lock:
        if _analyzer is None:
            from presidio_analyzer import AnalyzerEngine
            _analyzer = AnalyzerEngine()
    return _analyzer


def clean_text(text, fname, con, table):
    """Return (cleaned_text, report). table = build_table(con)."""
    replacements, ambiguous, email_map = table["replacements"], table["ambiguous"], table["email_map"]
    first_names, company_of = table["first_names"], table["company_of"]
    analyzer = get_analyzer()
    allow = get_list(con, "allow")
    allow_low = {a.lower() for a in allow}
    # what the member chose themselves (not the starter tools seeded into every new list); a name they
    # marked "It's a tool" counts as their choice
    user_allow = (allow_low - {s.lower() for s in STARTER_ALLOW}) | {n.lower() for n in get_list(con, "tools")}
    allow_tokens = {t for a in allow_low for t in a.split()}
    # known companies are never mistaken for people (matters when companies are left visible)
    co_names = {n.lower() for co in table.get("companies", []) for n in split(co["names"])}
    allow_low |= co_names
    allow_tokens |= {t for n in co_names for t in n.split()}
    allow_low |= GLOSSARY  # built-in tools and terms: never people, never clients
    allow_tokens |= {g for g in GLOSSARY if " " not in g}

    def noise(v, company=False):
        """Things that look like names but aren't: abbreviations (LLM, API), and, for companies only,
        words this same call also uses in lowercase ("the kanban board"). People are never filtered
        that way, because names like Mark, Will or Grace are ordinary words too."""
        words = [w for w in re.split(r"\s+", v) if w]
        if words and all(ACRONYM_RE.match(w) for w in words):
            return True
        if company and words and all(re.search(r"(?<![\w])" + re.escape(w.lower()) + r"(?![\w])", text) for w in words):
            return True
        return False
    # and known clients are never mistaken for companies (matters when people are left visible)
    person_names = {n for n, codes in table.get("owner_names", {}).items() if codes and codes[0].startswith("C")}
    hide = hide_settings(con)
    report = {"replaced": 0, "unknown": [], "ambiguous": [], "company": [], "found": set(),
              "removed": {"people": 0, "companies": 0, "emails": 0, "phones": 0}, "standins": {},
              "speakers": {m.group(1).strip().lower() for m in SPEAKER_RE.finditer(text)}}
    removed = report["removed"]
    hidden = report["hidden"] = {}
    report["tools_kept"] = []

    def person_signal(name):
        """Does this call treat a tool-like name (Claude, Hermes) as a person?"""
        n = re.escape(name)
        if (name.lower() in report["speakers"]
                or re.search(rf"\b(?:hi|hello|hey|dear|thanks|thank you)[,!]?\s+{n}\b", text, re.IGNORECASE)
                or re.search(rf"\b{n}(?:'s|’s)\s+(?:wife|husband|partner|son|daughter|kids|mom|dad|mother|father|family|"
                             rf"birthday|team|business|company|firm|office|assistant)\b", text, re.IGNORECASE)
                # a family member, colleague or role: "my brother-in-law Claude", "Claude from accounting"
                or re.search(rf"\bmy (?:{PEOPLE_WORDS})(?:-in-law)?,? {n}\b|\b{n},? (?:my|our) (?:{PEOPLE_WORDS})\b", text, re.IGNORECASE)
                or re.search(rf"\b{n} from (?:the )?(?!scratch|time|now|here|there|today|tomorrow|yesterday|home|memory|zero|start|"
                             rf"my\b|our\b|your\b)[a-z]", text)):
            return True
        # he or she refers back to it before anyone else is named: tools are "it" ("Lindy ... She is out until Thursday")
        for m in re.finditer(rf"\b{n}\b", text):
            window = text[m.end():m.end() + 160]
            other = re.search(rf"(?<![.!?:]\s)(?<!^)\b(?!I\b|{CALENDAR}\b)[A-Z][a-z]+", window)
            if re.search(r"\b(?:he|she|him|his|her|hers|himself|herself)\b", window[:other.start()] if other else window, re.IGNORECASE):
                return True
        return False
    email_answers = {r['name'].lower(): r['value'] for r in con.execute('SELECT name,value FROM resolutions WHERE file=?', (fname,)) if EMAIL_RE.fullmatch(r['name'])}

    def sub(pattern, token, text_):
        """Replace matches with the token, or, if that kind is set to stay visible, only note who it was."""
        on = hide[category(token)]
        hits = [0]
        ordinary_words = None

        def swap(m):
            nonlocal ordinary_words
            if (token.startswith(("C", "PERSON-")) or token == "[PERSON]") and m.group(0).lower() in WORD_NAMES:
                personal_context = bool(re.search(r"\b(?:hi|hello|hey|to|with|from|ask|email|contact|good|thanks)[, ]+$", text_[:m.start()], re.I)
                                        or re.match(r"[,:]|\s+(?:said|says|runs|should|approved|asked|wants|can|has)\b", text_[m.end():], re.I))
                if ordinary_words is None:
                    doc = analyzer.nlp_engine.nlp["en"](text_)
                    ordinary_words = {(t.idx, t.idx + len(t)) for t in doc
                                      if t.text.lower() in WORD_NAMES and t.pos_ in {"AUX", "VERB", "NOUN", "ADJ"}
                                      and t.ent_type_ != "PERSON"}
                if not personal_context and (m.start(), m.end()) in ordinary_words:
                    return m.group(0)
            if token.startswith("C") or token == "[PERSON]":
                following = re.match(r"\s+([A-Z][a-z]{2,})\b", text_[m.end():])
                if " " not in m.group(0) and any(c.isalpha() for c in m.group(0)) and following and following.group(1).lower() not in GLOSSARY:
                    return m.group(0)  # a different full name needs its own identity decision
            if token.startswith("O") or token == "[COMPANY]":
                # A company short name must not consume the surname of an
                # unregistered person, e.g. "Derek Olsen" / "Olsen Builds".
                previous = re.search(r"([A-Z][a-z]+)\s+$", text_[:m.start()])
                if " " not in m.group(0) and previous and previous.group(1).lower() not in GLOSSARY:
                    return m.group(0)
            base = CODE_RE.match(token)
            if base:
                report["found"].add(base.group(1))
            if not on:
                return m.group(0)
            hidden[m.group(0).lower()] = token
            hits[0] += 1
            return token
        out, _ = re.subn(pattern, swap, text_, flags=re.IGNORECASE)
        return out, hits[0]

    def count(token, n=1):
        report["replaced"] += n
        removed[category(token)] += n

    def placeholder(kind, value):
        row = con.execute("SELECT token FROM placeholders WHERE kind=? AND value=?", (kind, value)).fetchone()
        if row:
            return row["token"]
        n = con.execute("SELECT COUNT(*) FROM placeholders WHERE kind=?", (kind,)).fetchone()[0] + 1
        token = f"{kind}-{n}"
        con.execute("INSERT INTO placeholders (kind, value, token) VALUES (?,?,?)", (kind, value, token))
        return token

    # 0. emails first, so a name inside an address is never half-replaced
    def swap_email(m):
        known = email_answers.get(m.group(0).lower()) or email_map.get(m.group(0).lower())
        if known and CODE_RE.match(known):
            report["found"].add(known.split("-")[0])
        if not hide["emails"]:
            return m.group(0)
        token = known or placeholder("EMAIL", m.group(0).lower())
        hidden[m.group(0).lower()] = token
        count(token)
        return token
    text = EMAIL_RE.sub(swap_email, text)

    # Explicit contextual company mentions complement statistical name detection,
    # including lowercase transcription and companies with a public-tool name.
    contextual_companies = []
    for m in re.finditer(r"\b(?:at|from|client is|client called|company is|company called|(?:we|i) work for|(?:works|worked|working|work) (?:at|for))\s+(?:the\s+)?([\w&'-]+(?:[ \t]+[\w&'-]+){0,4})", text, re.IGNORECASE):
        candidate = re.split(r"\s+(?:has|have|had|is|was|were|said|asked|approved|wants|want|should|runs|and|but)\b", m.group(1), maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,;:")
        ws = candidate.split()
        suffix = next((i for i, w in enumerate(ws) if w.lower() in COMPANY_SUFFIXES), None)
        if suffix is not None:
            candidate = " ".join(ws[:suffix + 1])
        explicit = m.group(0).lower().startswith(("client ", "company ", "we work for ", "i work for ", "works ", "worked ", "working ", "work at", "work for"))
        if m.group(0).lower().startswith(("works ", "worked ", "working ", "work at", "work for")):
            # "works at Cedar Health now": the company is the run of capitalised words, not what follows it
            run = []
            for w in candidate.split():
                if w[:1].isupper() or (run and w.lower() in ("&", "of", "and")):
                    run.append(w)
                else:
                    break
            while run and run[-1].lower() in ("&", "of", "and"):
                run.pop()
            candidate = " ".join(run)
            ws = candidate.split()
        if candidate and (suffix is not None or explicit or (len(ws) == 1 and ACRONYM_RE.match(candidate))):
            contextual_companies.append(candidate)

    # Short company mentions follow a full-name match in this call, not globally.
    local_companies = []
    for co in table.get("companies", []):
        for name in split(co["names"]):
            if re.search(word_re(name), text, re.IGNORECASE):
                local_companies.extend((v, co["code"]) for v in company_variants(name)[1:])

    # 1. one-offs and this file's answers to "which Mike?" / "is this John Smith?"
    for list_name, token in (("oneoff", "[PERSON]"), ("oneoff_company", "[COMPANY]")):
        for name in get_list(con, list_name):
            had_full = " " in name and re.search(word_re(name), text, flags=re.IGNORECASE)
            text, n = sub(mention_re(name) if list_name == "oneoff" else word_re(name), token, text)
            count(token, n)
            if had_full and list_name == "oneoff":  # "Derek Tanaka" hidden, so his bare "Derek" in this call is too
                text, n = sub(mention_re(name.split()[0]), token, text)
                count(token, n)
            if had_full and list_name == "oneoff_company":
                for variant in company_variants(name)[1:]:
                    text, n = sub(word_re(variant), token, text)
                    count(token, n)
    # A later, fuller correction must win over an earlier partial answer.
    for r in con.execute("SELECT name, value FROM resolutions WHERE file=? ORDER BY length(name) DESC, name", (fname,)):
        text, n = sub(word_re(r["name"]), r["value"], text)
        count(r["value"], n)

    # 2. the client table: full names, nicknames, phones, companies
    for pattern, code in replacements:
        text, n = sub(pattern, code, text)
        count(code, n)
    for name, code in local_companies:
        text, n = sub(word_re(name), code, text)
        count(code, n)

    # A conservative phone-shaped fallback handles numbers Presidio rejects as
    # invalid numbering ranges. It runs after registered phone replacements.
    if hide["phones"]:
        phone_re = r"(?<![\w\d])(?:\+?1[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}" + PHONE_EXTENSION + r"(?!\d)"
        def swap_phone(m):
            value = digits(re.split(r"[ \t]*(?:ext(?:ension)?\.?|x|#)[ \t]*", m.group(0), flags=re.IGNORECASE)[0])[-10:]
            token = placeholder("PHONE", value)
            hidden[m.group(0).lower()] = token
            count(token)
            return token
        text = re.sub(phone_re, swap_phone, text, flags=re.IGNORECASE)
        # Digits-only and international numbers need an explicit phone cue.
        # Keep arbitrary account IDs, dates and amounts out of this fallback.
        contextual_phone = (r"\b(?:phone(?: number)?(?: is)?|call(?: me| us)?(?: at)?|"
                            r"tel(?:ephone)?\.?|mobile(?: number)?(?: is)?|cell(?: number)?(?: is)?|reach (?:me|us) at)"
                            r"[ \t:]+(?P<number>\+?\d(?:[\d \t.()-]*\d)?" + PHONE_EXTENSION + r")(?!\w)")
        def swap_contextual_phone(m):
            value = m.group('number')
            main = re.split(r"[ \t]*(?:ext(?:ension)?\.?|x|#)[ \t]*", value, flags=re.IGNORECASE)[0]
            if not 10 <= len(digits(main)) <= 15:
                return m.group(0)
            token = placeholder('PHONE', digits(main))
            hidden[value.lower()] = token
            count(token)
            return m.group(0)[:m.start('number') - m.start()] + token
        text = re.sub(contextual_phone, swap_contextual_phone, text, flags=re.IGNORECASE)

    # 3. bare first names: only when this call confirms which client it is
    present = set(CODE_RE.findall(text)) | report["found"]
    for name, codes in first_names.items():
        if not re.search(mention_re(name), text, flags=re.IGNORECASE):
            continue
        confirmed = [c for c in codes if c in present or (company_of.get(c) and company_of[c] in present)]
        # (the first name in any case, then a Capitalised surname: "imani Castellano" yes, "mike said" no)
        if not confirmed and re.search(r"(?<![\w@.])(?i:" + re.escape(name) + r")\s+[A-Z][a-z]{2,}", text):
            continue  # this call names someone else with that first name ("Imani Castellano"): it follows that question
        if len(confirmed) == 1:
            text, n = sub(mention_re(name), confirmed[0], text)
            count(confirmed[0], n)
        elif hide["people"]:
            report["ambiguous"].append((name, confirmed or codes))

    # 4. names shared by more than one client's nickname: hold
    for name, codes in ambiguous.items():
        if re.search(word_re(name), text, flags=re.IGNORECASE) and hide[category(codes[0])]:
            report["ambiguous"].append((name, codes))
    held_names = {n for n, _ in report["ambiguous"]}
    # first names of people you said are fine to keep, when their full name is in this call
    held_names |= {a.split()[0] for a in allow_low if " " in a and re.search(word_re(a), text, flags=re.IGNORECASE)}

    # 5. Presidio for people, emails and phones the table does not know
    wanted = [e for e, k in (("PERSON", "people"), ("EMAIL_ADDRESS", "emails"), ("PHONE_NUMBER", "phones")) if hide[k]]
    # One spaCy pass serves both the people detector (Presidio) and the company step below, instead of two.
    # Falls back to Presidio's own pass if its internals ever change.
    doc = artifacts = None
    if wanted or hide["companies"]:
        try:
            doc = analyzer.nlp_engine.nlp["en"](text)
            artifacts = analyzer.nlp_engine._doc_to_nlp_artifact(doc, "en") if wanted else None
        except Exception:
            doc = artifacts = None
    results = analyzer.analyze(text=text, language="en", entities=wanted, nlp_artifacts=artifacts) if wanted else []
    spans = []
    for r in sorted(results, key=lambda r: (r.start, -(r.end - r.start))):
        if spans and r.start < spans[-1][1]:
            continue
        value = text[r.start:r.end]
        if r.entity_type == "PERSON":
            v = value.split(":")[0]  # "Morgan Reyes: Hi" (a speaker label plus the next word) -> "Morgan Reyes"
            v = v.strip(" \t\n[](){}<>:;,.!?\"'-")  # "[00:00:06] Morgan Reyes" -> "Morgan Reyes"
            low = v.lower()
            if low in DUAL_USE and low not in user_allow and person_signal(v):
                report["unknown"].append(v)
                continue
            if (not re.search(r"[A-Za-z]", v) or OURS.match(v) or all(OURS.match(t) for t in v.split())
                    or low in held_names or low in allow_low or all(t in allow_tokens for t in low.split())
                    or noise(v)):
                continue
            report["unknown"].append(v)
            continue
        kind = "EMAIL" if r.entity_type == "EMAIL_ADDRESS" else "PHONE"
        key = value.lower() if kind == "EMAIL" else digits(value)[-10:]
        spans.append((r.start, r.end, placeholder(kind, key)))
    for start, end, token in sorted(spans, reverse=True):
        hidden[text[start:end].lower()] = token
        text = text[:start] + token + text[end:]
        count(token)

    # VTT voice annotations explicitly identify a speaker even when NER misses
    # the angle-bracket format. Saved identities have already become codes here.
    if hide['people']:
        for m in re.finditer(r'<v(?:\.[^\s>]+)*[ \t]+([^>\r\n]{1,120})>', text, re.IGNORECASE):
            name = m.group(1).strip()
            if name and not OURS.match(name) and name.lower() not in allow_low:
                report['unknown'].append(name)

    # one question per person: a bare "Derek" follows the answer about "Derek Tanaka" in the same call
    multi = [u for u in report["unknown"] if " " in u]
    report["unknown"] = [u for u in report["unknown"]
                         if " " in u or not any(u.lower() in (m.lower().split()[0], m.lower().split()[-1]) for m in multi)]

    # Direct greetings catch short nicknames missed by NER. These are questions,
    # never guesses about which existing client a nickname means.
    if hide["people"]:
        # "Hi, this is Derek" must not make "this" a name: under safe-by-default it would be hidden everywhere.
        # In a normally capitalised transcript a greeted name is capitalised, and common words never count.
        cased = bool(re.search(r"(?:^|[.!?]\s+)[A-Z]", text))
        vocab = analyzer.nlp_engine.nlp["en"].vocab
        for m in re.finditer(r"\b(?:hi|hello|hey|sounds good|happy to talk to)\s*,?\s+([A-Za-z][A-Za-z'-]{1,30})\b", text, re.IGNORECASE):
            name = m.group(1)
            low = name.lower()
            if (cased and not name[:1].isupper()) or low in GREETING_FILLER or (vocab[low].is_stop and low not in WORD_NAMES):
                continue
            tool_person = name.lower() in DUAL_USE and name.lower() not in user_allow
            if (tool_person or name.lower() not in allow_low | {"both", "all", "there", "again", "folks", "guys", "you", "good", "for", "to"}) and name.lower() not in held_names and not OURS.match(name) and not any(name.lower() == u.lower().split()[0] for u in multi):
                report["unknown"].append(name)
        # whatever found it, a lone common word ("this", "there") is never a name to hide everywhere
        report["unknown"] = [u for u in report["unknown"]
                             if " " in u.strip() or u.lower() in WORD_NAMES or not vocab[u.lower()].is_stop]

    # 6. company names the table does not know (spaCy, already loaded by Presidio)
    for ent in ((doc if doc is not None else analyzer.nlp_engine.nlp["en"](text)).ents if hide["companies"] else []):
        if ent.label_ != "ORG":
            continue
        v = re.sub(r"^[\[(]?\d{1,2}:\d{2}(?::\d{2})?[\])]?\s*", "", ent.text).strip(" []():;,.-'\"")  # drop "00:10:00]"
        if not v or v.lower() in {u.lower() for u in report["unknown"]}:
            continue  # nothing left, or already asked about as a person
        words = [w.strip(":.,;") for w in v.split()]
        caps = [w for w in words if w[:1].isupper() and not OURS.match(w) and w.lower() not in allow_tokens]
        long_terms = [g for g in GLOSSARY if " " in g and len(g) >= 8]  # "Acme Build Labs" ~ "acme build lab"
        if caps and not noise(v, company=True) and v.lower() not in allow_low \
                and not any(g in v.lower() for g in long_terms) \
                and not any(a in v.lower() for a in (allow_low - GLOSSARY) | person_names):
            report["company"].append(v)
    if hide["companies"]:
        for name in contextual_companies:
            trusted = {n.lower() for n in get_list(con, "context_allow")}
            if re.search(word_re(name), text, re.IGNORECASE) and name.lower() not in co_names and name.lower() not in trusted:
                report["company"].append(name)
                report["unknown"] = [u for u in report["unknown"] if u.lower() != name.lower()]
    multi_co = [c for c in report["company"] if " " in c]
    report["company"] = [c for c in report["company"]
                         if " " in c or not any(m.lower().split()[0] == c.lower() for m in multi_co)]
    # a one-word "company" that is really the first word of a person or company already asked about
    asked_first = {u.lower().split()[0] for u in report["unknown"] if " " in u}
    report["company"] = [c for c in report["company"] if " " in c or c.lower() not in asked_first]
    # ...and the other way round: a bare "Bluefern" the detector called a person is the short form of an unsure
    # "Bluefern Bakery" in the same call, so it gets the company's stand-in below. Unless it's also part of a
    # person's full name here ("Olsen" with both Derek Olsen and Olsen Builds), the person reading wins.
    co_shorts = {v.lower() for c in report["company"] if " " in c for v in company_variants(c)[1:]}
    person_parts = {w for u in report["unknown"] if " " in u for w in (u.lower().split()[0], u.lower().split()[-1])}
    report["unknown"] = [u for u in report["unknown"] if " " in u or u.lower() not in co_shorts or u.lower() in person_parts]

    asked = {u.lower() for u in report["unknown"]}
    asked_words = {w for u in asked for w in u.split()}
    for name in sorted(DUAL_USE - user_allow - asked):
        if re.search(r"(?<![\w@.])" + re.escape(name) + r"(?![\w])", text, re.IGNORECASE):
            if hide["people"] and name not in asked_words and person_signal(name.capitalize()):
                report["unknown"].append(name.capitalize())  # the detector missed it, but the call treats it as a person
            else:
                report["tools_kept"].append(name.capitalize())

    # 7. Safe by default: unsure names are hidden behind numbered stand-ins for this call, longest first,
    # so the clean copy is usable now and the owner reviews the list when it suits them.
    if not hold_unknown(con):
        pending = ([(n, "person") for n in report["unknown"]] + [(n, "company") for n in report["company"]]
                   + [(n, "person") for n, _ in report["ambiguous"]])
        ordered = sorted(dict.fromkeys(pending), key=lambda p: -len(p[0]))
        for name, kind in ordered:  # every full name first, so a company's short form can't split a person's name
            token = standin(con, fname, name, kind)
            report["standins"][name.lower()] = token
            if name.lower() in WORD_NAMES:
                # June, Mark, Will: hide the capitalised uses ("June said"), leave "in june" / "mark it" as written.
                # Safe by default: a capitalised month hidden by mistake costs far less than a client's name left in.
                text, n = re.subn(r"(?<![\w@.])" + re.escape(name[:1].upper() + name[1:].lower()) + r"(?![\w])", token, text)
                if n:
                    hidden[name.lower()] = token
                count(token, n)
                # ...and lowercase uses that read as a person ("talked to hope", "hi june"), via the usual rule
                text, n = sub(mention_re(name), token, text)
            else:
                text, n = sub(word_re(name) if kind == "company" else mention_re(name), token, text)
            count(token, n)
        for name, kind in ordered:  # then short forms: "Olsen" for Olsen Builds, a bare "Derek" for Derek Tanaka
            token = report["standins"][name.lower()]
            shorts = company_variants(name)[1:] if kind == "company" else ([name.split()[0]] if " " in name else [])
            for v in shorts:
                # a person's first name follows them even when it doubles as a month or tool (June, Claude);
                # only the member's own "fine to show" list keeps it visible
                if len(v) < 3 or OURS.match(v) or v.lower() in (user_allow if kind == "person" else allow_low):
                    continue
                if kind == "person" and (v.lower() in WORD_NAMES or v.lower() in GLOSSARY):
                    text, n = re.subn(r"(?<![\w@.])" + re.escape(v[:1].upper() + v[1:].lower()) + r"(?![\w])", token, text)
                    count(token, n)
                text, n = sub(word_re(v) if kind == "company" else mention_re(v), token, text)
                count(token, n)
    return text, report


def clean_filename(name, hidden, table):
    """Hide in the file name everything that was hidden in the call, plus anything on the client table.

    "zoom-2026-09-14-bluefern-kickoff.txt" becomes "zoom-2026-09-14-O001-kickoff.txt", so names
    never reach the clean folder (or an agent) through a file name.
    """
    stem, ext = Path(name).stem, Path(name).suffix
    words = re.sub(r"[-_.]+", " ", stem)
    hidden = dict(hidden)
    # file names often carry just the distinctive first word ("harbor" for Harbor Lane Realty)
    hide = table.get("hide", HIDE_DEFAULT)
    names = list(hidden.items()) + ([(n.lower(), co["code"]) for co in table.get("companies", []) for n in split(co["names"])]
                                    if hide["companies"] else [])
    for orig, token in names:
        hidden.setdefault(orig, token)  # full names first (longest wins), so "harbor lane" beats "harbor"
        first = orig.split()[0] if " " in orig else ""
        if len(first) >= 4 and first.isalpha() and first not in hidden:
            hidden[first] = token
    swaps = sorted(hidden.items(), key=lambda kv: len(kv[0]), reverse=True)
    for orig, token in swaps:
        if re.search(r"[a-z]", orig):
            words = re.sub(r"(?<![\w])" + re.escape(orig).replace(r"\ ", r"[ ]+") + r"(?![\w])", token, words,
                           flags=re.IGNORECASE)
    for pattern, code in table["replacements"]:
        if hide[category(code)]:
            words = re.sub(pattern, code, words, flags=re.IGNORECASE)
    words = words.replace("[PERSON]", "PERSON").replace("[COMPANY]", "COMPANY")
    return re.sub(r"\s+", "-", words.strip()) + ext


def survivors(text, allow):
    """Capitalised words left in a clean copy, for the owner to double-check."""
    allowed = {t for a in allow for t in a.lower().split()} | {g for g in GLOSSARY if " " not in g}
    found = set()
    for m in re.finditer(r"(?<![.!?:\]\n]\s)(?<!^)\b([A-Z][a-z]{2,})\b", text, flags=re.MULTILINE):
        w = m.group(1)
        if not OURS.match(w) and w.lower() not in allowed:
            found.add(w)
    return sorted(found)


# ---------- a cleaning run ----------

def safe_name(name):
    name = Path(name).name
    return name if Path(name).suffix.lower() in TEXT_TYPES else None


def add_inputs(paths=(), texts=()):
    """Copy files/folders (paths) or uploaded (name, text) pairs into dirty/. Originals untouched."""
    added = 0

    def store(name, text):
        n = safe_name(name)
        if not n:
            return 0
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        stem, suffix = Path(n).stem, Path(n).suffix
        number = 2
        while True:
            existing = next((d / n for d in (RAW, HELD, DIRTY) if (d / n).exists()), None)
            if not existing:
                break
            if read_text(existing) == text:
                return 0  # identical re-import, not another copy or a destructive overwrite
            n = f"{stem}-{number}{suffix}"
            number += 1
        (DIRTY / n).write_text(text, encoding="utf-8", newline="\n")
        return 1

    for a in paths:
        p = Path(a)
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else []
        for f in files:
            if safe_name(f.name) and f.resolve().parent != DIRTY.resolve():
                added += store(f.name, read_text(f))
    for name, text in texts:
        added += store(name, text)
    return added


def neutral_filename(con, file):
    row = con.execute("SELECT id FROM call_ids WHERE file=?", (file,)).fetchone()
    call_id = row[0] if row else uuid.uuid4().hex
    if not row:
        con.execute("INSERT INTO call_ids VALUES (?,?)", (file, call_id))
    return f"call-{call_id}{Path(file).suffix.lower()}"


def run(paths=(), texts=(), stats=False):
    """Clean everything waiting. Returns a summary dict (counts only)."""
    with _lock:
        init()
        t0 = time.perf_counter()
        added = add_inputs(paths, texts)
        con = connect()
        decided = apply_review(con)
        con.commit()
        queue = [f for d in (DIRTY, HELD) for f in sorted(d.iterdir()) if f.is_file() and f.suffix.lower() in TEXT_TYPES]
        summary = {"added": added, "decided": decided, "cleaned": 0, "held": 0, "replaced": 0,
                   "new_names": 0, "ambiguous": 0, "to_check": 0, "load_secs": 0.0, "words": 0, "secs": 0.0,
                   "delivered": 0}
        summary["export_failed"] = 0
        if not queue:
            con.close()
            return summary
        t_load = time.perf_counter()
        get_analyzer()
        summary["load_secs"] = time.perf_counter() - t_load
        table = build_table(con)
        allow = get_list(con, "allow")
        stamp = datetime.now().strftime("%m-%d-%Y")
        now = datetime.now().isoformat(timespec="seconds")
        for f in queue:
            raw = read_text(f)
            summary["words"] += len(raw.split())
            cleaned, rep = clean_text(raw, f.name, con, table)
            # this call's unanswered questions that no longer apply go away; the rest keep their place
            still = {("unknown", n.lower()) for n in rep["unknown"]} | {("company", n.lower()) for n in rep["company"]} \
                | {("ambiguous", n.lower()) for n, _ in rep["ambiguous"]} | {("tool", n.lower()) for n in rep["tools_kept"]}
            for name in rep["tools_kept"]:  # listed for a glance, never holds a call
                con.execute("INSERT OR IGNORE INTO review (kind, file, name) VALUES ('tool',?,?)", (f.name, name))
            for q in con.execute("SELECT id, kind, name FROM review WHERE file=? AND decision=''", (f.name,)).fetchall():
                if (q["kind"], q["name"].lower()) not in still:
                    con.execute("DELETE FROM review WHERE id=?", (q["id"],))
            pending = rep["unknown"] or rep["ambiguous"] or rep["company"]
            if pending:
                for kind, found in (("unknown", rep["unknown"]), ("company", rep["company"])):
                    for name in sorted(set(found)):
                        cur = con.execute("INSERT OR IGNORE INTO review (kind, file, name) VALUES (?,?,?)",
                                          (kind, f.name, name))
                        summary["new_names"] += cur.rowcount
                for name, codes in rep["ambiguous"]:
                    cur = con.execute("INSERT OR IGNORE INTO review (kind, file, name, candidates) VALUES (?,?,?,?)",
                                      ("ambiguous", f.name, name, " or ".join(codes)))
                    summary["ambiguous"] += cur.rowcount
                for q in con.execute("SELECT id, name FROM review WHERE file=? AND decision=''", (f.name,)).fetchall():
                    low = q["name"].lower()
                    con.execute("UPDATE review SET mentions=?, speaker=?, token=? WHERE id=?",
                                (len(re.findall(word_re(q["name"]), raw, flags=re.IGNORECASE)),
                                 int(low in rep["speakers"] or any(s.split()[0] == low for s in rep["speakers"] if s.split())),
                                 rep["standins"].get(low, ""), q["id"]))
            if pending and hold_unknown(con):
                if f.parent != HELD:
                    shutil.move(str(f), HELD / f.name)
                prev = con.execute("SELECT clean_name FROM calls WHERE file=?", (f.name,)).fetchone()
                for old in {f.name, (prev["clean_name"] if prev else "") or ""} - {""}:
                    if (CLEAN / old).exists():  # an older clean copy no longer matches your answers
                        remember_legacy_delivery(con, old)
                        (CLEAN / old).unlink()
                    undeliver(con, old)
                con.execute("INSERT OR REPLACE INTO calls (file, status, codes, words, survivors, updated, removed, clean_name) "
                            "VALUES (?,?,?,?,?,?,?,?)", (f.name, "held", "", len(raw.split()), "", now, "", ""))
                summary["held"] += 1
                continue
            summary["hidden_for_review"] = summary.get("hidden_for_review", 0) + len(rep["standins"])
            hide = hide_settings(con)
            kinds = [w for k, w in (("people", "names"), ("companies", "companies"), ("emails", "emails"),
                                    ("phones", "phone numbers")) if hide[k]]
            what = (", ".join(kinds[:-1]) + " and " + kinds[-1]) if len(kinds) > 1 else (kinds[0] if kinds else "nothing")
            header = (f"[Cleaned locally on {stamp}. Hidden: {what}, replaced with codes. "
                      # no literal code here: PERSON-1 is a real person's code now, and Put names back would fill it in
                      + ("Names the cleaner wasn't sure about are hidden as PERSON and COMPANY codes, the same code for the same name in every call. " if rep["standins"] else "")
                      + f"Indirect details kept.]\n\n")
            prev = con.execute("SELECT clean_name FROM calls WHERE file=?", (f.name,)).fetchone()
            prev = (prev["clean_name"] if prev else "") or ""
            cname = neutral_filename(con, f.name)
            taken = {r[0] for r in con.execute("SELECT clean_name FROM calls WHERE file != ?", (f.name,))}
            base, n = cname, 2
            while cname in taken:
                cname = f"{Path(base).stem}-{n}{Path(base).suffix}"
                n += 1
            for old in {prev, f.name} - {cname, ""}:  # an earlier clean copy under another name
                if (CLEAN / old).exists():
                    remember_legacy_delivery(con, old)
                    (CLEAN / old).unlink()
                undeliver(con, old)
            atomic_write(CLEAN / cname, header + cleaned)
            original = RAW / f.name
            if original.exists():
                if read_text(original) != raw:
                    raise ValueError("A different original already exists. Import this as a separate call.")
                f.unlink()
            else:
                shutil.move(str(f), original)
            codes = sorted(set(CODE_RE.findall(cleaned)) | rep["found"])
            left = survivors(cleaned, allow)
            con.execute("INSERT OR REPLACE INTO calls (file, status, codes, words, survivors, updated, removed, clean_name) "
                        "VALUES (?,?,?,?,?,?,?,?)", (f.name, "clean", "," + ",".join(codes) + ",", len(raw.split()),
                                                     ";".join(left), now, json.dumps(rep["removed"]), cname))
            if needs_export_review(con) and not export_approved(con, f.name):
                undeliver(con, cname)
            con.commit()  # a failed export never rolls back a preserved original / clean call
            try:
                if deliver(con, cname):
                    summary["delivered"] += 1
            except (ValueError, OSError) as e:
                con.execute("UPDATE calls SET export_error=? WHERE file=?", (str(e), f.name))
                summary["export_failed"] += 1
            summary["cleaned"] += 1
            summary["replaced"] += rep["replaced"]
            summary["to_check"] += len(left)
        con.commit()
        con.close()
        summary["secs"] = time.perf_counter() - t0
        LOG.mkdir(parents=True, exist_ok=True)
        with (LOG / "run-log.csv").open("a", encoding="utf-8") as lg:
            lg.write(f"{now},cleaned={summary['cleaned']},held={summary['held']},replaced={summary['replaced']},"
                     f"new_names={summary['new_names']},ambiguous={summary['ambiguous']},secs={summary['secs']:.1f}\n")
        return summary


def validate_output(path, home=None):
    out = Path(path).expanduser().resolve()
    vault = Path(home or HOME).resolve()
    if out == vault or out in vault.parents or vault in out.parents:
        raise ValueError("Choose a clean export folder separate from private storage. Neither folder may contain the other.")
    return out


def atomic_write(path, text):
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def output_dir(con):
    """The folder clean copies are also delivered to (like OBS's recording path), or None."""
    d = get_setting(con, "output_dir")
    if not d:
        return None
    try:
        out = validate_output(d)
    except ValueError:
        return None  # legacy unsafe configuration is disabled, never used
    return out if out.is_dir() else None


def deliver(con, name):
    """Copy one clean call to the output folder. Never in practice mode, never the original."""
    out = None if PRACTICE else output_dir(con)
    src = CLEAN / name
    if not out or not src.exists():
        return False
    call = con.execute("SELECT file FROM calls WHERE clean_name=? AND status='clean'", (name,)).fetchone()
    if not call or (needs_export_review(con) and not export_approved(con, call["file"])):
        return False
    target = out / name
    previous = con.execute("SELECT digest FROM deliveries WHERE file=? AND path=?", (call["file"], str(target))).fetchone()
    if target.exists() and (not previous or hashlib.sha256(target.read_bytes()).hexdigest() != previous[0]):
        raise ValueError("The export destination contains a different or edited file with this name. Choose another folder.")
    atomic_write(target, read_text(src))
    con.execute("INSERT OR REPLACE INTO deliveries VALUES (?,?,?,?)", (call["file"], name, str(target), hashlib.sha256(target.read_bytes()).hexdigest()))
    con.execute("UPDATE calls SET export_error='' WHERE file=?", (call["file"],))
    return True


# ---------- the final check before a clean copy goes to your agents ----------

CALENDAR_WORDS = {w.lower() for w in """Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February March
April May June July August September October November December Today Tomorrow Yesterday Morning Afternoon Evening""".split()}
CHECK_PHONE = re.compile(r"(?<![\w-])(?:\+?\d{1,3}[ .-]?)?(?:\(\d{3}\)|\d{3})[ .-]?\d{3}[ .-]?\d{4}(?![\w-])")
NAME_PHRASE = re.compile(r"(?<![\w@.])[A-Z][a-z'’]{1,}(?:[ \t]+(?:[A-Z][a-z'’]{1,}|&|of|and))*(?:[ \t]+[A-Z][a-z'’]{1,})?(?![\w@])")


def _snippet(text, start, end, room=70):
    a, b = max(0, start - room), min(len(text), end + room)
    if a:
        a = text.find(" ", a, start) + 1 or a
    if b < len(text):
        b = text.rfind(" ", end, b) if text.rfind(" ", end, b) > end else b
    return {"before": ("..." if a else "") + text[a:start].replace("\n", " "), "match": text[start:end],
            "after": text[end:b].replace("\n", " ") + ("..." if b < len(text) else "")}


def final_check(con, file):
    """Anything in the clean copy that still looks identifying, so the owner checks it before approving.

    Three kinds, most serious first: a saved client's or company's name, email or phone that is still there;
    an email address or phone number that isn't a code; and capitalised phrases that might be a name the
    detector missed. Respects What to hide, the fine-to-keep list, and per-call "it's fine here" answers.
    """
    path = clean_path(con, file)
    if not path.exists():
        return []
    text = read_text(path)
    hide = hide_settings(con)
    allow = [a.lower() for a in get_list(con, "allow")]
    allow_tokens = {w for a in allow for w in a.split()}
    ok = {r["phrase"].lower() for r in con.execute("SELECT phrase FROM final_ok WHERE file=?", (file,))}
    found, seen = [], set()

    def add(phrase, kind, reason, m):
        key = phrase.lower()
        if key in seen or key in ok or key in allow:
            return
        seen.add(key)
        count = len(re.findall(word_re(phrase), text, flags=re.IGNORECASE)) or 1
        found.append({"phrase": phrase, "kind": kind, "reason": reason, "count": count, **_snippet(text, m.start(), m.end())})

    # 1. saved identifiers that should have become codes
    saved = []
    if hide["people"]:
        for c in con.execute("SELECT * FROM clients"):
            for n in [c["full_name"], c["full_name"].split()[0] if c["full_name"].split() else ""] + split(c["aliases"]):
                if len(n) >= 3:
                    saved.append((n, f"Saved as {c['code']} ({c['full_name']})"))
    if hide["companies"]:
        for c in con.execute("SELECT * FROM companies"):
            for n in split(c["names"]):
                if len(n) >= 3:
                    saved.append((n, f"Saved as {c['code']} ({split(c['names'])[0]})"))
    for c in con.execute("SELECT code, emails, phones FROM clients"):
        if hide["emails"]:
            saved += [(e, f"Saved email for {c['code']}") for e in split(c["emails"])]
    for name, reason in sorted(saved, key=lambda s: -len(s[0])):
        m = re.search(word_re(name), text, flags=re.IGNORECASE)
        if m:
            add(m.group(0), "saved", reason, m)

    # 2. contact details that aren't codes
    if hide["emails"]:
        for m in EMAIL_RE.finditer(text):
            add(m.group(0), "contact", "An email address", m)
    if hide["phones"]:
        for m in CHECK_PHONE.finditer(text):
            if len(digits(m.group(0))) >= 10:
                add(m.group(0), "contact", "A phone number", m)

    # 3. capitalised phrases mid-sentence that might be a name the detector missed
    if hide["people"] or hide["companies"]:
        for m in NAME_PHRASE.finditer(text):
            phrase = m.group(0).strip()
            before = text[max(0, m.start() - 3):m.start()]
            # a line's first word counts as a sentence start, including after a list bullet or a heading mark
            prefix = text[text.rfind("\n", 0, m.start()) + 1:m.start()]
            line_start = (re.fullmatch(r"[ \t]*(?:(?:[-*•>]|#{1,6}|\d+[.)])[ \t]+)?", prefix)
                          or re.search(r"[.!?:\]\[(]\s*$", before))
            words = [w for w in re.split(r"[ \t]+", phrase) if w not in ("&", "of", "and")]
            lows = [w.lower().strip("'’") for w in words]
            if line_start and len(words) == 1:
                continue  # one capitalised word starting a sentence is just grammar
            if all(w in GLOSSARY or w in CALENDAR_WORDS or w in allow_tokens or w in ("i", "i'm", "i'll", "i've", "i'd") for w in lows):
                continue
            if any(OURS.match(w) for w in words) or phrase.lower() in GLOSSARY:
                continue
            if line_start:  # a multi-word phrase at a sentence start: drop the first word if it is ordinary
                if lows[0] in GLOSSARY or lows[0] in CALENDAR_WORDS:
                    continue
            add(phrase, "maybe", "Not a saved client, and not on your fine-to-keep list", m)
    return found


def final_ok(con, file, phrase):
    con.execute("INSERT OR IGNORE INTO final_ok (file, phrase) VALUES (?, ?)", (file, phrase.strip()))


def needs_export_review(con):
    return get_setting(con, "review_before_export", "0") == "1"


def export_approved(con, file):
    row = con.execute("SELECT digest FROM export_approvals WHERE file=?", (file,)).fetchone()
    path = clean_path(con, file)
    return bool(row and path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == row[0])


def approve_export(con, file):
    row = con.execute("SELECT status FROM calls WHERE file=?", (file,)).fetchone()
    if not row or row[0] != "clean":
        raise ValueError("Resolve this call's questions before approving an export.")
    path = clean_path(con, file)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    con.execute("INSERT OR REPLACE INTO export_approvals VALUES (?,?)", (file, digest))
    return deliver(con, path.name)


def undeliver(con, name):
    """Take back a clean copy this app delivered earlier (it was renamed or is held now)."""
    if PRACTICE:
        return
    for row in con.execute("SELECT * FROM deliveries WHERE name=?", (name,)).fetchall():
        p = Path(row["path"])
        try:
            validate_output(p.parent)
            if p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == row["digest"]:
                p.unlink()  # only an unchanged copy this app recorded delivering
            con.execute("DELETE FROM deliveries WHERE file=? AND path=?", (row["file"], row["path"]))
        except (OSError, ValueError):
            pass


def remember_legacy_delivery(con, name):
    out = output_dir(con)
    source = CLEAN / name
    target = out / name if out else None
    if not target or not target.exists() or not source.exists():
        return
    row = con.execute("SELECT file FROM calls WHERE clean_name=? OR (clean_name='' AND file=?)", (name, name)).fetchone()
    if row and source.read_bytes() == target.read_bytes():
        con.execute("INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?)", (row[0], name, str(target), hashlib.sha256(target.read_bytes()).hexdigest()))


def clean_path(con, file):
    """Where a call's clean copy lives (by its cleaned file name)."""
    row = con.execute("SELECT clean_name FROM calls WHERE file=?", (file,)).fetchone()
    name = (row["clean_name"] if row else "") or file
    return CLEAN / name


def deliver_all():
    con = connect()
    try:
        n = 0
        for f in list(CLEAN.iterdir()) if CLEAN.exists() else []:
            if not f.is_file():
                continue
            try:
                n += int(deliver(con, f.name))
            except (OSError, ValueError) as e:
                con.execute("UPDATE calls SET export_error=? WHERE clean_name=?", (str(e), f.name))
        con.commit()
        return n
    finally:
        con.close()


def answers(con):
    """Every past answer the owner can change."""
    return {
        "allow": get_list(con, "allow"),
        "oneoff": get_list(con, "oneoff"),
        "oneoff_company": get_list(con, "oneoff_company"),
        "resolutions": [dict(r) for r in con.execute("SELECT file, name, value FROM resolutions ORDER BY file, name")],
    }


def forget_answer(con, kind, name, file=""):
    """Undo one past answer. The caller re-cleans so every call follows the change."""
    if kind in ("allow", "oneoff", "oneoff_company"):
        con.execute("DELETE FROM lists WHERE list=? AND name=?", (kind, name))
        if kind == "allow":
            con.execute("DELETE FROM lists WHERE list='context_allow' AND name=?", (name,))
    elif kind == "resolution":
        con.execute("DELETE FROM resolutions WHERE file=? AND name=?", (file, name.lower()))


def _to_trash(path):
    """Move a file to the Recycle Bin (Windows) or Trash (Mac), never a permanent delete."""
    path = Path(path)
    if not path.exists():
        return
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        op = SHFILEOPSTRUCTW(wFunc=3, pFrom=str(path.resolve()) + "\0", fFlags=0x0040 | 0x0010 | 0x0004 | 0x0400)
        if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) != 0 or path.exists():
            raise OSError("Couldn't move the call to the Recycle Bin.")
    elif sys.platform == "darwin":
        trash = Path.home() / ".Trash"
        shutil.move(str(path), str(trash / f"{path.stem}-{int(time.time())}{path.suffix}"))
    else:
        trash = Path.home() / ".local" / "share" / "Trash" / "files"
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(trash / path.name))


def rename_call(old, new):
    """Rename a call. It is re-cleaned so its clean copy's file name hides whatever the new name contains."""
    old = Path(old).name
    new = Path(str(new).strip()).name
    if not Path(new).suffix:
        new += Path(old).suffix
    if not safe_name(new) or not Path(new).stem.strip():
        raise ValueError("Use a name ending in .txt, .md, .vtt or .srt.")
    if new == old:
        return old
    with _lock:
        con = connect()
        if con.execute("SELECT 1 FROM calls WHERE file=?", (new,)).fetchone():
            con.close()
            raise ValueError("Another call already has that name.")
        src = next((d / old for d in (RAW, HELD, DIRTY) if (d / old).exists()), None)
        if not src:
            con.close()
            raise ValueError("Couldn't find that call's original.")
        shutil.move(str(src), str(DIRTY / new))  # back through the cleaner under its new name
        forget_call(con, new)  # anything left from an earlier call of that name
        for q in ("UPDATE calls SET file=? WHERE file=?", "UPDATE review SET file=? WHERE file=?",
                  "UPDATE resolutions SET file=? WHERE file=?", "UPDATE call_ids SET file=? WHERE file=?", "UPDATE export_approvals SET file=? WHERE file=?", "UPDATE deliveries SET file=? WHERE file=?",
                  "UPDATE standins SET file=? WHERE file=?", "UPDATE final_ok SET file=? WHERE file=?", "UPDATE suggested_people SET file=? WHERE file=?",
                  "UPDATE suggestion_sources SET file=? WHERE file=?", "UPDATE decisions SET file=? WHERE file=?"):
            con.execute(q, (new, old))
        con.commit()
        con.close()
    run()
    return new


def delete_call(file):
    """Remove one call from the app: original, held and clean copies go to the Recycle Bin/Trash."""
    name = Path(file).name
    with _lock:
        con = connect()
        row = con.execute("SELECT clean_name FROM calls WHERE file=?", (name,)).fetchone()
        cname = (row["clean_name"] if row else "") or ""
        if cname:
            remember_legacy_delivery(con, cname)
        for p in (RAW / name, HELD / name, DIRTY / name, CLEAN / cname if cname else None, CLEAN / name):
            if p is not None:
                _to_trash(p)
        if cname:
            undeliver(con, cname)
        forget_call(con, name)
        con.commit()
        con.close()


VAULT_PARTS = ("dirty", "clean", "held", "raw", "private", "log")


def move_vault(target):
    """Move the private files to a new folder the member picked. Returns the new vault path."""
    target = Path(target)
    if target.resolve() == HOME.resolve():
        raise ValueError("That's already where your files live.")
    if HERE in target.resolve().parents or target.resolve() == HERE:
        raise ValueError("Pick a folder outside the app's own folder, so agents working on the app never see a call.")
    with _lock:
        con = connect()
        export = get_setting(con, "output_dir")
        con.close()
        if export:
            validate_output(export, home=target)
        if target.resolve() in HOME.resolve().parents or HOME.resolve() in target.resolve().parents:
            raise ValueError("Pick a private storage folder separate from the current one.")
        existing = [part for part in VAULT_PARTS if (target / part).exists()]
        if existing and not (target / "private" / "vault.db").exists():
            raise ValueError("That folder already has files with the same names. Pick an empty folder.")
        if (target / "private" / "vault.db").exists():
            other = sqlite3.connect(target / "private" / "vault.db")
            try:
                row = other.execute("SELECT value FROM settings WHERE key='output_dir'").fetchone()
                if row and row[0]:
                    validate_output(row[0], home=target)
            finally:
                other.close()
            set_home(target)  # an existing vault: switch to it, move nothing
            return target
        target.mkdir(parents=True, exist_ok=True)
        for part in VAULT_PARTS:
            if (HOME / part).exists():
                shutil.move(str(HOME / part), str(target / part))
        set_home(target)
        return target


def reclean_all(terms=None):
    """Send originals back through after a change. With terms (the names, emails and phones that changed,
    old and new), only calls that mention one of them are re-checked; held calls always are."""
    words, numbers = None, None
    if terms is not None:
        wanted = {str(x).strip() for x in terms if x and len(str(x).strip()) >= 2}
        wanted |= {w.split()[0] for w in wanted if " " in w and len(w.split()[0]) >= 3}  # "Jane Whitfield" -> calls saying "Jane"
        words = [re.compile(word_re(w), re.IGNORECASE) for w in wanted if re.search(r"[A-Za-z]", w)]
        numbers = {digits(w)[-7:] for w in wanted if len(digits(w)) >= 7}
    with _lock:
        for f in RAW.iterdir():
            if f.is_file():
                if words is not None:
                    original = read_text(f)
                    flat = digits(original) if numbers else ""
                    if not (any(p.search(original) for p in words) or any(n in flat for n in numbers)):
                        continue  # this change can't affect this call
                if (DIRTY / f.name).exists() and read_text(DIRTY / f.name) != read_text(f):
                    raise ValueError("A different call is already queued under this name.")
                shutil.copy2(f, DIRTY / f.name)
    return run()


# ---------- command line ----------

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    init()
    if "--init" in sys.argv:
        print(f"Ready. Folders are in: {HOME}")
        return
    if "onedrive" in str(HOME).lower():
        print("WARNING: this folder is inside OneDrive, so raw transcripts would sync to the cloud. Move it.")
    s = run(paths=args)
    if not (s["cleaned"] or s["held"]):
        print(f"Nothing to clean. (copied in: {s['added']}, decisions applied: {s['decided']})")
        return
    print(f"Cleaned: {s['cleaned']}   Held: {s['held']}   Items replaced: {s['replaced']}")
    if s["new_names"] or s["ambiguous"]:
        print(f"Waiting on you: {s['new_names']} new name(s) or company(ies), {s['ambiguous']} unclear first name(s).")
        print("Open the Transcript Cleaner app to answer them.")
    if s["to_check"]:
        print(f"{s['to_check']} capitalised word(s) left in clean copies to double-check in the app.")
    if s["added"]:
        print(f"Copied in {s['added']} file(s); your originals were left where they were.")
    if "--stats" in sys.argv:
        import psutil
        mem = psutil.Process().memory_info()
        peak = getattr(mem, "peak_wset", mem.rss) / 1e6
        print(f"[stats] model load {s['load_secs']:.1f}s | {s['words']} words | total {s['secs']:.1f}s | "
              f"peak memory {peak:.0f} MB")


if __name__ == "__main__":
    main()

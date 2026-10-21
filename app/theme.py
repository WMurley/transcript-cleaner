"""Turn a design.md (Refero / Google DESIGN.md style) into the app's look.

No AI involved: this reads the colour list, fonts and corner rounding out of
the file and maps them onto the app's own theme settings. Every value is
checked against a strict pattern before it reaches the page, so a design.md
can only change how the app looks, never what it does.
"""

import json
import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
THEMES = Path(os.environ.get("CLEANER_THEMES", HERE.parent / "themes"))  # your look and logo, in the install folder
ACTIVE = THEMES / "active.json"
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
SAFE_FONT = re.compile(r"^[A-Za-z0-9 .\-]{1,40}$")
SAFE_LEN = re.compile(r"^-?\d*\.?\d+(?:px|em)$")
SAFE_SHADOW = re.compile(r"^[\w\s.,()#%-]{1,120}$")
SANS_FALLBACK = '"Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif'
SERIF_FALLBACK = 'Georgia, "Times New Roman", serif'


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "theme"


def _hex6(h):
    h = h.lstrip("#")
    return "#" + ("".join(c * 2 for c in h) if len(h) == 3 else h).lower()


def _rgb(h):
    h = _hex6(h)[1:]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb))


def _lum(h):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _font_list(text):
    out = []
    for f in re.split(r",|\bor\b", text):
        f = f.strip().strip("'\"").strip()
        if f and SAFE_FONT.match(f) and f.lower() not in ("serif", "sans-serif", "monospace"):
            out.append(f)
    return out


def parse(md):
    """Return a theme dict, or raise ValueError with a plain-language reason."""
    name_m = re.search(r"^#\s+(.+?)(?:\s+[—-]\s+Style Reference)?\s*$", md, flags=re.MULTILINE)
    name = (name_m.group(1).strip() if name_m else "Custom")[:40]
    tag_m = re.search(r"^>\s*(.+)$", md, flags=re.MULTILINE)
    mode_m = re.search(r"\*\*Theme:\*\*\s*(light|dark)", md, flags=re.IGNORECASE)

    quick = {}
    q = re.search(r"Quick Color Reference(.+?)(?:\n## |\Z)", md, flags=re.DOTALL | re.IGNORECASE)
    if q:
        for role, hexv in re.findall(r"^-\s*([a-z /&]+?):\s*(#[0-9a-fA-F]{3,6})", q.group(1), flags=re.MULTILINE | re.IGNORECASE):
            quick.setdefault(role.split("/")[0].strip().lower(), _hex6(hexv))
    if "accent" not in quick and "primary action" in quick:
        quick["accent"] = quick["primary action"]
    need = ("text", "background", "accent")
    if not all(k in quick for k in need):
        raise ValueError("This design.md has no colour list the app can read (it needs text, background and accent colours).")
    bg, text, accent = quick["background"], quick["text"], quick["accent"]
    surface = quick.get("card surface") or quick.get("surface") or bg
    border = quick.get("border") or _mix(surface, text, 0.15)

    # a muted text colour: a colour-table row whose role mentions muted/helper/caption, else a blend
    muted = None
    for row in re.findall(r"^\|([^|\n]+)\|\s*`?(#[0-9a-fA-F]{6})`?\s*\|[^|\n]*\|([^|\n]+)\|", md, flags=re.MULTILINE):
        if re.search(r"muted|helper|caption|secondary metadata", row[2], flags=re.IGNORECASE):
            muted = _hex6(row[1])
            break
    muted = muted or _mix(text, bg, 0.42)

    # fonts: Quick Start custom properties, in order (display first, then body)
    families = []
    for var, value in re.findall(r"--font-([a-z0-9-]+):\s*([^;]+);", md):
        first = _font_list(value.split(",")[0])
        if first and first[0] not in [f["family"] for f in families]:
            families.append({"var": var, "family": first[0]})
    sections = {}
    for m in re.finditer(r"^###\s+(.+?)(?:\s+[—-]\s+.*)?$", md, flags=re.MULTILINE):
        start, nxt = m.end(), re.search(r"^###\s", md[m.end():], flags=re.MULTILINE)
        sections[m.group(1).strip().lower()] = md[start: start + nxt.start() if nxt else len(md)]

    def stack(fam):
        sec = sections.get(fam["family"].lower(), "")
        subs = re.search(r"\*\*Substitute:\*\*\s*(.+)", sec)
        names = [fam["family"]] + (_font_list(subs.group(1)) if subs else [])
        serif = "serif" in sec.lower() and "sans" not in sec.lower()
        mono = "mono" in fam["family"].lower()
        fallback = 'ui-monospace, Consolas, monospace' if mono else (SERIF_FALLBACK if serif else SANS_FALLBACK)
        return ", ".join(f'"{n}"' for n in names) + ", " + fallback

    def lead_role(fam):
        """The first clause of a family's Role line, e.g. 'Display and hero headlines'."""
        role = re.search(r"\*\*Role:\*\*\s*([^\n]+)", sections.get(fam["family"].lower(), ""))
        return re.split(r"[.,;—]", role.group(1))[0].lower() if role else ""

    text_fams = [f for f in families if "mono" not in f["family"].lower() and f["family"].lower() != "math"]
    display = next((f for f in text_fams if re.search(r"display|headline|hero|heading", lead_role(f))), None)
    ui = next((f for f in text_fams if f is not display and re.search(r"\bbody\b|\bui\b|interface|navigation|chrome|text", lead_role(f))), None)
    if display or ui:
        heading_font = stack(display or ui)
        body_font = stack(ui or display)
        text_fams = [f for f in (display, ui) if f] + [f for f in text_fams if f not in (display, ui)]
    else:
        heading_font = stack(text_fams[0]) if text_fams else SANS_FALLBACK
        body_font = stack(text_fams[1]) if len(text_fams) > 1 else heading_font

    def section(title):
        m = re.search(rf"^###\s+{re.escape(title)}[^\n]*\n(.*?)(?=^###\s|^##\s|\Z)", md, flags=re.MULTILINE | re.DOTALL)
        return m.group(1) if m else ""

    def first_px(text, default, lo, hi):
        m = re.search(r"(\d+)(?:\s*-\s*\d+)?\s*px", text or "")  # "24-32px" -> 24
        return max(lo, min(hi, int(m.group(1)))) if m else default

    # headings: the display family's regular weight (serif display faces are usually 400)
    heading_sec = sections.get(text_fams[0]["family"].lower(), "") if text_fams else ""
    weights = [int(w) for w in re.findall(r"\b([1-9]00)\b", (re.search(r"\*\*Weights:\*\*([^\n]+)", heading_sec) or [None, ""])[1])]
    serif_heading = "serif" in heading_font and "sans-serif" not in heading_font.split(",")[-1]
    heading_weight = (400 if 400 in weights else min(weights)) if (weights and serif_heading) else 650
    # body letter-spacing, if the design sets one
    body_sec = sections.get(text_fams[1]["family"].lower(), "") if len(text_fams) > 1 else heading_sec
    # Only a single body value counts ("0.1em to 0.2em for small caps labels" is for labels, not reading text),
    # and it stays near normal so paragraphs and transcripts remain easy to read.
    trk = re.search(r"\*\*Letter spacing:\*\*\s*(-?\d*\.?\d+)(em|px)([^\n]*)", body_sec)
    tracking = "normal"
    if trk and not re.search(r"\bto\b|label|caps|display", trk.group(3), flags=re.IGNORECASE):
        value = float(trk.group(1)) / (16 if trk.group(2) == "px" else 1)
        tracking = f"{max(-0.03, min(0.02, value)):.3f}em" if value else "normal"
    # page heading size from the type scale (kept app-sized)
    hs = re.search(r"--text-heading:\s*(\d+)px", md)
    h1 = max(22, min(30, int(hs.group(1)))) if hs else 22
    # density and spacing
    dens = (re.search(r"\*\*Density:\*\*\s*(\w+)", md) or [None, "comfortable"])[1].lower()
    row_pad = {"compact": 8, "comfortable": 12, "spacious": 15}.get(dens, 11)
    card_pad = first_px((re.search(r"\*\*Card padding:\*\*([^\n]+)", md) or [None, ""])[1], 18, 14, 30)
    gap = first_px((re.search(r"\*\*Element gap:\*\*([^\n]+)", md) or [None, ""])[1], 18, 12, 28)
    # buttons: weight and padding from the primary button description
    cta = section("Primary CTA Button") or section("Primary Button") or section("Button")
    bw = re.search(r"\b([4-8]00)\b", cta)
    btn_weight = int(bw.group(1)) if bw else 500
    bp = re.search(r"padding\s+(\d+)px\s+(\d+)px", cta)
    btn_pad = f"{max(6, round(int(bp.group(1)) * 0.7))}px {max(12, round(int(bp.group(2)) * 0.75))}px" if bp else "7px 14px"
    # small labels: all caps if the design's eyebrow/label style says so
    eyebrow = section("Eyebrow Label") or section("Eyebrow")
    caps = bool(re.search(r"all caps|uppercase", eyebrow, flags=re.IGNORECASE))
    # floating panels: the design's own large shadow, if it has a safe one
    sh = re.search(r"--shadow-xl:\s*([^;\n]+);", md) or re.search(r"--shadow-lg:\s*([^;\n]+);", md)
    shadow = sh.group(1).strip() if sh and SAFE_SHADOW.match(sh.group(1).strip()) else ""

    def radius(label, default):
        m = re.search(rf"^\|\s*{label}\s*\|\s*(\d+)px\s*\|", md, flags=re.MULTILINE | re.IGNORECASE)
        return min(int(m.group(1)), 999) if m else default

    return {
        "name": name, "tagline": (tag_m.group(1).strip()[:80] if tag_m else ""),
        "mode": (mode_m.group(1).lower() if mode_m else ("dark" if _lum(bg) < 0.2 else "light")),
        "bg": bg, "panel": surface, "line": border, "text": text,
        "panel2": _mix(surface, border, 0.45) if contrast(surface, border) < 2.5 else _mix(surface, text, 0.05),
        "muted": muted, "accent": accent, "accent_soft": _mix(bg, accent, 0.13),
        "accent_text": "#ffffff" if _lum(accent) < 0.35 else "#111111",
        "font_heading": heading_font, "font_body": body_font,
        # transcripts are read closely: a narrow interface face gets a regular-width font for reading text
        "font_reading": SANS_FALLBACK if re.search(r"condensed|narrow|compressed|compact", body_font.split(",")[0], flags=re.IGNORECASE) else body_font,
        "r_card": radius("cards", 10), "r_button": radius("buttons", 8), "r_input": radius("inputs", 8),
        "heading_weight": heading_weight, "tracking": tracking, "h1": h1, "row_pad": row_pad, "card_pad": card_pad,
        "gap": gap, "btn_weight": btn_weight, "btn_pad": btn_pad, "label_caps": caps, "shadow_float": shadow,
        "flat": bool(re.search(r"\bno (?:drop )?shadows?\b|don't (?:apply|use|add) (?:any )?(?:drop )?shadows?", md, flags=re.IGNORECASE)),
    }


def contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _toward(color, target, against, ratio):
    """Mix color toward target until it reaches the contrast ratio against a background."""
    for step in range(0, 21):
        c = _mix(color, target, step / 20)
        if contrast(c, against) >= ratio:
            return c
    return target


def _finish(t):
    """Readability and structure guarantees, whatever the design.md says."""
    deep = "#000000" if t["mode"] == "dark" else t["text"]
    t["bg"] = _toward(t["bg"], deep, t["panel"], 1.12)         # the page sits visibly behind the cards
    t["panel2"] = _toward(t["panel2"], t["text"], t["panel"], 1.06)  # insets (quotes, table headers) read as insets
    t["line"] = _toward(t["line"], t["text"], t["panel"], 1.45)      # card edges are visible
    t["line_strong"] = _toward(t["line"], t["text"], t["panel"], 2.6)  # buttons and fields stand out from cards
    t["muted"] = _toward(t["muted"], t["text"], t["panel2"], 5.0)
    pale = contrast(t["accent"], t["panel"]) < 1.6
    if not pale:  # an ordinary accent still has to read against the page
        t["accent"] = _toward(t["accent"], "#ffffff" if t["mode"] == "dark" else "#000000", t["bg"], 3.0)
    t["accent_text"] = "#ffffff" if contrast("#ffffff", t["accent"]) >= contrast("#111111", t["accent"]) else "#111111"
    t["accent_fg"] = t["text"] if pale else (t["accent"] if contrast(t["accent"], t["panel"]) >= 3 else _toward(t["accent"], t["text"], t["panel"], 3.0))
    t["accent_edge"] = t["line_strong"] if pale else t["accent"]
    t["accent_soft"] = _toward(t["accent_soft"], t["accent"], t["panel"], 1.08)
    t["line_soft"] = t["line"] if contrast(t["line"], t["panel"]) < 2 else _mix(t["panel"], t["line"], 0.3)
    return t


def derive_other(t):
    """A design.md usually describes one mode. Work out the other from the same colours."""
    o = dict(t)
    if t["mode"] == "light":
        o["mode"] = "dark"
        o["bg"] = _mix(t["text"], "#000000", 0.45)
        o["panel"] = _mix(o["bg"], t["bg"], 0.06)
        o["panel2"] = _mix(o["bg"], t["bg"], 0.12)
        o["line"] = _mix(o["bg"], t["bg"], 0.20)
        o["text"] = t["bg"] if _lum(t["bg"]) > 0.6 else "#ededed"
        o["muted"] = _mix(o["text"], o["bg"], 0.35)
        o["accent_soft"] = _mix(o["bg"], t["accent"], 0.22)
    else:
        o["mode"] = "light"
        o["bg"] = _mix("#ffffff", t["accent"], 0.03)
        o["panel"] = "#ffffff"
        o["panel2"] = _mix(o["bg"], "#000000", 0.05)
        o["line"] = _mix(o["bg"], "#000000", 0.13)
        o["text"] = t["bg"] if _lum(t["bg"]) < 0.05 else "#1b1f24"
        o["muted"] = _mix(o["text"], o["bg"], 0.42)
        o["accent_soft"] = _mix(o["bg"], t["accent"], 0.13)
    return _finish(o)


def _vars(t):
    v = (f"--bg:{t['bg']};--panel:{t['panel']};--panel-2:{t['panel2']};--line:{t['line']};--text:{t['text']};"
         f"--muted:{t['muted']};--accent:{t['accent']};--accent-soft:{t['accent_soft']};--accent-text:{t['accent_text']};"
         f"--font-heading:{t['font_heading']};--font-body:{t['font_body']};--font-reading:{t['font_reading']};"
         f"--radius:{t['r_card']}px;--radius-btn:{t['r_button']}px;--radius-input:{t['r_input']}px;"
         f"--line-strong:{t['line_strong']};--line-soft:{t['line_soft']};--accent-fg:{t['accent_fg']};--accent-edge:{t['accent_edge']};"
         f"--shadow:{'0 1px 2px rgba(16,24,40,.08), 0 3px 10px rgba(16,24,40,.06)' if t['mode'] == 'light' and not t.get('flat') else 'none'};color-scheme:{t['mode']};"
         f"--heading-weight:{t['heading_weight']};--tracking:{t['tracking']};--h1-size:{t['h1']}px;"
         f"--row-pad:{t['row_pad']}px;--pad-card:{t['card_pad']}px;--gap:{t['gap']}px;"
         f"--btn-weight:{t['btn_weight']};--btn-pad:{t['btn_pad']};"
         f"--label-transform:{'uppercase' if t['label_caps'] else 'none'};--label-tracking:{'0.06em' if t['label_caps'] else 'normal'};"
         + (f"--shadow-float:{t['shadow_float']};" if t["shadow_float"] else ""))
    # status colours (clean / waiting / warning / highlight) follow the mode
    v += ("--green:#17734a;--green-soft:#e3f5ec;--amber:#8a5a09;--amber-soft:#fbeed6;--red:#b03a31;"
          "--red-soft:#fbe9e7;--mark:#ffe58f;" if t["mode"] == "light" else
          "--green:#4cc38a;--green-soft:#15302a;--amber:#e3a646;--amber-soft:#352914;--red:#ef7a70;"
          "--red-soft:#3a1f1d;--mark:#6b5a17;")
    return v


def to_css(t):
    if not t:
        return ""
    native = _finish(dict(t))
    other = derive_other(t)
    light, dark = (native, other) if native["mode"] == "light" else (other, native)
    return (f":root{{{_vars(light)}}}\n:root[data-mode=\"dark\"]{{{_vars(dark)}}}\n"
            f"@media (prefers-color-scheme: dark){{:root:not([data-mode=\"light\"]){{{_vars(dark)}}}}}\n")


def save(md, filename="design.md"):
    t = parse(md)
    THEMES.mkdir(exist_ok=True)
    s = slug(t["name"])
    (THEMES / f"{s}.md").write_text(md, encoding="utf-8")
    use(s)
    return s


def themes():
    out = []
    if THEMES.exists():
        for p in sorted(THEMES.glob("*.md")):
            try:
                t = parse(p.read_text(encoding="utf-8"))
                d = derive_other(t)
                out.append({"id": p.stem, "name": t["name"], "tagline": t["tagline"], "native": t["mode"],
                            "swatches": [t["bg"], t["panel"], t["accent"], t["text"]],
                            "swatches_other": [d["bg"], d["panel"], d["accent"], d["text"]]})
            except ValueError:
                continue
    return out


def _settings():
    try:
        return json.loads(ACTIVE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(**changes):
    THEMES.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(json.dumps({**_settings(), **changes}), encoding="utf-8")


def active_id():
    return _settings().get("active", "")


def mode():
    m = _settings().get("mode", "auto")
    return m if m in ("auto", "light", "dark") else "auto"


def tour_done():
    return bool(_settings().get("tour_done"))


def set_tour_done(done):
    _write(tour_done=bool(done))


def set_mode(m):
    if m not in ("auto", "light", "dark"):
        raise ValueError("Mode must be auto, light or dark.")
    _write(mode=m)


def use(theme_id):
    if theme_id and not (THEMES / f"{theme_id}.md").exists():
        raise ValueError("That theme isn't installed.")
    _write(active=theme_id)


# ---------- name and logo ----------

DEFAULT_NAME = "Transcript Cleaner"
LOGO = THEMES / "logo.png"
LOGO_ICO = THEMES / "logo.ico"


def brand():
    name = _settings().get("name") or DEFAULT_NAME
    return {"name": name, "has_logo": LOGO.exists(), "logo_v": int(LOGO.stat().st_mtime) if LOGO.exists() else 0}


def set_name(name):
    name = re.sub(r"[\x00-\x1f<>]", "", (name or "")).strip()[:40]
    _write(name=name if name and name != DEFAULT_NAME else "")


def set_logo(png):
    """png: bytes of a square PNG, at most 256 pixels (the app shrinks it in the browser first)."""
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 2_000_000:
        raise ValueError("That image couldn't be read. Try a PNG or JPG.")
    w, h = int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")
    if not (16 <= w <= 256 and 16 <= h <= 256):
        raise ValueError("The logo needs to be between 16 and 256 pixels.")
    THEMES.mkdir(parents=True, exist_ok=True)
    LOGO.write_bytes(png)
    # Windows icons can carry a PNG inside them, so the desktop shortcut can use the same picture
    header = (0).to_bytes(2, "little") + (1).to_bytes(2, "little") + (1).to_bytes(2, "little")
    entry = bytes([w % 256, h % 256, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little") \
        + len(png).to_bytes(4, "little") + (22).to_bytes(4, "little")
    LOGO_ICO.write_bytes(header + entry + png)


def clear_logo():
    for p in (LOGO, LOGO_ICO):
        if p.exists():
            p.unlink()


def accent():
    """The current look's accent colour (light-mode value), or '' for the default look."""
    tid = active_id()
    p = THEMES / f"{tid}.md" if tid else None
    try:
        if p and p.exists():
            t = parse(p.read_text(encoding="utf-8"))
            return _finish(dict(t))["accent"] if t["mode"] == "light" else derive_other(t)["accent"]
    except ValueError:
        pass
    return ""


def active_css():
    tid = active_id()
    if not tid:
        return ""
    p = THEMES / f"{tid}.md"
    try:
        return to_css(parse(p.read_text(encoding="utf-8"))) if p.exists() else ""
    except ValueError:
        return ""

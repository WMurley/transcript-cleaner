"""Local identity forms. Changes are transactional; no model or external service."""
import re
import clean


def names(value):
    return ";".join(dict.fromkeys(x.strip() for x in re.split(r"[;,\n]", value or "") if x.strip()))


def duplicate(con, kind, value, exclude=""):
    table, field = ("clients", "full_name") if kind == "person" else ("companies", "names")
    wanted = {n.casefold() for n in clean.split(names(value))}
    return [dict(r) for r in con.execute(f"SELECT * FROM {table}")
            if r["code"] != exclude and wanted & {n.casefold() for n in clean.split(r[field])}]


def suggestions(con, review, text=None):
    if text is None:
        path = next((d / review["file"] for d in (clean.HELD, clean.RAW, clean.DIRTY) if (d / review["file"]).exists()), None)
        text = clean.read_text(path) if path else ""
    companies = [r["name"] for r in con.execute("SELECT name FROM review WHERE file=? AND kind='company'", (review["file"],))]
    company = companies[0] if len(companies) == 1 else ""
    company_code = ""
    for co in con.execute("SELECT * FROM companies"):
        if any(re.search(clean.word_re(n), text, re.I) for n in clean.split(co["names"])):
            if company_code:
                company_code = ""
                break
            company_code = co["code"]
    return {"company_names": ", ".join(clean.company_variants(company)) if company else "",
            "company_code": company_code,
            "emails": ", ".join(dict.fromkeys(clean.EMAIL_RE.findall(text))),
            "phones": ", ".join(dict.fromkeys(re.findall(r"(?:\(\d{3}\)|\d{3})[ .-]\d{3}[ .-]\d{4}", text))),
            "company_variants": ", ".join(clean.company_variants(review["name"]))}


def save(con, body):
    review = con.execute("SELECT * FROM review WHERE id=?", (body.get("review_id"),)).fetchone() if body.get("review_id") else None
    if body.get("review_id") and review is None:
        raise ValueError("That question has already been answered. Refresh and try again.")
    file, detected = (review["file"], review["name"]) if review else (str(body.get("file", "")), str(body.get("detected", "")).strip())
    if not detected:
        raise ValueError("Enter the exact name or phrase you want to tag.")
    if not review:
        if not clean.safe_name(file) or file != clean.safe_name(file):
            raise ValueError("Choose a call in this app.")
        path = next((d / file for d in (clean.RAW, clean.HELD, clean.DIRTY) if (d / file).exists()), None)
        if not path or not re.search(clean.word_re(detected), clean.read_text(path), re.I):
            raise ValueError("That phrase is not in the original call. Check the spelling.")
    kind = body.get("kind", "person")
    if kind not in ("person", "company"):
        raise ValueError("Choose Person or Company.")
    action = body.get("action", "new")
    code = str(body.get("code", ""))
    if action == "tool":
        clean.add_to_list(con, "allow", detected)
        clean.add_to_list(con, "context_allow", detected)
        clean.add_to_list(con, "tools", detected)
        if review:
            con.execute("DELETE FROM review WHERE id=?", (review["id"],))
        return ""
    if action in ("hide_call", "hide_always", "keep", "link_call"):
        if action == 'link_call':
            table = 'clients' if kind == 'person' else 'companies'
            if not con.execute(f'SELECT 1 FROM {table} WHERE code=?', (code,)).fetchone():
                raise ValueError('Choose an existing record for this call.')
            token = code + '-EMAIL' if clean.EMAIL_RE.fullmatch(detected) else code + '-PHONE' if len(clean.digits(detected)) >= 7 and not re.search(r'[A-Za-z]', detected) else code
            con.execute('INSERT OR REPLACE INTO resolutions VALUES (?,?,?)', (file, detected.lower(), token))
        elif action == "hide_call":
            token = "[PERSON]" if kind == "person" else "[COMPANY]"
            con.execute("INSERT OR REPLACE INTO resolutions VALUES (?,?,?)", (file, detected.lower(), token))
        else:
            listing = "allow" if action == "keep" else "oneoff" if kind == "person" else "oneoff_company"
            clean.add_to_list(con, listing, detected)
            if action == "keep" and kind == "company":
                clean.add_to_list(con, "context_allow", detected)
        code = ""
    elif action in ("new", "existing"):
        if kind == "company":
            value = names(body.get("names", ""))
            if action == "new":
                if not value:
                    raise ValueError("Enter a company name.")
                matches = duplicate(con, kind, value)
                if matches and not body.get("distinct"):
                    raise ValueError("This company already exists. Choose Link existing, or confirm it is a separate company.")
                code = clean.add_company(con, names(value + ";" + detected))
            else:
                row = con.execute("SELECT * FROM companies WHERE code=?", (code,)).fetchone()
                if not row:
                    raise ValueError("Choose an existing company.")
                con.execute("UPDATE companies SET names=? WHERE code=?", (names(row["names"] + ";" + value + ";" + detected), code))
        else:
            full_name = str(body.get("full_name", "")).strip()
            aliases = names(body.get("aliases", ""))
            company_code = str(body.get("company_code", ""))
            if body.get("company_names", "").strip():
                company_names = names(body["company_names"])
                matches = duplicate(con, "company", company_names)
                if len(matches) > 1:
                    raise ValueError("Several companies match. Choose the existing company explicitly.")
                company_code = matches[0]["code"] if matches else clean.add_company(con, company_names)
            if company_code and not con.execute("SELECT 1 FROM companies WHERE code=?", (company_code,)).fetchone():
                raise ValueError("Choose a company from the list.")
            if action == "new":
                if not full_name:
                    raise ValueError("Enter the person's name.")
                matches = duplicate(con, kind, full_name)
                if matches and not body.get("distinct"):
                    raise ValueError("This person already exists. Choose Link existing, or confirm it is a different person with the same name.")
                code = clean.add_client(con, full_name, names(aliases + ";" + (detected if detected.lower() != full_name.lower() else "")), company_code,
                                        names(body.get("emails", "")), names(body.get("phones", "")))
            else:
                row = con.execute("SELECT * FROM clients WHERE code=?", (code,)).fetchone()
                if not row:
                    raise ValueError("Choose an existing person.")
                con.execute("UPDATE clients SET aliases=?, company_code=?, emails=?, phones=? WHERE code=?",
                            (names(row["aliases"] + ";" + aliases + ";" + (detected if detected.lower() != row["full_name"].lower() else "")),
                             company_code or row["company_code"], names(row["emails"] + ";" + body.get("emails", "")),
                             names(row["phones"] + ";" + body.get("phones", "")), code))
    else:
        raise ValueError("Choose how this name should be handled.")
    if review:
        con.execute("DELETE FROM review WHERE id=?", (review["id"],))
    return code


def group_rows(con, ids):
    if not isinstance(ids, list) or not ids or len(ids) > 500:
        raise ValueError('Choose between one and 500 questions.')
    if any(not isinstance(i, int) or isinstance(i, bool) for i in ids) or len(set(ids)) != len(ids):
        raise ValueError('Choose distinct question IDs.')
    rows = [con.execute('SELECT * FROM review WHERE id=? AND decision=\'\'', (i,)).fetchone() for i in ids]
    if any(r is None for r in rows):
        raise ValueError('A selected question changed. Refresh and check the group again.')
    keys = {(r['kind'], r['name'].casefold(), r['candidates']) for r in rows}
    if len(keys) != 1:
        raise ValueError('Only matching questions with the same choices can be grouped.')
    return rows


def save_group(con, body):
    rows = group_rows(con, body.get('review_ids'))
    if rows[0]['kind'] == 'ambiguous':
        raise ValueError('Choose a listed answer for an ambiguous first name.')
    code = save(con, {**body, 'review_id': rows[0]['id']})
    for row in rows[1:]:
        if body.get('action') in ('hide_call', 'link_call'):
            save(con, {**body, 'review_id': row['id']})
        else:
            con.execute('DELETE FROM review WHERE id=?', (row['id'],))
    return code


def merge(con, keep, remove):
    if keep == remove or not re.fullmatch(r"[CO]\d{3,}", keep) or not re.fullmatch(r"[CO]\d{3,}", remove) or keep[0] != remove[0]:
        raise ValueError("Choose two different records of the same type.")
    table = "clients" if keep.startswith("C") else "companies"
    a = con.execute(f"SELECT * FROM {table} WHERE code=?", (keep,)).fetchone()
    b = con.execute(f"SELECT * FROM {table} WHERE code=?", (remove,)).fetchone()
    if not a or not b:
        raise ValueError("One of those records no longer exists.")
    if table == "clients":
        if a["company_code"] and b["company_code"] and a["company_code"] != b["company_code"]:
            raise ValueError("These people link to different companies. Confirm their company before merging.")
        aliases = names(a["aliases"] + ";" + b["aliases"] + ";" + (b["full_name"] if b["full_name"].lower() != a["full_name"].lower() else ""))
        notes = "\n".join(dict.fromkeys(v for v in (a["notes"], b["notes"]) if v))
        con.execute("UPDATE clients SET aliases=?, emails=?, phones=?, company_code=?, notes=? WHERE code=?",
                    (aliases, names(a["emails"] + ";" + b["emails"]), names(a["phones"] + ";" + b["phones"]), a["company_code"] or b["company_code"], notes, keep))
    else:
        con.execute("UPDATE companies SET names=? WHERE code=?", (names(a["names"] + ";" + b["names"]), keep))
        con.execute("UPDATE clients SET company_code=? WHERE company_code=?", (keep, remove))
    con.execute("UPDATE resolutions SET value=? WHERE value=?", (keep, remove))
    con.execute(f"DELETE FROM {table} WHERE code=?", (remove,))

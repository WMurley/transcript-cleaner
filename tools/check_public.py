"""Fail if a folder holds anything that must not be public. Run it on the public snapshot before every push.

    python tools/check_public.py <folder> [--denylist FILE]

Checks every file for local paths, file links, personal email addresses, private network addresses,
secret-looking strings, symlinks and binary files. A denylist (one term per line, # for notes) adds the
maintainer's own private terms: real names, internal product names, hostnames. The denylist itself never
goes in the public copy. A line containing public-ok was checked by a person and is skipped.
A pass only means these patterns found nothing; a person still reads the diff.
"""

import argparse
import re
import sys
from pathlib import Path

PATTERNS = [
    ("local path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s'\"]+|/Users/[a-z][\w.-]*/|/home/[a-z][\w.-]*/", re.I)),
    ("file link", re.compile(r"file:/{2}", re.I)),
    ("personal email", re.compile(r"[\w.+-]+@(?:gmail|googlemail|outlook|hotmail|live|yahoo|icloud|me|proton|protonmail|aol)\.(?:com|me)\b", re.I)),
    ("private network address", re.compile(r"\b(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b|\.ts\.net\b", re.I)),
    ("secret-looking string", re.compile(r"sk-ant-[\w-]{10,}|sk-[A-Za-z0-9]{32,}|ghp_[A-Za-z0-9]{30,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}|xox[abp]-[\w-]{10,}"
                                         r"|-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
TEXT_LIMIT = 5_000_000


def load_denylist(path):
    if not path or not Path(path).exists():
        return []
    terms = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append((line, re.compile(r"(?<![\w])" + re.escape(line) + r"(?![\w])", re.I)))
    return terms


def check(folder, denylist=None):
    folder = Path(folder)
    problems = []
    deny = load_denylist(denylist)
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder).as_posix()
        if rel.startswith(".git/") or rel == ".git":
            continue
        if p.is_symlink():
            problems.append(f"{rel}: symlink")
            continue
        if not p.is_file():
            continue
        data = p.read_bytes()[:TEXT_LIMIT]
        if b"\0" in data:
            problems.append(f"{rel}: binary file")
            continue
        text = data.decode("utf-8", errors="replace")
        for n, line in enumerate(text.splitlines(), 1):
            if "public-ok" in line:  # a person checked this line (an invented address, say) and marked it fine
                continue
            for label, rx in PATTERNS:
                if rx.search(line):
                    problems.append(f"{rel}:{n}: {label}")
            for term, rx in deny:
                if rx.search(line):
                    problems.append(f"{rel}:{n}: private term ({term[:3]}...)")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder")
    ap.add_argument("--denylist", default=str(Path(__file__).resolve().parent.parent / ".public-denylist"))
    args = ap.parse_args()
    problems = check(args.folder, args.denylist)
    for p in problems:
        print(p)
    print(f"\n{len(problems)} problem(s)" if problems else "Public check passed: no local paths, personal emails, private addresses, secrets, private terms, symlinks or binary files.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()

"""Build the public copy: this repo's committed files, minus what .publicignore lists, as a fresh one-commit repo.

    python tools/make_public_snapshot.py <new empty folder> [--email NOREPLY] [--name NAME]

The private repo keeps its full history; the public one starts clean, so nothing ever removed from the
private history (old docs, third-party files) can be read there. Only committed files are copied, so
local vaults, settings and test output never travel. The public check must pass or no commit is made.
Nothing is pushed: creating the public GitHub repo and pushing stay with the owner.
"""

import argparse
import fnmatch
import io
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_public  # noqa: E402


def git(*args, cwd=HERE, data=None):
    return subprocess.run(["git", *args], cwd=cwd, input=data, capture_output=True, check=True).stdout


def ignored(rel, patterns):
    return any(fnmatch.fnmatch(rel, p) or rel.startswith(p.rstrip("/") + "/") for p in patterns)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("target")
    ap.add_argument("--name", default="Wade Murley")
    ap.add_argument("--email", default="162849498+WMurley@users.noreply.github.com")
    ap.add_argument("--message", default="Transcript Cleaner: first public release")
    args = ap.parse_args()

    target = Path(args.target).resolve()
    if target.exists() and any(target.iterdir()):
        sys.exit(f"{target} is not empty. Choose a new folder.")
    if HERE in target.parents or target == HERE:
        sys.exit("Choose a folder outside this repo.")
    if git("status", "--porcelain").strip():
        print("Note: uncommitted changes are left out; only committed files are copied.")

    patterns = [l.strip() for l in (HERE / ".publicignore").read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]
    archive = tarfile.open(fileobj=io.BytesIO(git("archive", "--format=tar", "HEAD")))
    target.mkdir(parents=True, exist_ok=True)
    kept = 0
    for m in archive.getmembers():
        if not m.isfile() or ignored(m.name, patterns):
            continue
        out = target / m.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(archive.extractfile(m).read())
        kept += 1
    print(f"Copied {kept} committed files to {target}")

    problems = check_public.check(target, HERE / ".public-denylist")
    if problems:
        print("\n".join(problems))
        sys.exit(f"\n{len(problems)} problem(s): fix them in this repo, commit, and build again. No public commit was made.")
    if not (target / "LICENSE").exists():
        print("Warning: no LICENSE file. Without one, people can read the code but have no right to use it.")

    git("init", "-q", "-b", "main", cwd=target)
    git("add", "-A", cwd=target)
    git("-c", f"user.name={args.name}", "-c", f"user.email={args.email}", "commit", "-q", "-m", args.message, cwd=target)
    print(f"Public check passed. One commit by {args.name} <{args.email}>. Not pushed.")


if __name__ == "__main__":
    main()

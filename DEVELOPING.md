# Developing Transcript Cleaner

How the app works in detail and how to set it up by hand. Using the app is covered in [README.md](README.md) and [SETUP.md](SETUP.md).

Tested on Windows 11, macOS 15.6 and macOS 26.6 (both Apple Silicon). Windows 10 and Intel Macs are supported by the setup scripts but haven't been tested.

## How it works

- **Safe by default.** A call is never stuck waiting on you. Any name the cleaner isn't sure about is hidden behind a stand-in (PERSON-1, COMPANY-1): one per name, the same in every call and every time a call is cleaned again, and a number is never reused for someone else, even after its calls are deleted. The call is clean straight away. Full names are replaced before their short forms, so "Derek Olsen from Olsen Builds" becomes "PERSON-1 from COMPANY-1", and a bare "Bluefern" next to an unsure "Bluefern Bakery" takes the company's stand-in.
- **Review names** is grouped by call: one card per call, newest first, with the call's name as the heading. A name said in more than one call is asked once, in an "In more than one call" card at the top. Inside a card, which-client questions come first, then speakers, then names by how often they're mentioned. A progress bar counts names reviewed since the app opened. Each row: **This is me**, **Save as a client** or **Save as a company**, **Fine to show**, **It's a tool** (single words, remembered for good), or **Keep hidden** (stays a stand-in, leaves the list). **Keep all N hidden** clears the list in one click. **See where** shows each place the name was said. Names kept visible as AI tools fold away below.
- **Undo.** Every one-click answer (Fine to show, Keep hidden, It's a tool, a which-client pick, hide or link in one call, On my team, This is me, and the final check's Leave it) shows a pop-up with **Undo** for 10 seconds, and is listed on **Recent decisions** with Undo. `decisions.py` logs each answer as the exact difference it made, and Undo reverses it and re-checks the calls that mention the name. Renamed calls keep their decisions; deleting a call removes the decisions about that call only. Saving a new client goes through the Clients page instead and isn't logged.
- **Your team** (Settings): teammates and tools that are fine to show in every call, first names included. **Copy team list** gives plain text (one name per line, `tool: Name` for tools); teammates use **Paste or open a team list**, see a preview, then add. A saved client is never accepted as a teammate, so someone else's list can't un-hide a client. On Review names, someone speaking on the call gets **On my team** in place of Fine to show.
- **Your own name** is asked once (on Review names, or in Settings > What to hide) and stays visible in every call. Until it's set, speakers get a **This is me** button.
- **AI tool names that are also first names** (Claude, Gemini, Hermes, Siri and others) stay visible as tools unless the call shows a person: a speaker label, a greeting ("Hi Claude"), "Claude's wife", "Claude from accounting", or he/she referring back to the name (tools are "it"). **It's a person: hide it** reverses one for good.
- **Strict mode** (Settings > What to hide): calls with unsure names wait until every one is answered. Off by default; `CLEANER_HOLD_UNKNOWN=1` also turns it on.
- **Speed.** spaCy reads each call once (the detector reuses that pass), and saving a client, company or answer re-checks only the calls that mention it.
- **Guided tutorial** (the book button, top right) uses one built-in, invented call in its own temporary workspace, with the real cleaning and approval controls, and never touches your calls, identities or export folder. Its sample folders are removed when it ends, or at the next start if the app was closed partway through. While it runs, Settings says so and offers **Leave the tutorial and open sample calls**. **Practice** (Settings) is separate: five made-up calls and clients in `_practice`.
- **Updates** (Settings): **Check for updates** reads the public repo's `app/VERSION` (the app goes online only when it's clicked). **Update now** downloads the release ZIP and swaps in only the app's own files: `.tools`, `.venv`, `themes` and `_practice` are never written, every replaced or removed file is copied to `.update/backup-<time>` first, files are removed only if an older release listed them in `app/FILES.txt` and the new one doesn't, and packages are installed with the app's own uv only when `requirements.lock` changed. **Restart now** opens the new version and closes the old one. A developer copy (a git folder) is never updated this way. `CLEANER_UPDATE_BASE` points the updater at a local folder for tests.
- **Two folders**, side by side in Settings. **Private storage** holds the original transcripts and your client list (the only record of who each code is): only this app reads it, and no AI agent should. The **clean export folder** gets the coded copies: that's the folder agents read. Overlapping locations are refused. The private vault defaults to `~/TranscriptCleaner-Vault`, outside the app folder, so an agent working on this code never sees a call.
- **Fathom** and **Granola** connect in Settings. Pull from either on Calls: choose a window, tick the calls you want, and only those transcripts are downloaded. Keys live in Windows Credential Manager or the macOS Keychain. Granola needs a Business or Enterprise plan. Only the transcript is pulled, never a summary, and files get neutral names.
- **People from your meeting invites**: after a Fathom or Granola pull, invitees who aren't saved yet appear on Calls with a company guessed from their email. **Add many at once** on Clients takes a pasted list or a CSV, with a preview before anything is saved.
- **Before / after** compares the saved original and clean copy. Click an original highlight to correct it for that call, or select original text and tag a missed phrase.
- **Final check** before export: one plain question per leftover. "Is "X" the name of a person or a company?" (**Yes, hide it** / **No, leave it**) for a capitalised phrase that might be a missed name, and "An email address is still showing" (**Hide it** / **Leave it showing**) for contacts and saved names still in the copy. The first word of a sentence, a list item or a heading is never asked about. Codes, weekdays, months and the fine-to-keep list are respected.
- **Put names back**: codes in an agent's answer turn back into real names (first name after a greeting such as "Hi C001"), company names, emails and phone numbers. Stand-ins come back too, even in an answer about several calls. Restored words are highlighted; unknown codes and [PERSON] placeholders are flagged and left as written. Nothing on that page is saved.
- **Export**: new installations require review before automatic export. Export filenames are neutral call IDs; original filenames stay private. Different calls with the same filename are kept separately; an identical re-import is skipped.
- **The app window**: Windows uses the built-in WebView2, Mac uses Apple's WebKit (via pywebview), so the app is its own program: ending it never ends your browser, and browser extensions never see the page. Closing the window stops the app. If a native window isn't possible, it falls back to a separate Chrome window with its own profile, which stops the app when it goes quiet.
- **On a Mac**, setup makes `Transcript Cleaner.app` in the folder: a small launcher plus a relative link to the app's Python inside the package, so macOS names the running app "Transcript Cleaner" (not "Python 3.13") and no Terminal window opens. The Dock and Finder icons follow the logo in Appearance, and the package's name follows the app name there, from the next open.

Detection is a review aid, not a guarantee that every identifying detail will be found. Indirect details are kept. Known gaps: surname-only names, addresses, client web addresses, indirect descriptions ("the CFO at our biggest account"), and a lone first name typed in lowercase that appears nowhere else ("ask dana").

## What's in here

| Where | What it is |
|---|---|
| `Setup Transcript Cleaner (Windows).cmd`, `Setup Transcript Cleaner (Mac).command` | the setup scripts (see [SETUP.md](SETUP.md)) |
| `app/app.py` | the local app server (127.0.0.1 only, per-launch token) and the app window |
| `app/clean.py` | the cleaning engine (client table, Microsoft Presidio, first-name rules, glossary, file-name cleaning) |
| `app/index.html`, `app/tutorial.js` | the app screen and the guided tutorial |
| `app/restore.py`, `app/decisions.py`, `app/updater.py` | Put names back, Undo, and Settings > Updates |
| `app/identities.py`, `app/intake.py`, `app/team.py`, `app/comparison.py` | saving people and companies, invite suggestions and lists, Your team, before/after |
| `app/theme.py`, `app/keystore.py`, `app/fathom.py`, `app/granola.py` | looks, name and logo; API keys in Windows Credential Manager or the macOS Keychain; Fathom and Granola |
| `app/samples/` | the made-up practice calls and clients |
| `app/Open Transcript Cleaner.vbs`, `app/Open Transcript Cleaner (with console).cmd`, `app/Open Transcript Cleaner.command` | launchers; setup's desktop shortcut uses the first (Windows) or `Transcript Cleaner.app` (Mac); the other two show errors |
| `app/setup-windows.ps1` | the Windows setup, run by the .cmd |
| `app/requirements.in`, `app/requirements.lock` | the packages, pinned to exact files by hash |
| `app/VERSION`, `app/FILES.txt` | the release number and the release's file list, read by the updater |

Setup adds these next to `app/`, never inside it: `.tools` and `.venv` (uv, Python and the packages), `setup.log`, and on a Mac `Transcript Cleaner.app`. The app adds `themes` (your look and logo), `_practice` (practice data), short-lived `_tutorial-*` folders, and `.update` (backups from updates). Your calls and clients are in the private vault, `~/TranscriptCleaner-Vault` by default, outside this folder.

The tests, evaluations and the maintainer's publishing tools are kept in the maintainer's own repository; this copy holds only what the app needs.

## Setup, in detail

The setup script is the one supported install path (see [SETUP.md](SETUP.md)). It downloads a pinned uv (checksum-verified) and Python 3.13, then installs `app/requirements.lock` with `--require-hashes`: every package and the name model are pinned to an exact file hash, so a changed or substituted file is refused. Everything lands in this folder (`.tools`, `.venv`), with nothing added to PATH or the registry and no admin rights. Then it makes the desktop shortcut (and, on a Mac, `Transcript Cleaner.app`). Safe to re-run.

**Updating packages:** edit the exact versions in `app/requirements.in`, then regenerate the lock for both systems:
`uv pip compile app/requirements.in --universal --python-version 3.13 --generate-hashes --no-header -o app/requirements.lock`. Check new versions' release notes and security pages before bumping.

### By hand, Windows

```
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r app\requirements.lock
```

About 737 MB in total (the name model is 425 MB of it). Then double-click `app\Open Transcript Cleaner.vbs`.

### By hand, Mac

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r app/requirements.lock
chmod +x 'app/Open Transcript Cleaner.command'
```

Then double-click `app/Open Transcript Cleaner.command`. It runs in Terminal, so the Dock shows Python; the setup script's `Transcript Cleaner.app` is what gives the app its own name and no Terminal window.

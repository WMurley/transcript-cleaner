# Developing Transcript Cleaner

How the app works in detail, how to set it up by hand, and how to run the tests. Using the app is covered in [README.md](README.md) and [SETUP.md](SETUP.md).

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
- **Two folders**, side by side in Settings. **Private storage** holds the original transcripts and your client list (the only record of who each code is): only this app reads it, and no AI agent should. The **clean export folder** gets the coded copies: that's the folder agents read. Overlapping locations are refused. The private vault defaults to `~/TranscriptCleaner-Vault`, outside the app folder, so an agent working on this code never sees a call.
- **Fathom** and **Granola** connect in Settings. Pull from either on Calls: choose a window, tick the calls you want, and only those transcripts are downloaded. Keys live in Windows Credential Manager or the macOS Keychain. Granola needs a Business or Enterprise plan. Only the transcript is pulled, never a summary, and files get neutral names.
- **People from your meeting invites**: after a Fathom or Granola pull, invitees who aren't saved yet appear on Calls with a company guessed from their email. **Add many at once** on Clients takes a pasted list or a CSV, with a preview before anything is saved.
- **Before / after** compares the saved original and clean copy. Click an original highlight to correct it for that call, or select original text and tag a missed phrase.
- **Final check** before export: one plain question per leftover. "Is "X" the name of a person or a company?" (**Yes, hide it** / **No, leave it**) for a capitalised phrase that might be a missed name, and "An email address is still showing" (**Hide it** / **Leave it showing**) for contacts and saved names still in the copy. The first word of a sentence, a list item or a heading is never asked about. Codes, weekdays, months and the fine-to-keep list are respected.
- **Put names back**: codes in an agent's answer turn back into real names (first name after a greeting such as "Hi C001"), company names, emails and phone numbers. Stand-ins come back too, even in an answer about several calls. Restored words are highlighted; unknown codes and [PERSON] placeholders are flagged and left as written. Nothing on that page is saved.
- **Export**: new installations require review before automatic export. Export filenames are neutral call IDs; original filenames stay private. Different calls with the same filename are kept separately; an identical re-import is skipped.
- **The app window**: Windows uses the built-in WebView2, Mac uses Apple's WebKit (via pywebview), so the app is its own program: ending it never ends your browser, and browser extensions never see the page. Closing the window stops the app. If a native window isn't possible, it falls back to a separate Chrome window with its own profile, which stops the app when it goes quiet.
- **On a Mac**, setup makes `Transcript Cleaner.app` in the folder: a small launcher plus a relative link to the app's Python inside the package, so macOS names the running app "Transcript Cleaner" (not "Python 3.13") and no Terminal window opens. The Dock and Finder icons follow the logo in Appearance, and the package's name follows the app name there, from the next open.

Detection is a review aid, not a guarantee that every identifying detail will be found. Indirect details are kept. Independent, hand-written evaluation: [10-03-2026 results and remaining gaps](docs/Independent-Evaluation-10-03-2026.html).

## What's in here

| File | What it is |
|---|---|
| `clean.py` | the cleaning engine (client table, Microsoft Presidio, first-name rules, glossary, file-name cleaning) |
| `app.py` | the local app server (127.0.0.1 only, per-launch token) and the app window |
| `index.html` | the app screen (Calls, Review names, Put names back, Recent decisions, Clients, Companies, Appearance, Settings) |
| `tutorial.js` | the guided tutorial, checkpoints and tab navigation |
| `restore.py` | Put names back |
| `decisions.py` | Undo: logs each one-click answer with the exact change it made |
| `identities.py`, `intake.py`, `team.py` | saving people and companies, invite suggestions and lists, Your team |
| `theme.py` | design.md themes, name and logo, app settings |
| `fathom.py`, `granola.py` | pulling calls from Fathom's and Granola's APIs |
| `keystore.py` | API keys in Windows Credential Manager or the macOS Keychain |
| `Setup Transcript Cleaner (Windows).cmd`, `setup/setup-windows.ps1`, `Setup Transcript Cleaner (Mac).command` | the setup scripts |
| `Open Transcript Cleaner.vbs` | the Windows launcher (no console window); `(with console).cmd` shows errors |
| `Open Transcript Cleaner.command` | the Mac launcher that shows errors in Terminal |
| `samples/` | made-up practice calls and clients for practice mode |
| `test_*.py`, `*_test.py`, `test_*.mjs`, `*_test.mjs`, `smoke_app.py`, `eval_*.py`, `audit.mjs` | tests (synthetic data only) |

## Setup, in detail

The setup script is the one supported install path (see [SETUP.md](SETUP.md)). It downloads a pinned uv (checksum-verified) and Python 3.13, then installs `requirements.lock` with `--require-hashes`: every package and the name model are pinned to an exact file hash, so a changed or substituted file is refused. Everything lands in this folder (`.tools`, `.venv`), with nothing added to PATH or the registry and no admin rights. Then it makes the desktop shortcut (and, on a Mac, `Transcript Cleaner.app`). Safe to re-run.

**Updating packages:** edit the exact versions in `requirements.in`, then regenerate the lock for both systems and commit both files:
`uv pip compile requirements.in --universal --python-version 3.13 --generate-hashes --no-header -o requirements.lock`. Check new versions' release notes and security pages before bumping.

### By hand, Windows

```
python -m venv .venv
.venv\Scripts\python -m pip install --require-hashes -r requirements.lock
```

About 737 MB in total (the name model is 425 MB of it). Then double-click `Open Transcript Cleaner.vbs`.

### By hand, Mac

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
chmod +x 'Open Transcript Cleaner.command'
```

Then double-click `Open Transcript Cleaner.command`. It runs in Terminal, so the Dock shows Python; the setup script's `Transcript Cleaner.app` is what gives the app its own name and no Terminal window.

## Tests

```
.venv\Scripts\python test_flow.py          # cleaning engine
.venv\Scripts\python test_review_names.py  # safe by default: stand-ins (one per name), speakers, tools, strict mode, targeted re-check
.venv\Scripts\python test_short_forms.py   # a bare "Bluefern" follows an unsure "Bluefern Bakery" instead of becoming a person
.venv\Scripts\python test_team.py          # Your team: visible everywhere, list round trip, clients refused
.venv\Scripts\python smoke_app.py          # app server
.venv\Scripts\python fathom_test.py        # Fathom against a stand-in server (writes a test key to the real keystore)
.venv\Scripts\python granola_test.py       # Granola against a stand-in server (writes a test key to the real keystore)
.venv\Scripts\python test_theme.py         # design.md reader: pale accents, fonts, layers
.venv\Scripts\python test_restore.py       # codes back to names: greetings, possessives, contacts, unknown codes
.venv\Scripts\python test_intake.py        # pasted lists, CSV exports, company guesses, invite suggestions
.venv\Scripts\python test_final_check.py   # final check: leftovers flagged; codes, ordinary words and list-item starts not
.venv\Scripts\python test_window.py        # app window: closing stops the app, a reload or a quiet window doesn't
.venv\Scripts\python test_undo.py          # Undo reverses each answer exactly; follows renamed calls; deleted calls take theirs along
.venv\Scripts\python test_delete_call.py   # delete and rename leave nothing behind (moves test files to the real Trash on a Mac)
.venv\Scripts\python test_tutorial_cleanup.py  # the tutorial's sample folders go when it ends, or at the next start
.venv\Scripts\python test_hardening.py     # integrity and privacy regressions
.venv\Scripts\python test_adversarial.py   # matching, contacts, structured labels and correction regressions
.venv\Scripts\python test_review_workflow.py # saved-copy comparison and batch validation
.venv\Scripts\python eval_client_calls.py 20 1   # synthetic client-call evaluation (leaks, unlisted names, noise)
.venv\Scripts\python eval_approval.py 1    # full approval cycle, nonzero exit on leaks/held calls (also 2 and 3)
.venv\Scripts\python eval_adversarial.py --report-only # 24 hand-written cases; measures known limitations
node test_identity_ui.mjs                  # tagging, drafts, destinations, export approval
node test_review_ui.mjs                    # before/after, corrections and grouped scopes
node test_review_progress_ui.mjs           # Review names: grouped by call, progress bar, folds stay open, Calls pill
node test_undo_ui.mjs                      # the Undo pop-up and Recent decisions
node test_final_check_ui.mjs               # final check: one plain question per item
node test_tutorial_ui.mjs                  # tutorial, workspace isolation, export and resume
node test_tutorial_practice_ui.mjs         # Settings during the tutorial; one click to practice
node test_team_ui.mjs                      # On my team, Settings card, copy, paste with preview, remove
node test_restore_ui.mjs                   # Put names back: live restore, copy, nothing kept
node test_intake_ui.mjs                    # Add many at once: preview, save, waiting calls clean themselves
node audit.mjs                             # 450-screen layout audit: three looks, light and dark, five widths
```

For browser tests, run `npm install` then `npx playwright-core install --only-shell chromium`. Without that, set `CLEANER_BROWSER_HELPER` (or put its path in a git-ignored `.browser-helper` file) to a module exporting `chromium` and `EXE`. Set `CLEANER_PYTHON` to override the test Python executable.

Most suites pin strict mode (`CLEANER_HOLD_UNKNOWN=1`) because they test the answer-every-name workflows; `test_review_names.py` covers the default. All fixtures are invented. `eval_adversarial.py` still demonstrates limitations with surname-only names, addresses, client URLs and indirect identifying descriptions, and a lone first name typed in lowercase that was never seen elsewhere ("ask dana") is not caught.

## Notes

- A GLiNER detector trial (10-10-2026) was measured and not adopted: see [docs/GLiNER-Trial-10-10-2026.md](docs/GLiNER-Trial-10-10-2026.md).
- Test design.md files (`test-fixtures/clay-design.md`, `test-fixtures/pale-accent-design.md`) are invented.

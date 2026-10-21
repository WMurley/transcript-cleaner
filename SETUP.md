# Set up Transcript Cleaner

One setup script does everything. Run it yourself with a double-click, or have your AI agent run it: either way you get the same checked install. It downloads about 800 MB once, into the Transcript Cleaner folder only, and takes 5 to 15 minutes. Apart from a shortcut on your desktop, it doesn't change anything else on your computer, and setup itself doesn't need an admin password (a Mac may ask for your password once, to allow the downloaded script). To remove it later, delete the folder and the shortcut.

Transcript Cleaner must run on the computer where your call transcripts are, usually your laptop. An agent that runs on a server (a VPS) can't set it up for you: use one on the same computer, such as Claude Code or Codex, or the double-click.

## With your agent

Open your agent in the Transcript Cleaner folder and paste this:

```
Set up Transcript Cleaner in this folder by running its setup script, then confirm it worked.
On Windows run: powershell -NoProfile -ExecutionPolicy Bypass -File app\setup-windows.ps1
On a Mac run: bash "Setup Transcript Cleaner (Mac).command"
If it stops, read setup.log, fix the cause, and run the script again until it reports All set.
Rules: install only through the setup script, which keeps everything inside this folder and checks
every download; never install packages any other way, system-wide, or with admin rights; don't
change requirements.lock; don't open, read or move anything in my TranscriptCleaner-Vault folder or
any transcript.
```

## With a double-click

### Windows

1. In your Downloads folder, right-click the ZIP and choose **Extract All**, then **Extract**. (Double-clicking a ZIP only looks inside it, and setup can't run from there.) Move the extracted folder somewhere you'll keep it, for example your Documents folder. Not inside OneDrive or Dropbox.
2. Double-click **Setup Transcript Cleaner (Windows)**.
3. If Windows says **Windows protected your PC**, click **More info**, then **Run anyway**. If it says **The publisher could not be verified**, click **Run**. Windows shows these for any script downloaded from the internet.
4. Wait for **All set**. When it asks **Open it now?**, press Enter. From then on, open Transcript Cleaner from the new shortcut on your desktop.

### Mac

1. Your Mac usually unzips the download for you (if you only see a ZIP, double-click it). Move the folder somewhere you'll keep it, for example your Documents folder. Not inside iCloud Drive or Dropbox.
2. Double-click **Setup Transcript Cleaner (Mac)**. The first time, a message says it was **Not Opened** because "Apple could not verify" it is free of malware. Apple shows this for any script downloaded from the internet. Click **Done**. Don't click **Move to Trash**.
3. Open **System Settings**, click **Privacy & Security**, and scroll down to **Security**. You'll see "Setup Tran…command was blocked to protect your Mac." Click **Open Anyway** next to it.
4. A second message asks **Open "Setup Transcript Cleaner (Mac).command"?** The big blue button is **Move to Trash**: don't click it. Click **Open Anyway**, the grey button under it. If your Mac asks for your password or Touch ID, give it.
5. Wait for **All set**. Open Transcript Cleaner from the new shortcut on your desktop. It opens as its own app, with its own name in the Dock and no Terminal window. Close the app's window to quit it.

On macOS 14 or older, steps 2 to 4 are shorter: right-click the file, choose **Open**, then **Open** again. The agent route above skips steps 2 to 4 entirely, because your agent runs the script for you.

## Updating to a new version

**In the app (version 1.1 and later):** go to **Settings**, find **Updates**, and click **Check for updates**. If there's a new version, click **Update now**, then **Restart now**. Only the app's own files change: Python and its packages, your calls, clients, settings, look and practice data all stay as they are, and every file it replaces is backed up in the `.update` folder first. If an update needs new packages, it installs them itself, or tells you to run setup once more.

**Version 1.0, or a fresh copy:** use one of the ways below. Your calls, clients and settings live in the TranscriptCleaner-Vault folder in your home folder (or wherever you moved it in Settings, under Private storage), not in the Transcript Cleaner folder. Updating replaces the app folder and never touches them.

### With your agent

Open your agent in the folder that holds Transcript Cleaner (for example your Documents folder) and paste this, with the link filled in:

```
Update my Transcript Cleaner to the newest version. Its folder is here, named Transcript Cleaner (or similar).
The newest version is on this GitHub page: PASTE THE LINK HERE
1. If Transcript Cleaner is open, ask me to close its window first, and wait.
2. Rename the Transcript Cleaner folder by adding "-old" to the end of its name.
3. Download the newest version from that page (the ZIP is the page link plus /archive/refs/heads/main.zip), unzip it here, and give the new folder the old folder's original name.
4. In the new folder, run its setup script. On Windows: powershell -NoProfile -ExecutionPolicy Bypass -File app\setup-windows.ps1. On a Mac: bash "Setup Transcript Cleaner (Mac).command". If it stops, read setup.log, fix the cause and run it again until it reports All set.
5. Open Transcript Cleaner from the desktop shortcut and check that it starts and shows my calls.
6. Move the -old folder to the Trash or Recycle Bin.
Rules: never open, read, move or delete my TranscriptCleaner-Vault folder or any transcript; install only through the setup script; don't change requirements.lock.
```

### By hand

1. Close the Transcript Cleaner window.
2. Rename the old Transcript Cleaner folder, for example by adding "old" to the end of its name.
3. Download the new version (green **Code** button, then **Download ZIP**), unzip it, and put the new folder where the old one was.
4. Run setup in the new folder, the same way as the first time. Windows and Apple show their warning again, because it's a new download.
5. Open Transcript Cleaner from the desktop shortcut and check your calls are there. Then move the old folder to the Trash or Recycle Bin.

## If setup stops

Run it again: it picks up where it stopped. If it keeps stopping, use the agent prompt above: it reads setup.log, fixes the cause and runs the script again. setup.log has no transcripts or client details in it, so it's safe to share.

## What gets installed, and from where

| What | Size | From |
|---|---|---|
| uv 0.12.23, the tool that fetches Python | about 20 MB | github.com/astral-sh/uv (checked against its published checksum) |
| Python 3.13, for this app only | about 60 MB | Astral's Python builds, fetched by uv |
| Microsoft Presidio and spaCy, the cleaning packages | about 300 MB | PyPI, the standard Python package index |
| pywebview, the app's own window (uses Windows' WebView2 or Apple's WebKit) | a few MB | PyPI |
| The English name model | about 400 MB | github.com/explosion/spacy-models |

Every package and the name model are pinned in `app/requirements.lock` to an exact version and the fingerprint (hash) of the exact file that was checked. Setup refuses any file that doesn't match, so a changed or substituted download can't be installed. All of it lands in the `.tools` and `.venv` folders inside Transcript Cleaner. Nothing is added to your PATH or the Windows registry. After setup, the app runs entirely on your computer: the only time it goes online is when you choose to pull calls from Fathom or Granola.

# Transcript Cleaner

Transcript Cleaner takes the transcript of a client call and hides the names, companies, emails and phone numbers in it, on your own computer, before any AI sees it. Your AI agents get a clean copy with codes like C001 instead of names. When an agent writes you something back, Transcript Cleaner can put the real names back in so you can send it.

It's made for client calls: one-to-one, or a handful of people. It isn't designed for large group sessions.

## Is it safe?

- **It runs only on your computer.** The cleaning happens on this machine, with no AI model involved. The app goes online only during setup, when you choose to pull calls from Fathom or Granola, and when you click Check for updates.
- **Your originals stay private.** The original transcripts and your client list are kept in a private folder that only this app reads. Your agents read a separate folder that holds only the clean copies.
- **It's a safety net, not a guarantee.** It catches most names, but no tool catches everything. Read a clean copy before you share it. The app's final check points out anything that still looks like a name.

## What you need

- A Windows 10 or 11 computer, or a Mac.
- About 1.5 GB of free space, and an internet connection for setup.
- Set it up on the computer where your call transcripts are, usually your laptop, not on a server.

## Get started

It takes about 15 minutes, once. Follow the steps for your computer, one at a time.

### On Windows

1. On this page, click the green **Code** button, then **Download ZIP**.
2. Open your **Downloads** folder. Right-click the ZIP file (named something like **transcript-cleaner-main**) and choose **Extract All**, then click **Extract**. Don't run anything from inside the ZIP itself.
3. Move the new **transcript-cleaner-main** folder into your **Documents** folder. Not into OneDrive or Dropbox.
4. Open that folder and double-click **Setup Transcript Cleaner (Windows)**.
5. If Windows says **Windows protected your PC**, click **More info**, then **Run anyway**. If it says **The publisher could not be verified**, click **Run**.
6. A black window shows setup working. Wait for **All set** (5 to 15 minutes). When it asks **Open it now?**, press Enter.
7. From now on, open it with the **Transcript Cleaner** shortcut on your desktop. Close its window to quit.

### On a Mac

1. On this page, click the green **Code** button, then **Download ZIP**.
2. Open your **Downloads** folder. Your Mac usually unzips it for you into a folder named something like **transcript-cleaner-main**. If you only see a ZIP file, double-click it.
3. Move the **transcript-cleaner-main** folder into your **Documents** folder. Not into iCloud Drive or Dropbox.
4. Open that folder and double-click **Setup Transcript Cleaner (Mac)**. Your Mac says it was **Not Opened**. Click **Done**. Don't click Move to Trash.
5. Open **System Settings**, click **Privacy & Security**, and scroll down to **Security**. Next to the message about Setup Transcript Cleaner, click **Open Anyway**.
6. A second message asks if you want to open it. The big blue button is **Move to Trash**: don't click it. Click **Open Anyway**, the grey button under it. Enter your Mac password if asked.
7. A Terminal window shows setup working. Wait for **All set** (5 to 15 minutes). When it asks **Open it now?**, press Return.
8. From now on, open it with the **Transcript Cleaner** shortcut on your desktop. Close its window to quit.

Windows and Apple show these warnings for any script downloaded from the internet. They don't mean anything is wrong.

### Or let your AI agent do it

If you use Claude Code, Codex or a similar agent on this computer, do steps 1 to 3 above, then open your agent in the **transcript-cleaner-main** folder and paste the setup prompt from [SETUP.md](SETUP.md). It runs setup for you, with no warnings to click through.

## Your first 10 minutes

1. **Take the guided tour.** Click **Guided tutorial** (top right). It walks you through one made-up call, step by step. Click **Exit tutorial** in the yellow bar when you're done.
2. **Try the practice calls.** Go to **Settings**, find **Practice**, and click **Try sample calls**. You get five made-up calls to explore. Nothing here is real. Click **Leave practice** when you're ready for your own calls.
3. **Tell it your name.** On **Review names**, type your name once, so it stays visible in all your calls.
4. **Add a real call.** On **Calls**, click **Choose files** or **Paste a transcript**, or connect Fathom or Granola in Settings and pull calls from there. The call is cleaned straight away.
5. **Review the names.** **Review names** lists the names the cleaner wasn't sure about, grouped by call. They're already hidden. For each one, choose **Save as a client** (it gets a lasting code), **Fine to show**, or **Keep hidden**. Clicked the wrong thing? Every answer has an **Undo**, and **Recent decisions** in the sidebar lists them all.
6. **Choose where clean copies go.** On **Calls**, click **Choose export folder** and pick the folder your AI agents read. Open a call, read the clean copy, then click **Approve clean copy and export**.
7. **Put names back.** When your agent writes something using the codes, paste it into **Put names back**. The real names come back, ready to send.

## What the codes mean

| Code | Means |
|---|---|
| C001, C002... | a person you saved as a client |
| O001, O002... | a company you saved |
| C001-EMAIL, C001-PHONE | that client's email or phone number |
| EMAIL-1, PHONE-1 | an email or phone number that isn't saved to anyone |
| PERSON-1, COMPANY-1 | a name the cleaner wasn't sure about, hidden until you review it |

A code always means the same name in every call. The **Put names back** page has a short note to paste into your agent, so it keeps the codes exactly as written.

## Updating

In the app, go to **Settings**, find **Updates**, and click **Check for updates**. If there's a new version, click **Update now**, then **Restart now**. No new download, no setup and no warnings to click through. Your calls, clients and settings stay exactly as they are.

Version 1.0 doesn't have the Updates card yet, so update it once by hand: [SETUP.md](SETUP.md) has the steps and a prompt your agent can follow.

## If something goes wrong

- **Setup stopped?** Run it again: it picks up where it stopped. If it keeps stopping, give the **setup.log** file in the Transcript Cleaner folder to your AI agent. It never contains transcripts or client details, so it's safe to share.
- **The app won't open?** Open the **app** folder inside Transcript Cleaner and double-click **Open Transcript Cleaner (with console)** on Windows, or **Open Transcript Cleaner.command** on a Mac. Those show error messages you can give your agent.

## License and credits

MIT. See [LICENSE](LICENSE). Use it, change it and share it. Keep the copyright notice with any copy. The license comes with no warranty.

Transcript Cleaner is built on these open-source projects. Setup downloads them, each with its own license file:

| Project | Used for | License |
|---|---|---|
| [Microsoft Presidio](https://github.com/microsoft/presidio) | finding emails, phone numbers and other personal details | MIT |
| [spaCy](https://github.com/explosion/spaCy) and its `en_core_web_lg` English model | finding names of people and companies | MIT |
| [pywebview](https://github.com/r0x0r/pywebview) | the app window | BSD-3-Clause |
| [pythonnet](https://github.com/pythonnet/pythonnet) (Windows only) | connects the app window to Windows | MIT |
| [PyObjC](https://github.com/ronaldoussoren/pyobjc) (Mac only) | connects the app window to the Mac | MIT |
| [uv](https://github.com/astral-sh/uv) | the one-click setup | MIT or Apache-2.0 |

Their own dependencies (listed in `app/requirements.lock`) are under permissive licenses too: MIT, BSD, Apache-2.0, ISC, PSF and MPL-2.0.

The app's icons are drawn from [Feather](https://github.com/feathericons/feather) (MIT) and [Lucide](https://github.com/lucide-icons/lucide) (ISC). Their license notices are in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

Transcript Cleaner is an independent project. Microsoft, Explosion and the other projects above have not reviewed or endorsed it.

For developers: how it works in detail, setting it up by hand, and the tests are in [DEVELOPING.md](DEVELOPING.md).

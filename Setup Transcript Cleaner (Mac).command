#!/bin/bash
# Transcript Cleaner setup for a Mac. Double-click it (the first time: right-click, then Open).
#
# Everything goes inside this folder: a private copy of uv (the tool that fetches Python), its own Python,
# the app's packages and the name model. Nothing is added to your PATH, no admin password is needed, and
# deleting this folder removes all of it. About 800 MB is downloaded, once. Safe to run again.

UV_VERSION="0.12.23"   # pinned: a settled release, not the newest
PYTHON_VERSION="3.13"

APP="$(cd -- "$(dirname -- "$0")" && pwd)" || exit 1
TOOLS="$APP/.tools"
LOG="$APP/setup.log"
PY="$APP/.venv/bin/python"
LOCK="$APP/requirements.lock"   # every package, the name model included, pinned to a checked file hash
STEP="starting"

# uv keeps everything it fetches inside .tools and never touches PATH
export UV_PYTHON_INSTALL_DIR="$TOOLS/python" UV_CACHE_DIR="$TOOLS/cache" UV_PYTHON_BIN_DIR="$TOOLS/bin"
export UV_PYTHON_INSTALL_BIN=0 UV_MANAGED_PYTHON=1

say() { printf '%s\n' "$1"; printf '%s  %s\n' "$(date '+%Y-%m-%dT%H:%M:%S')" "$1" >> "$LOG"; }
run() { printf '> %s\n' "$*" >> "$LOG"; "$@" 2>&1 | tee -a "$LOG"; return "${PIPESTATUS[0]}"; }
stop() {
  say "Setup stopped while $STEP."
  printf '\n  Setup didn'"'"'t finish (it stopped while %s).\n' "$STEP"
  printf '  Nothing outside this folder was changed. Running setup again picks up where it stopped.\n'
  printf '  If it keeps stopping, give setup.log (in this folder) to your AI agent or whoever shared this app with you.\n'
  printf '  It has no transcripts or client details in it.\n\n'
  read -r -p '  Press Return to close. ' _
  exit 1
}

printf 'Transcript Cleaner setup log (no transcripts or client details are ever written here)\n' > "$LOG"
printf '\n  Transcript Cleaner setup\n'
printf '  Downloads about 800 MB once, into this folder only. It takes 5 to 15 minutes.\n'
printf '  Apart from a shortcut on your desktop, nothing else on this Mac is changed, and no admin password is needed.\n\n'

STEP="getting uv"
UV="$TOOLS/uv"
if [ ! -x "$UV" ]; then
  case "$(uname -m)" in
    arm64) ASSET="uv-aarch64-apple-darwin.tar.gz" ;;
    x86_64) ASSET="uv-x86_64-apple-darwin.tar.gz" ;;
    *) say "This Mac's processor ($(uname -m)) isn't supported."; stop ;;
  esac
  BASE="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
  mkdir -p "$TOOLS" || stop
  say "1 of 4  Downloading uv $UV_VERSION (about 20 MB)..."
  curl -fsSL "$BASE/$ASSET" -o "$TOOLS/$ASSET" || stop
  EXPECTED="$(curl -fsSL "$BASE/$ASSET.sha256" | awk '{print tolower($1)}')" || stop
  ACTUAL="$(shasum -a 256 "$TOOLS/$ASSET" | awk '{print tolower($1)}')"
  if [ -z "$EXPECTED" ] || [ "$EXPECTED" != "$ACTUAL" ]; then
    rm -f "$TOOLS/$ASSET"; say "The uv download didn't match its published checksum, so it was deleted."; stop
  fi
  tar -xzf "$TOOLS/$ASSET" -C "$TOOLS" || stop
  rm -f "$TOOLS/$ASSET"
  FOUND="$(find "$TOOLS" -type f -name uv -perm -u+x | head -n 1)"
  [ "$FOUND" != "$UV" ] && mv -f "$FOUND" "$UV"
else
  say "1 of 4  uv is already here."
fi

STEP="setting up Python"
if [ -x "$PY" ] && "$PY" -c "import presidio_analyzer, spacy, webview; spacy.load('en_core_web_lg')" >/dev/null 2>&1; then
  say "2 and 3 of 4  Python and the checked packages are already installed."
else
  if [ ! -x "$PY" ]; then
    say "2 of 4  Getting Python $PYTHON_VERSION for this app..."
    run "$UV" venv "$APP/.venv" --python "$PYTHON_VERSION" || stop
  else
    say "2 of 4  Python is already here."
  fi
  STEP="installing packages"
  say "3 of 4  Installing the checked packages, including the 400 MB name model (the slow part)..."
  # --require-hashes: any file that doesn't match the hash in requirements.lock is refused
  run "$UV" pip install --python "$PY" --require-hashes -r "$LOCK" || stop
fi

STEP="checking the install"
say "4 of 4  Checking everything works..."
run "$PY" -c "import presidio_analyzer, spacy, webview; spacy.load('en_core_web_lg'); print('Name model and app window load.')" || stop
chmod +x "$APP/Open Transcript Cleaner.command"

# A small Mac app around the app's own Python, so the Dock shows "Transcript Cleaner", not "Python 3.13":
# macOS names a running app after the package its program sits in. Links are relative, so renaming or moving
# the whole folder keeps it working. (Open Transcript Cleaner.command stays: it shows errors in Terminal.)
STEP="making the Mac app"
BUNDLE="$APP/Transcript Cleaner.app"
rm -rf "$BUNDLE"
mkdir -p "$BUNDLE/Contents/MacOS" || stop
cat > "$BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Transcript Cleaner</string>
  <key>CFBundleDisplayName</key><string>Transcript Cleaner</string>
  <key>CFBundleIdentifier</key><string>local.transcriptcleaner</string>
  <key>CFBundleExecutable</key><string>Transcript Cleaner</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST
cat > "$BUNDLE/Contents/MacOS/Transcript Cleaner" <<'LAUNCH'
#!/bin/bash
# Opens Transcript Cleaner as its own Mac app. app-python is a link to the app's Python, kept inside this package.
CONTENTS="$(cd -- "$(dirname -- "$0")/.." && pwd)"
APP="$(cd -- "$CONTENTS/../.." && pwd)"
cd -- "$APP" || exit 1
if [ ! -x "$CONTENTS/MacOS/app-python" ]; then
  osascript -e 'display dialog "Set up Transcript Cleaner first: double-click Setup Transcript Cleaner (Mac) in its folder." buttons {"OK"} default button 1' >/dev/null 2>&1
  exit 1
fi
case "${1:-}" in ""|--*) set -- "$APP/app.py" "$@" ;; esac   # a double-click (or app options) opens the app
exec "$CONTENTS/MacOS/app-python" "$@"
LAUNCH
chmod +x "$BUNDLE/Contents/MacOS/Transcript Cleaner"
ln -s "../../../.venv/bin/python" "$BUNDLE/Contents/MacOS/app-python" || stop
cp "$APP/.venv/pyvenv.cfg" "$BUNDLE/Contents/pyvenv.cfg" || stop   # Python finds the app's packages through these two
ln -s "../../.venv/lib" "$BUNDLE/Contents/lib" || stop
# its logo in Finder and on the desktop shortcut (the app keeps it matching Appearance after this)
"$PY" -c 'import sys; sys.path.insert(0, sys.argv[1]); import app; app.mac_finder_icon()' "$APP" >/dev/null 2>&1

# files unzipped from a download are marked as from the internet; clear that on this folder so the app opens
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
ln -sfn "$BUNDLE" "$HOME/Desktop/Transcript Cleaner" && say "Desktop shortcut: added Transcript Cleaner to your desktop."

printf '\n  All set. Open Transcript Cleaner from the shortcut on your desktop.\n\n'
read -r -p '  Open it now? (Y/n) ' OPEN
case "$OPEN" in [nN]*) ;; *) open "$BUNDLE" ;; esac
exit 0

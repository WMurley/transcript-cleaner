#!/bin/bash
# macOS launcher. Setup is described in README.md.
cd -- "$(dirname -- "$0")" || exit 1
if [ ! -x ../.venv/bin/python ]; then
  printf 'Set up Transcript Cleaner first. Follow the macOS setup in README.md.\n'
  read -r -p 'Press Return to close. ' reply
  exit 1
fi
../.venv/bin/python app.py
status=$?
if [ "$status" -ne 0 ]; then
  printf 'Transcript Cleaner stopped with an error. See the message above.\n'
  read -r -p 'Press Return to close. ' reply
fi
exit "$status"

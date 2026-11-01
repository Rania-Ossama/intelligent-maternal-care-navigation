#!/usr/bin/env bash
# macOS / Linux launcher
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt || exit 1
else
  source .venv/bin/activate
fi
python run.py "$@"

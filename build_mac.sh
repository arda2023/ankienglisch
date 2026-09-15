#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Fehler: Dieses Skript kann nur unter macOS ausgeführt werden."
    exit 1
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

if ! python -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) and getattr(tkinter, "TkVersion", 0) >= 8.6 else 1)' 2>/dev/null; then
    echo "Bitte Python 3.13 von python.org installieren (nicht das System-Python von Apple)."
    exit 1
fi

rm -rf build dist

pyinstaller --noconfirm --windowed --onedir --name AnkiEnglishManager --osx-bundle-identifier local.ankienglishmanager --collect-data customtkinter main.py

echo ""
echo "Fertig! Die App befindet sich hier:"
echo "$(pwd)/dist/AnkiEnglishManager.app"

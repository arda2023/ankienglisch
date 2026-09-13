@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
pip install -r requirements.txt

pyinstaller ^
  --onefile ^
  --windowed ^
  --name AnkiEnglishManager ^
  --add-data "config.py;." ^
  --add-data "import_cards.py;." ^
  --add-data "export_cards.py;." ^
  --add-data "sync_cards.py;." ^
  main.py

pause

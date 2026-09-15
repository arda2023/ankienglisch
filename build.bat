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
  main.py

pause

# Anki English Manager

Simple Windows-11-Desktop-App mit CustomTkinter für die vorhandenen Skripte:

- `import_cards.py`
- `export_cards.py`
- `sync_cards.py`
- `config.py`

Die GUI ändert die Logik dieser Skripte nicht. Sie ruft nur deren Funktionen auf und zeigt Ausgaben im Statusfenster an.

## Voraussetzungen

- Windows 11
- Python 3.10 oder neuer
- Anki muss laufen
- AnkiConnect muss installiert und erreichbar sein

## Installation

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Start

```bat
python main.py
```

## Funktionen

- Import aus Zwischenablage
- Export nach `cards.json`
- Export & JSON in Zwischenablage kopieren
- Synchronisieren
- `cards.json` öffnen
- Projektordner öffnen

## EXE bauen

```bat
build.bat
```

Die fertige EXE liegt danach im Ordner `dist`.

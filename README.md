# Anki English Manager

Windows-11-Desktop-App (CustomTkinter + PyInstaller) zum Verwalten von Anki-Vokabelkarten über AnkiConnect.

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

## EXE bauen

```bat
build.bat
```

Die fertige EXE liegt danach im Ordner `dist`.

---

## Konfiguration — config.json

`config.json` liegt im selben Ordner wie die EXE (bzw. das Skript). Fehlende
Schlüssel werden beim Start automatisch mit Standardwerten ergänzt. Wenn die
Datei fehlt, wird sie neu erstellt.

| Schlüssel | Typ | Standardwert | Bedeutung |
|---|---|---|---|
| `deck_name` | string | `"Englisch"` | Name des Anki-Decks. Nur Notizen **genau** in diesem Deck werden gelesen oder verändert — Unter-Decks werden ignoriert. |
| `model_name` | string | `"English Active Speaking"` | Name des Note-Types (Kartenvorlage). Nur Notizen dieses Typs werden berücksichtigt. |
| `anki_connect_url` | string | `"http://localhost:8765"` | URL des AnkiConnect-Plugins. |
| `expected_profile` | string \| null | `null` | Wenn gesetzt, prüft die App beim Start, ob das angegebene Anki-Profil aktiv ist. `null` deaktiviert diese Prüfung. |
| `max_auto_delete` | integer | `3` | Maximale Anzahl von Notizen, die der Sync automatisch aus Anki löschen darf (Schutz gegen versehentliches Massenlöschen). |

> **Hinweis:** Decks und Note-Types werden von der App **niemals** automatisch erstellt.
> Bitte vor dem ersten Einsatz beides manuell in Anki anlegen.

---

## Dateien und Ordner

### cards.json

Lokale Kopie aller Karten im konfigurierten Deck. Dient als Grundlage für
den Sync. Der **Import** ergänzt neu importierte Karten in dieser Datei
(Anhängen, kein Überschreiben des Bestehenden). Der **Export** ersetzt den
gesamten Inhalt mit dem aktuellen Stand aus Anki.

### backups/

Nach jedem Schreibzugriff auf `cards.json` wird automatisch eine
Sicherungskopie in diesem Unterordner angelegt
(Format: `cards_YYYYMMDD_HHMMSS_ffffff.json`). Es werden maximal 20 Backups
behalten; ältere werden gelöscht. Der Ordner wird von Git ignoriert.

---

## Funktionen

| Schaltfläche | Beschreibung |
|---|---|
| **Import aus Zwischenablage** | Liest ein JSON-Array aus der Zwischenablage, validiert die Karten, überspringt Duplikate und legt neue Notizen in Anki an. Importierte Karten werden an `cards.json` angehängt. |
| **Export nach cards.json** | Liest alle Notizen des konfigurierten Note-Types aus **genau** dem konfigurierten Deck (keine Unter-Decks) und schreibt sie in `cards.json`. |
| **Export & JSON in Zwischenablage kopieren** | Wie Export, kopiert `cards.json` danach zusätzlich in die Zwischenablage. |
| **Synchronisieren** | Gleicht `cards.json` mit Anki ab. |
| **cards.json öffnen** | Öffnet `cards.json` mit dem Standard-Editor. |
| **Projektordner öffnen** | Öffnet den Projektordner im Explorer. |

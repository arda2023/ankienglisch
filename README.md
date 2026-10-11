# Anki English Manager

Windows/macOS-Desktop-App (CustomTkinter + PyInstaller) zum Verwalten von Anki-Vokabelkarten über AnkiConnect.

## Voraussetzungen

- Windows 11 oder macOS
- Python 3.10+ (Windows) oder Python 3.13 von python.org (macOS)
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

## EXE / App bauen

**Windows:**
```bat
build.bat
```
Die fertige EXE liegt danach im Ordner `dist`.

**macOS:**
```bash
chmod +x build_mac.sh
./build_mac.sh
```
Die fertige App liegt in `dist/AnkiEnglishManager.app`.

> **macOS App Nap & Gatekeeper:**
> Damit AnkiConnect im Hintergrund antwortet, App Nap für Anki deaktivieren:
> `defaults write net.ankiweb.dtop NSAppSleepDisabled -bool true`
> 
> Eine heruntergeladene oder kopierte `.app` muss unter macOS ggf. einmalig in den **Systemeinstellungen → Datenschutz & Sicherheit** mit „Dennoch öffnen“ autorisiert werden.

---

## Konfiguration — config.json

`config.json` und `cards.json` liegen im Datenordner:
- **Windows:** Im selben Ordner wie die EXE (bzw. das Skript).
- **macOS:** `~/Library/Application Support/AnkiEnglishManager`

Fehlende Schlüssel in der Konfiguration werden beim Start automatisch mit Standardwerten ergänzt. Wenn die Datei fehlt, wird sie neu erstellt.

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
| **Datenordner öffnen** | Öffnet den Datenordner (mit config.json, cards.json und backups) im Datei-Explorer/Finder. |

## Kartenlayout für Chunks und Patterns

**Kartenlayout einrichten** erweitert den bestehenden Notiztyp „English Active
Speaking“ um sechs optionale Felder und ersetzt seine einzelne Kartenvorlage
sowie das CSS. Der Notiztyp gilt sammlungsweit, auch außerhalb des konfigurierten
Decks. Notizen und bestehender Lernfortschritt werden bei der Einrichtung nicht
zurückgesetzt. Mehrere Kartenvorlagen führen zum Abbruch.

Vor jeder Einrichtung wird im Datenordner unter `backups/` eine Sicherung
`notetype_backup_YYYYMMDD_HHMMSS.json` mit Feldnamen, Vorlagen und CSS angelegt.
Diese Sicherungen werden nicht automatisch gelöscht. Bei einem Fehler können
bereits Teiländerungen erfolgt sein; die Statusmeldung nennt die Sicherung.

### Erstmalige Einrichtung und vollständiger Abgleich

1. **Zuerst alle Geräte synchronisieren**, insbesondere iPhone und andere PCs.
   Nicht synchronisierte Wiederholungen auf anderen Geräten können sonst verloren gehen.
2. Auf **einem Gerät** Anki öffnen und in der App **Kartenlayout einrichten** klicken.
   Das Hinzufügen fehlender Felder erfordert eine Bestätigung; voreingestellt ist Nein.
3. Danach auf diesem Gerät in **Anki** synchronisieren und **Zu AnkiWeb hochladen** wählen.
4. Anschließend die anderen Geräte synchronisieren und, falls gefragt,
   **Von AnkiWeb herunterladen** wählen.

Der App-Button „Synchronisieren“ gleicht nur die JSON-Datei mit lokalem Anki ab;
er ersetzt den AnkiWeb-Abgleich nicht. Wenn alle neuen Felder bereits vorhanden
sind, benötigt eine erneute reine Layout-Aktualisierung keine Schema-Bestätigung.
Import und Sync benötigen die neuen Felder; Export funktioniert weiterhin mit
alten Notiztypen und warnt bei fehlenden Feldern.

### Felder und Marker

Die bisherigen Felder `CardId`, `German`, `English`, `Alternative1` und
`Alternative2` bleiben erhalten. Die neuen Felder dürfen fehlen oder leer sein:

| Feld | Inhalt |
|---|---|
| `Hint` | Kurzer deutscher Tipp bei mehrdeutigem Ausgangssatz, ohne die Antwort zu verraten. |
| `Trap` | Typischer, vom Deutschen beeinflusster englischer Fehler. |
| `Pattern` | Wiederverwendbares Muster, etwa `[people / someone] + [[who]] + [verb]`. |
| `Transfer1` / `Transfer2` | Ein bis zwei kurze Beispielsätze mit demselben Muster. |
| `Rule` | Ein kurzer deutscher Satz zur Fehlerursache. |

`[[…]]` markiert den Schlüsselteil: in `English`, `Pattern`, `Transfer1` und
`Transfer2` grün, in `Trap` rot. Einzelne `[ ]` bleiben normale Platzhalter.
Die Marker werden unverändert gespeichert und exportiert; erst die Karte
wandelt sie zur Anzeige um. Nicht geschlossene, verschachtelte oder leere Marker
blockieren Import und Sync. Beim Import gibt es unverbindliche Warnungen für
`Hint` über 60 Zeichen, `Rule` über 160 Zeichen oder ein `Pattern` ohne Marker in `English`.

Leere Abschnitte verschwinden. `Transfer2` wird nur mit `Transfer1` angezeigt,
`Alternative2` nur mit `Alternative1`. Das Layout unterstützt helle und dunkle
Darstellung sowie schmale Handybildschirme.

**Datensicherheit beim Sync:** Ein fehlender Feldschlüssel in `cards.json` lässt
den Anki-Wert unverändert. Ein vorhandener Textfeldschlüssel mit `""` leert
gezielt das Feld. Damit löscht eine Datei aus einer älteren App-Version die
neuen Inhalte nicht. Neue Karten benötigen weiterhin `German` und `English`.
Beim Import werden fehlende optionale Felder als leere Zeichenketten angelegt.

"""
cards_file.py — Gemeinsame Lese-/Schreibhilfen für cards.json.

Stellt load_cards(), save_cards() und Normalisierungsfunktionen bereit.
"""

import json
import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

from config import BACKUP_DIR, CARDS_FILE

# ---------------------------------------------------------------------------
# Geschützte Tags (werden beim Sync nie automatisch entfernt)
# ---------------------------------------------------------------------------

PROTECTED_TAGS = frozenset({"leech", "marked"})  # type: frozenset

# Maximale Anzahl gespeicherter Backups
_MAX_BACKUPS = 20


# ---------------------------------------------------------------------------
# Laden
# ---------------------------------------------------------------------------


def load_cards():
    """Liest CARDS_FILE und gibt die enthaltene Karten-Liste zurück.

    Toleriert eine UTF-8-BOM (utf-8-sig). Wirft FileNotFoundError oder
    ValueError bei Problemen.
    """
    if not CARDS_FILE.exists():
        raise FileNotFoundError(
            f"Die Datei '{CARDS_FILE.name}' wurde nicht gefunden "
            f"(erwartet in: {CARDS_FILE.parent})."
        )

    try:
        raw = CARDS_FILE.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"'{CARDS_FILE.name}' enthält kein gültiges JSON: {exc}"
        ) from exc

    if not isinstance(data, list):
        raise ValueError(
            f"'{CARDS_FILE.name}' muss ein JSON-Array enthalten, kein Objekt oder Skalar."
        )

    return data


# ---------------------------------------------------------------------------
# Speichern (atomar mit Backup)
# ---------------------------------------------------------------------------


def save_cards(cards):
    """Schreibt die Karten-Liste atomar in CARDS_FILE.

    Wenn CARDS_FILE bereits existiert, wird zuerst eine Sicherungskopie nach
    BACKUP_DIR angelegt. Es werden maximal _MAX_BACKUPS Backups behalten.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Backup der vorhandenen Datei
    if CARDS_FILE.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"cards_{timestamp}.json"
        backup_path = BACKUP_DIR / backup_name
        shutil.copy2(CARDS_FILE, backup_path)
        _prune_backups()

    # Atomares Schreiben: temp-Datei im selben Verzeichnis, dann os.replace
    content = json.dumps(cards, ensure_ascii=False, indent=2)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=CARDS_FILE.parent, prefix=".cards_tmp_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, CARDS_FILE)
    except Exception:
        # Aufräumen, falls etwas schiefgeht
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _prune_backups() -> None:
    """Löscht ältere Backups, wenn mehr als _MAX_BACKUPS vorhanden sind."""
    backups = sorted(BACKUP_DIR.glob("cards_*.json"))
    excess = len(backups) - _MAX_BACKUPS
    for backup in backups[:excess]:
        try:
            backup.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Normalisierung
# ---------------------------------------------------------------------------


def normalize_text(value):
    """Normalisiert einen Feldwert zu einer Zeichenkette.

    - None  → ""
    - str   → gestrippt
    - int/float → str
    - list/dict → ValueError
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        raise ValueError(
            f"Ungültiger Feldwert (bool): {value!r}. Erwartet wird eine Zeichenkette."
        )
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    raise ValueError(
        f"Ungültiger Feldwert ({type(value).__name__}): {value!r}. "
        "Erwartet wird eine Zeichenkette, Zahl oder null."
    )


def normalize_tags(tags):
    """Normalisiert eine Tag-Liste.

    - None        → []
    - list[str]   → bereinigt (Strip, Leerzeichen → '-', leer entfernt, Duplikate entfernt)
    - Non-list    → ValueError
    """
    if tags is None:
        return []
    if not isinstance(tags, list):
        raise ValueError(
            f"'tags' muss eine Liste sein, nicht {type(tags).__name__}: {tags!r}"
        )

    seen = set()  # type: set
    result = []  # type: List[str]
    for tag in tags:
        if not isinstance(tag, str):
            tag = str(tag)
        tag = tag.strip()
        # Internes Leerzeichen → '-'
        tag = re.sub(r"\s+", "-", tag)
        if not tag:
            continue
        if tag not in seen:
            seen.add(tag)
            result.append(tag)

    return result

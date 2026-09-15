"""
config.py — Zentrale Konfiguration für Anki English Manager.

Beim Start wird PROJECT_DIR bestimmt (EXE-Verzeichnis oder Script-Verzeichnis),
dann config.json geladen. Fehlende Schlüssel werden mit Standardwerten ergänzt.
"""

import json
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Verzeichnisse
# ---------------------------------------------------------------------------

import shutil

_SCRIPT_DIR = Path(__file__).resolve().parent

if sys.platform == "darwin":
    DATA_DIR = Path.home() / "Library" / "Application Support" / "AnkiEnglishManager"
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise RuntimeError(f"Datenordner konnte nicht erstellt werden: {DATA_DIR}\n{exc}") from exc

    # Einmalige Migration bei Ausführung aus den Sourcen
    if not getattr(sys, "frozen", False):
        if not (DATA_DIR / "config.json").exists() and not (DATA_DIR / "cards.json").exists():
            _migrated = False
            for _fname in ("config.json", "cards.json"):
                _src = _SCRIPT_DIR / _fname
                if _src.exists():
                    shutil.copy2(_src, DATA_DIR / _fname)
                    _migrated = True
            if _migrated:
                print(f"INFO: Daten wurden von '{_SCRIPT_DIR}' nach '{DATA_DIR}' kopiert.")
else:
    if getattr(sys, "frozen", False):
        # Eingefroren als EXE (PyInstaller)
        DATA_DIR = Path(sys.executable).resolve().parent
    else:
        DATA_DIR = _SCRIPT_DIR

CARDS_FILE = DATA_DIR / "cards.json"  # type: Path
BACKUP_DIR = DATA_DIR / "backups"  # type: Path

# ---------------------------------------------------------------------------
# Standardwerte
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "deck_name": "Englisch",
    "model_name": "English Active Speaking",
    "anki_connect_url": "http://localhost:8765",
    "expected_profile": None,
    "max_auto_delete": 3,
}

_CONFIG_FILE: Path = DATA_DIR / "config.json"

# ---------------------------------------------------------------------------
# config.json laden oder erstellen
# ---------------------------------------------------------------------------


def _load_config():
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.write_text(
            json.dumps(_DEFAULTS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return dict(_DEFAULTS)

    try:
        raw = _CONFIG_FILE.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Ungültiges JSON in {_CONFIG_FILE.name}: {exc}\n"
            "Bitte die Datei korrigieren oder löschen (wird dann neu erstellt)."
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"{_CONFIG_FILE.name} muss ein JSON-Objekt sein, kein Array oder Skalar."
        )

    # Fehlende Schlüssel mit Standardwerten auffüllen
    merged: dict = dict(_DEFAULTS)
    merged.update(data)

    # Typvalidierung
    if not isinstance(merged["deck_name"], str) or not merged["deck_name"].strip():
        raise ValueError("config.json: 'deck_name' muss eine nicht-leere Zeichenkette sein.")
    if not isinstance(merged["model_name"], str) or not merged["model_name"].strip():
        raise ValueError("config.json: 'model_name' muss eine nicht-leere Zeichenkette sein.")
    if not isinstance(merged["anki_connect_url"], str) or not merged["anki_connect_url"].strip():
        raise ValueError("config.json: 'anki_connect_url' muss eine nicht-leere Zeichenkette sein.")
    if merged["expected_profile"] is not None and not isinstance(merged["expected_profile"], str):
        raise ValueError("config.json: 'expected_profile' muss eine Zeichenkette oder null sein.")
    if not isinstance(merged["max_auto_delete"], int) or isinstance(merged["max_auto_delete"], bool):
        raise ValueError("config.json: 'max_auto_delete' muss eine ganze Zahl sein.")
    if merged["max_auto_delete"] < 0:
        raise ValueError("config.json: 'max_auto_delete' darf nicht negativ sein.")

    return merged


_cfg = _load_config()

# ---------------------------------------------------------------------------
# Öffentliche Konstanten
# ---------------------------------------------------------------------------

DECK_NAME = _cfg["deck_name"]          # type: str
MODEL_NAME = _cfg["model_name"]        # type: str
ANKI_CONNECT_URL = _cfg["anki_connect_url"]  # type: str
EXPECTED_PROFILE = _cfg["expected_profile"]  # type: Optional[str]
MAX_AUTO_DELETE = _cfg["max_auto_delete"]    # type: int
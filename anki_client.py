"""
anki_client.py — Gemeinsamer AnkiConnect-Client für Anki English Manager.

Stellt invoke_anki, Suchabfragen und preflight_check() bereit.
"""

from typing import List

import requests

from config import (
    ANKI_CONNECT_URL,
    DECK_NAME,
    EXPECTED_PROFILE,
    MODEL_NAME,
)

# Felder, die das Note-Type mindestens besitzen muss
_REQUIRED_FIELDS = ["CardId", "German", "English", "Alternative1", "Alternative2"]


# ---------------------------------------------------------------------------
# Kernfunktion
# ---------------------------------------------------------------------------


def invoke_anki(action, params=None):
    """Sendet einen AnkiConnect-Befehl und gibt das Ergebnis zurück.

    Wirft requests.RequestException bei Verbindungsproblemen und
    RuntimeError bei AnkiConnect-Fehlern.
    """
    if params is None:
        params = {}

    response = requests.post(
        ANKI_CONNECT_URL,
        json={"action": action, "version": 6, "params": params},
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect-Fehler: {data['error']}")

    return data.get("result")


# ---------------------------------------------------------------------------
# Suchabfragen
# ---------------------------------------------------------------------------


def _escape_anki(name: str) -> str:
    """Maskiert Sonderzeichen in Anki-Suchabfragen (\\, \", *, _)."""
    for ch in ("\\", '"', "*", "_"):
        name = name.replace(ch, "\\" + ch)
    return name


def deck_query():
    """Suchabfrage für genau das konfigurierte Deck (ohne Unter-Decks) und den Note-Type."""
    deck = _escape_anki(DECK_NAME)
    model = _escape_anki(MODEL_NAME)
    return f'deck:"{deck}" -deck:"{deck}::*" note:"{model}"'


def model_query():
    """Suchabfrage für alle Notizen des konfigurierten Note-Types (gesamte Sammlung)."""
    model = _escape_anki(MODEL_NAME)
    return f'note:"{model}"'


# ---------------------------------------------------------------------------
# Notizen suchen
# ---------------------------------------------------------------------------


def find_notes_info(query):
    """Gibt notesInfo für alle Treffer der Suchabfrage zurück.

    Lädt notesInfo in Blöcken von 500, um AnkiConnect nicht zu überlasten.
    Gibt eine leere Liste zurück, wenn nichts gefunden wurde.
    """
    note_ids = invoke_anki("findNotes", {"query": query}) or []  # type: List[int]
    if not note_ids:
        return []

    notes = []  # type: List[dict]
    chunk_size = 500
    for i in range(0, len(note_ids), chunk_size):
        chunk = note_ids[i : i + chunk_size]
        result = invoke_anki("notesInfo", {"notes": chunk})
        if result:
            notes.extend(result)

    return notes


def notes_info_by_ids(note_ids):
    """Gibt notesInfo für eine konkrete Liste von Notiz-IDs zurück.

    Nützlich zur Verifikation nach updateNoteFields.
    """
    if not note_ids:
        return []

    notes = []  # type: List[dict]
    chunk_size = 500
    for i in range(0, len(note_ids), chunk_size):
        chunk = note_ids[i : i + chunk_size]
        result = invoke_anki("notesInfo", {"notes": chunk})
        if result:
            notes.extend(result)

    return notes


# ---------------------------------------------------------------------------
# Vorab-Prüfung
# ---------------------------------------------------------------------------


def preflight_check():
    """Prüft AnkiConnect, Deck, Note-Type, Felder und optional das Profil.

    Wirft RuntimeError bei einem Problem. Gibt eine Zusammenfassung aus.
    """
    # 1. Erreichbarkeit
    try:
        invoke_anki("version")
    except requests.RequestException as exc:
        raise RuntimeError(
            f"AnkiConnect ist nicht erreichbar ({ANKI_CONNECT_URL}): {exc}\n"
            "Bitte Anki starten und AnkiConnect aktivieren."
        ) from exc

    # 2. Deck vorhanden?
    deck_names = invoke_anki("deckNames") or []  # type: List[str]
    if DECK_NAME not in deck_names:
        raise RuntimeError(
            f"Das Deck '{DECK_NAME}' wurde in Anki nicht gefunden.\n"
            "Bitte das Deck manuell anlegen oder 'deck_name' in config.json anpassen."
        )

    # 3. Note-Type vorhanden?
    model_names = invoke_anki("modelNames") or []  # type: List[str]
    if MODEL_NAME not in model_names:
        raise RuntimeError(
            f"Der Note-Type '{MODEL_NAME}' wurde in Anki nicht gefunden.\n"
            "Bitte den Note-Type manuell anlegen oder 'model_name' in config.json anpassen."
        )

    # 4. Pflichtfelder vorhanden?
    existing_fields = (
        invoke_anki("modelFieldNames", {"modelName": MODEL_NAME}) or []
    )
    missing_fields = [f for f in _REQUIRED_FIELDS if f not in existing_fields]
    if missing_fields:
        raise RuntimeError(
            f"Dem Note-Type '{MODEL_NAME}' fehlen folgende Felder: "
            + ", ".join(missing_fields)
        )

    # 5. Profil-Prüfung (optional)
    profile_info = ""
    if EXPECTED_PROFILE is not None:
        active_profile = None
        try:
            active_profile = invoke_anki("getActiveProfile") or ""
        except RuntimeError as exc:
            # Wenn AnkiConnect die Aktion nicht kennt, Warnung ausgeben und
            # Prüfung überspringen; jeden anderen Fehler weiterwerfen.
            anki_msg = str(exc).lower()
            if "unsupported action" in anki_msg or "unknown action" in anki_msg:
                print(
                    "Warnung: Profil-Prüfung nicht möglich "
                    "(getActiveProfile wird von dieser AnkiConnect-Version nicht unterstützt)."
                )
            else:
                raise

        if active_profile is not None and active_profile != EXPECTED_PROFILE:
            raise RuntimeError(
                f"Falsches Anki-Profil aktiv: '{active_profile}' "
                f"(erwartet: '{EXPECTED_PROFILE}').\n"
                "Bitte das richtige Profil in Anki auswählen."
            )
        if active_profile is not None:
            profile_info = f", Profil: {active_profile}"

    print(
        f"Vorab-Prüfung OK — Deck: '{DECK_NAME}', "
        f"Note-Type: '{MODEL_NAME}'{profile_info}"
    )

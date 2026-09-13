import json

import pyperclip
import requests

from config import DECK_NAME, MODEL_NAME


ANKI_CONNECT_URL = "http://localhost:8765"
REQUIRED_FIELDS = ["German", "English"]
OPTIONAL_FIELDS = ["Alternative1", "Alternative2"]
NOTE_FIELDS = REQUIRED_FIELDS + OPTIONAL_FIELDS
CARD_ID_FIELD = "CardId"


def invoke_anki(action, params):
    payload = {
        "action": action,
        "version": 6,
        "params": params,
    }

    response = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10)
    response.raise_for_status()

    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect error: {data['error']}")

    return data.get("result")


def load_cards_from_clipboard():
    clipboard_content = pyperclip.paste()
    if not clipboard_content.strip():
        raise ValueError("Zwischenablage ist leer.")

    try:
        cards = json.loads(clipboard_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Zwischenablage enthält kein gültiges JSON: {exc}") from exc

    if not isinstance(cards, list):
        raise ValueError("Der Inhalt der Zwischenablage muss ein JSON-Array sein.")

    return cards


def get_highest_card_id():
    note_ids = invoke_anki(
        "findNotes",
        {"query": f'deck:"{DECK_NAME}" note:"{MODEL_NAME}"'},
    )
    if not note_ids:
        return 0

    notes = invoke_anki("notesInfo", {"notes": note_ids})
    highest_id = 0

    for note in notes:
        card_id_value = note["fields"].get(CARD_ID_FIELD, {}).get("value", "").strip()
        if card_id_value.isdigit():
            highest_id = max(highest_id, int(card_id_value))

    return highest_id


def build_note(card, card_id):
    if not isinstance(card, dict):
        raise ValueError("Jede Karte muss ein JSON-Objekt sein.")

    missing_fields = [field for field in REQUIRED_FIELDS if field not in card]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"Pflichtfelder fehlen: {missing}")

    fields = {field: str(card.get(field, "")) for field in NOTE_FIELDS}
    fields[CARD_ID_FIELD] = str(card_id)
    tags = card.get("tags", [])

    if tags is None:
        tags = []
    if not isinstance(tags, list):
        raise ValueError("Optionales Feld 'tags' muss eine Liste sein.")

    return {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": fields,
        "tags": [str(tag) for tag in tags],
    }


def import_cards():
    cards = load_cards_from_clipboard()
    success_count = 0
    skipped_duplicates = 0
    error_count = 0
    next_card_id = get_highest_card_id() + 1

    for index, card in enumerate(cards, start=1):
        try:
            note = build_note(card, next_card_id)
            result = invoke_anki("addNote", {"note": note})
            if result is None:
                raise RuntimeError("AnkiConnect hat keine Notiz-ID zurückgegeben.")
            success_count += 1
            next_card_id += 1
        except Exception as exc:
            error_message = str(exc)
            if "duplicate" in error_message.lower():
                skipped_duplicates += 1
                continue

            error_count += 1
            print(f"Karte {index} konnte nicht importiert werden: {exc}")

    print(f"Erfolgreich importiert: {success_count}")
    print(f"Übersprungen (Duplikate): {skipped_duplicates}")
    print(f"Fehler: {error_count}")


def main():
    try:
        import_cards()
    except requests.RequestException as exc:
        print(f"Verbindung zu AnkiConnect fehlgeschlagen: {exc}")
    except Exception as exc:
        print(f"Fehler: {exc}")


if __name__ == "__main__":
    main()

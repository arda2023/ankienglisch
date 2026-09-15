import requests

from anki_client import invoke_anki
from config import CARDS_FILE, DECK_NAME, MODEL_NAME

import json

CARD_ID_FIELD = "CardId"
SYNC_FIELDS = ["German", "English", "Alternative1", "Alternative2"]


def load_cards_from_file():
    if not CARDS_FILE.exists():
        raise FileNotFoundError(f"{CARDS_FILE.name} wurde nicht gefunden.")

    with CARDS_FILE.open(encoding="utf-8") as file:
        cards = json.load(file)

    if not isinstance(cards, list):
        raise ValueError(f"{CARDS_FILE.name} muss ein JSON-Array enthalten.")

    return cards


def validate_card(card, index):
    if not isinstance(card, dict):
        raise ValueError(f"Karte {index} muss ein JSON-Objekt sein.")

    card_id = str(card.get(CARD_ID_FIELD, "")).strip()
    if not card_id:
        raise ValueError(f"Karte {index}: CardId fehlt oder ist leer.")

    missing_fields = [field for field in SYNC_FIELDS if field not in card]
    if missing_fields:
        missing = ", ".join(missing_fields)
        raise ValueError(f"Karte {index} (CardId {card_id}): Pflichtfelder fehlen: {missing}")

    tags = card.get("tags", [])
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        raise ValueError(f"Karte {index} (CardId {card_id}): 'tags' muss eine Liste sein.")

    return card_id


def get_existing_notes():
    note_ids = invoke_anki(
        "findNotes",
        {"query": f'deck:"{DECK_NAME}" note:"{MODEL_NAME}"'},
    )
    if not note_ids:
        return []

    return invoke_anki("notesInfo", {"notes": note_ids})


def build_existing_index(notes):
    index = {}
    duplicate_note_ids = []

    for note in notes:
        card_id = note["fields"].get(CARD_ID_FIELD, {}).get("value", "").strip()
        note_info = {
            "note_id": note["noteId"],
            "tags": note["tags"],
        }

        if card_id in index:
            duplicate_note_ids.append(note["noteId"])
            print(
                f"Warnung: Doppelte CardId '{card_id}' in Anki "
                f"(Notiz {note['noteId']} wird übersprungen)."
            )
            continue

        index[card_id] = note_info

    return index, duplicate_note_ids


def build_fields(card):
    fields = {field: str(card.get(field, "")) for field in SYNC_FIELDS}
    fields[CARD_ID_FIELD] = str(card[CARD_ID_FIELD]).strip()
    return fields


def sync_tags(note_id, current_tags, desired_tags):
    current = set(current_tags)
    desired = {str(tag) for tag in desired_tags}

    tags_to_add = desired - current
    tags_to_remove = current - desired

    if tags_to_add:
        invoke_anki(
            "addTags",
            {"notes": [note_id], "tags": " ".join(sorted(tags_to_add))},
        )

    if tags_to_remove:
        invoke_anki(
            "removeTags",
            {"notes": [note_id], "tags": " ".join(sorted(tags_to_remove))},
        )


def update_note(note_id, card, current_tags):
    invoke_anki(
        "updateNoteFields",
        {"note": {"id": note_id, "fields": build_fields(card)}},
    )
    sync_tags(note_id, current_tags, card.get("tags", []))


def add_note(card):
    tags = card.get("tags", []) or []
    note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": build_fields(card),
        "tags": [str(tag) for tag in tags],
    }
    result = invoke_anki("addNote", {"note": note})
    if result is None:
        raise RuntimeError("AnkiConnect hat keine Notiz-ID zurückgegeben.")


def delete_notes(note_ids):
    if note_ids:
        invoke_anki("deleteNotes", {"notes": note_ids})


def sync_cards():
    cards = load_cards_from_file()
    existing_notes = get_existing_notes()
    existing_by_card_id, duplicate_note_ids = build_existing_index(existing_notes)

    json_card_ids = set()
    added = 0
    updated = 0
    deleted = 0
    errors = 0

    for index, card in enumerate(cards, start=1):
        card_id = None
        try:
            card_id = validate_card(card, index)
            if card_id in json_card_ids:
                raise ValueError(f"Doppelte CardId im JSON: {card_id}")
            json_card_ids.add(card_id)

            if card_id in existing_by_card_id:
                note_info = existing_by_card_id[card_id]
                update_note(note_info["note_id"], card, note_info["tags"])
                updated += 1
            else:
                add_note(card)
                added += 1
        except Exception as exc:
            errors += 1
            label = card_id if card_id is not None else card.get(CARD_ID_FIELD, "?")
            print(f"Karte {index} (CardId: {label}): {exc}")

    notes_to_delete = list(duplicate_note_ids)
    for note in existing_notes:
        card_id = note["fields"].get(CARD_ID_FIELD, {}).get("value", "").strip()
        if card_id not in json_card_ids:
            notes_to_delete.append(note["noteId"])

    try:
        delete_count = len(notes_to_delete)
        delete_notes(notes_to_delete)
        deleted = delete_count
    except Exception as exc:
        errors += 1
        print(f"Löschen fehlgeschlagen: {exc}")

    print(f"Hinzugefügt: {added}")
    print(f"Aktualisiert: {updated}")
    print(f"Gelöscht: {deleted}")
    print(f"Fehler: {errors}")


def main():
    try:
        sync_cards()
    except requests.RequestException as exc:
        print(f"Verbindung zu AnkiConnect fehlgeschlagen: {exc}")
    except Exception as exc:
        print(f"Fehler: {exc}")


if __name__ == "__main__":
    main()

import json
from pathlib import Path

import requests

from config import DECK_NAME, MODEL_NAME

ANKI_CONNECT_URL = "http://localhost:8765"
EXPORT_FIELDS = ["CardId", "German", "English", "Alternative1", "Alternative2"]
OUTPUT_FILE = Path(__file__).parent / "cards.json"


def invoke_anki(action, params=None):
    if params is None:
        params = {}

    response = requests.post(
        ANKI_CONNECT_URL,
        json={
            "action": action,
            "version": 6,
            "params": params,
        },
        timeout=10,
    )
    response.raise_for_status()

    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])

    return data.get("result")


def card_id_sort_key(card):
    card_id = str(card.get("CardId", "")).strip()
    if card_id.isdigit():
        return int(card_id)
    return float("inf")


def export_cards():
    note_ids = invoke_anki(
        "findNotes",
        {"query": f'deck:"{DECK_NAME}" note:"{MODEL_NAME}"'},
    )
    if not note_ids:
        notes = []
    else:
        notes = invoke_anki("notesInfo", {"notes": note_ids})

    cards = []
    for note in notes:
        fields = note["fields"]
        card = {field: fields[field]["value"] for field in EXPORT_FIELDS}
        card["tags"] = note["tags"]
        cards.append(card)

    cards.sort(key=card_id_sort_key)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(cards, file, ensure_ascii=False, indent=2)

    print(f"Exportiert: {len(cards)}")


def main():
    try:
        export_cards()
    except requests.RequestException as exc:
        print(f"Verbindung zu AnkiConnect fehlgeschlagen: {exc}")
    except Exception as exc:
        print(f"Fehler: {exc}")


if __name__ == "__main__":
    main()

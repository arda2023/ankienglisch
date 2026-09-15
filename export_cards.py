"""
export_cards.py — Export der Anki-Notizen nach cards.json.

Liest alle Notizen aus dem konfigurierten Deck, entfernt geschützte Tags
und schreibt sie via save_cards() (Backup + atomares Schreiben) sortiert
nach numerischer CardId. Bei 0 gefundenen Notizen oder unvollständigen
Notizen wird cards.json NICHT verändert.
"""

import requests

from anki_client import deck_query, find_notes_info, preflight_check
from cards_file import PROTECTED_TAGS, save_cards
from config import DECK_NAME, MODEL_NAME

EXPORT_FIELDS = ["CardId", "German", "English", "Alternative1", "Alternative2"]


def card_id_sort_key(card):
    card_id = str(card.get("CardId", "")).strip()
    if card_id.isdigit():
        return int(card_id)
    return float("inf")


def build_card(note):
    fields = note["fields"]
    missing = [field for field in EXPORT_FIELDS if field not in fields]
    if missing:
        raise ValueError(
            f"Notiz {note['noteId']} hat folgende Felder nicht: {', '.join(missing)}."
        )

    card = {field: fields[field]["value"] for field in EXPORT_FIELDS}
    card["tags"] = [tag for tag in note["tags"] if tag not in PROTECTED_TAGS]
    return card


def warn_about_card_ids(cards):
    invalid = [c for c in cards if not str(c.get("CardId", "")).strip().isdigit()]
    if invalid:
        print(
            f"Warnung: {len(invalid)} Notiz(en) haben eine leere oder "
            "nicht-numerische CardId."
        )

    seen = set()
    duplicates = set()
    for card in cards:
        card_id = str(card.get("CardId", "")).strip()
        if not card_id.isdigit():
            continue
        if card_id in seen:
            duplicates.add(card_id)
        seen.add(card_id)

    if duplicates:
        print(
            "Warnung: doppelte CardId(s) gefunden: "
            + ", ".join(sorted(duplicates, key=int))
        )


def export_cards():
    preflight_check()

    notes = find_notes_info(deck_query())
    if not notes:
        raise RuntimeError(
            f"Es wurden keine Notizen im Deck '{DECK_NAME}' "
            f"(Note-Type '{MODEL_NAME}') gefunden.\n"
            "Möglicherweise ist in Anki das falsche Profil aktiv, oder das "
            "Deck ist (noch) leer. cards.json wurde NICHT verändert."
        )

    cards = [build_card(note) for note in notes]

    warn_about_card_ids(cards)

    cards.sort(key=card_id_sort_key)

    save_cards(cards)

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

"""
import_cards.py — Import von Karten aus der Zwischenablage nach Anki.

Liest ein JSON-Array aus der Zwischenablage (toleriert Markdown-Codefences
und Text drumherum), validiert alle Karten, überspringt Duplikate (Vergleich
über eine normalisierte German-Kennung) und vergibt neue CardIds. Erfolgreich
importierte Karten werden an cards.json angehängt, damit ein späterer Sync
sie nicht wegen einer veralteten Datei löscht.
"""

import html
import json
import re
import unicodedata

import pyperclip
import requests

from anki_client import deck_query, find_notes_info, invoke_anki, model_query, preflight_check
from card_fields import ALL_FIELDS, JSON_KEY_ORDER, validate_markers
from cards_file import load_cards, normalize_tags, normalize_text, save_cards
from config import DECK_NAME, MODEL_NAME

CARD_ID_FIELD = "CardId"


# Matches any opening fence: ```<optional-tag>, captures content up to closing ```
_FENCE_RE = re.compile(r"^```(\S*)\s*\n(.*?)^```", re.DOTALL | re.MULTILINE)
_TAG_RE = re.compile(r"<[^>]+>")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:!?…]+$")


# ---------------------------------------------------------------------------
# Zwischenablage lesen
# ---------------------------------------------------------------------------


def extract_json_text(clipboard_content):
    """Extrahiert den JSON-Teil aus dem Zwischenablage-Inhalt.

    Bevorzugt den ersten ```-Codeblock (beliebiger Sprachtag), dessen Inhalt
    mit '[' beginnt. Wenn kein passender Fence-Block gefunden wird, wird der
    Bereich vom ersten '[' bis zum letzten ']' verwendet.
    """
    # Collect all fenced blocks; keep the first one starting with "["
    first_fence_content = None
    for m in _FENCE_RE.finditer(clipboard_content):
        content = m.group(2).strip()
        if content.startswith("["):
            return content
        if first_fence_content is None:
            first_fence_content = content

    # No fenced block starting with "[" found — fall back to first "[" … last "]"
    start = clipboard_content.find("[")
    end = clipboard_content.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(
            "In der Zwischenablage wurde kein JSON-Array gefunden. "
            "Erwartet wird entweder ein ```…```-Codeblock oder "
            "ein Array in eckigen Klammern [ ... ]."
        )
    return clipboard_content[start : end + 1]


def load_cards_from_clipboard():
    clipboard_content = pyperclip.paste()
    if not clipboard_content or not clipboard_content.strip():
        raise ValueError("Zwischenablage ist leer.")

    json_text = extract_json_text(clipboard_content)

    try:
        cards = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Zwischenablage enthält kein gültiges JSON: {exc}") from exc

    if not isinstance(cards, list):
        raise ValueError("Der Inhalt der Zwischenablage muss ein JSON-Array sein.")

    return cards


# ---------------------------------------------------------------------------
# Validierung
# ---------------------------------------------------------------------------


def validate_and_normalize_card(card, index):
    """Validiert eine einzelne Karte und gibt normalisierte Felder zurück.

    Wirft ValueError mit einer Meldung, die den Karten-Index nennt.
    Eine im JSON enthaltene CardId wird bewusst ignoriert — IDs vergibt
    ausschließlich die App.
    """
    if not isinstance(card, dict):
        raise ValueError(f"Karte {index}: muss ein JSON-Objekt sein.")

    normalized = {}
    problems = []
    for name in ALL_FIELDS:
        if name == CARD_ID_FIELD:
            continue  # Die App vergibt die ID selbst.
        try:
            value = normalize_text(card.get(name))
            validate_markers(value)
            if name in ("German", "English") and not value:
                raise ValueError("Feld ist leer.")
            normalized[name] = value
        except ValueError as exc:
            problems.append(f"Karte {index}: {name} ist ungültig ({exc}).")
    try:
        normalized["tags"] = normalize_tags(card.get("tags"))
    except ValueError as exc:
        problems.append(f"Karte {index}: tags ist ungültig ({exc}).")
    if problems:
        raise ValueError("\n".join(problems))
    for name, limit in (("Rule", 160), ("Hint", 60)):
        if len(normalized[name]) > limit:
            print(f"Warnung: Karte {index}: {name} ist länger als {limit} Zeichen.")
    if normalized["Pattern"] and "[[" not in normalized["English"]:
        print(f"Warnung: Karte {index}: Pattern ist gesetzt, aber English enthält keinen [[…]]-Marker.")
    return normalized


def validate_cards(cards):
    """Validiert alle Karten. Bei mindestens einem Problem wird der gesamte
    Import mit allen gefundenen Problemen abgebrochen (keine Teilimporte)."""
    problems = []
    normalized = []

    for index, card in enumerate(cards, start=1):
        try:
            normalized.append(validate_and_normalize_card(card, index))
        except ValueError as exc:
            problems.append(str(exc))

    if problems:
        raise ValueError(
            "Import abgebrochen — folgende Probleme wurden gefunden:\n"
            + "\n".join(problems)
        )

    return normalized


# ---------------------------------------------------------------------------
# Duplikaterkennung
# ---------------------------------------------------------------------------


def normalize_german_key(text):
    """Normalisiert einen German-Wert zu einer Vergleichs-Kennung.

    Reihenfolge:
    1. HTML-Tags entfernen
    2. HTML-Entities dekodieren (z. B. &amp; → &)
    3. Unicode NFC-Normalisierung
    4. Kleinschreiben
    5. Alle Whitespace-Varianten (inkl. geschütztem Leerzeichen \\xa0) zu
       einem normalen Leerzeichen zusammenfassen
    6. Strip
    7. Abschließende Satzzeichen entfernen
    8. Strip
    """
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    text = _TRAILING_PUNCT_RE.sub("", text).strip()
    return text


def build_existing_german_keys():
    """Normalisierte German-Kennungen aller vorhandenen Notizen im Deck."""
    notes = find_notes_info(deck_query())
    keys = set()
    for note in notes:
        value = note["fields"].get("German", {}).get("value", "")
        key = normalize_german_key(value)
        if key:
            keys.add(key)
    return keys


# ---------------------------------------------------------------------------
# CardId-Vergabe
# ---------------------------------------------------------------------------


def get_highest_card_id_in_anki():
    """Höchste numerische CardId unter allen Notizen dieses Note-Types in der
    gesamten Sammlung (nicht nur im konfigurierten Deck)."""
    notes = find_notes_info(model_query())
    highest = 0
    for note in notes:
        value = note["fields"].get(CARD_ID_FIELD, {}).get("value", "").strip()
        if value.isdigit():
            highest = max(highest, int(value))
    return highest


def get_highest_card_id_in_file():
    """Höchste numerische CardId in cards.json, oder 0 wenn die Datei fehlt."""
    try:
        cards = load_cards()
    except FileNotFoundError:
        return 0

    highest = 0
    for card in cards:
        value = str(card.get(CARD_ID_FIELD, "")).strip()
        if value.isdigit():
            highest = max(highest, int(value))
    return highest


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_cards():
    preflight_check()

    raw_cards = load_cards_from_clipboard()
    if not raw_cards:
        print("Die Zwischenablage enthält keine Karten.")
        return

    normalized_cards = validate_cards(raw_cards)

    existing_keys = build_existing_german_keys()
    seen_batch_keys = set()

    to_import = []
    skipped = []
    for card in normalized_cards:
        key = normalize_german_key(card["German"])
        if key in existing_keys or key in seen_batch_keys:
            skipped.append(card["German"])
            continue
        seen_batch_keys.add(key)
        to_import.append(card)

    next_card_id = max(get_highest_card_id_in_anki(), get_highest_card_id_in_file()) + 1
    first_card_id = next_card_id

    imported_cards = []
    error_count = 0

    for card in to_import:
        note = {
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {name: str(next_card_id) if name == CARD_ID_FIELD else card[name]
                       for name in ALL_FIELDS},
            "tags": card["tags"],
            "options": {"allowDuplicate": True},
        }

        try:
            result = invoke_anki("addNote", {"note": note})
            if result is None:
                raise RuntimeError("AnkiConnect hat keine Notiz-ID zurückgegeben.")
        except Exception as exc:
            error_count += 1
            print(
                f"Karte '{card['German']}' (CardId {next_card_id}) "
                f"konnte nicht importiert werden: {exc}"
            )
            continue

        imported_cards.append({
            name: str(next_card_id) if name == CARD_ID_FIELD else card[name]
            for name in JSON_KEY_ORDER
        })
        next_card_id += 1

    for german in skipped:
        print(f"Übersprungen (Duplikat): {german}")

    # Summary (always printed, even when the cards.json update fails below)
    imported_count = len(imported_cards)
    print(f"Importiert: {imported_count}")
    print(f"Übersprungen (Duplikate): {len(skipped)}")
    print(f"Fehler: {error_count}")
    if imported_cards:
        last_card_id = int(imported_cards[-1][CARD_ID_FIELD])
        print(f"Vergebene CardIds: {first_card_id}–{last_card_id}")
    else:
        print("Vergebene CardIds: keine")

    if imported_cards:
        try:
            file_cards = load_cards()
        except FileNotFoundError:
            file_cards = []
        try:
            file_cards.extend(imported_cards)
            save_cards(file_cards)
        except Exception as exc:
            print(
                f"\nWARNUNG: {imported_count} Karte(n) wurden in Anki angelegt, "
                f"aber cards.json konnte nicht aktualisiert werden ({exc}). "
                "Bitte jetzt 'Export nach cards.json' ausführen, "
                "BEVOR synchronisiert wird."
            )
            raise RuntimeError(
                f"{imported_count} Karte(n) in Anki importiert, "
                "cards.json-Aktualisierung fehlgeschlagen."
            ) from exc


def main():
    try:
        import_cards()
    except requests.RequestException as exc:
        print(f"Verbindung zu AnkiConnect fehlgeschlagen: {exc}")
    except Exception as exc:
        print(f"Fehler: {exc}")


if __name__ == "__main__":
    main()

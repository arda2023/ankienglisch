"""
sync_cards.py — Synchronisation zwischen cards.json und Anki.

Zwei Phasen:
  plan_sync()  → analysiert, ohne Änderungen durchzuführen (gibt SyncPlan zurück)
  apply_sync() → führt die Änderungen laut Plan aus

Die Planungsphase liest cards.json und die Anki-Notizen und bestimmt,
welche Notizen hinzugefügt, aktualisiert oder gelöscht werden sollen.
Die Anwendungsphase führt nur dann Löschungen durch, wenn keine Fehler
beim Hinzufügen oder Aktualisieren aufgetreten sind.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List

import requests

from anki_client import (
    deck_query,
    find_notes_info,
    invoke_anki,
    model_query,
    notes_info_by_ids,
    preflight_check,
)
from card_fields import ALL_FIELDS, validate_markers
from cards_file import is_protected_tag, load_cards, normalize_tags, normalize_text
from config import DECK_NAME, MODEL_NAME

CARD_ID_FIELD = "CardId"



# ---------------------------------------------------------------------------
# Datentypen
# ---------------------------------------------------------------------------


@dataclass
class AddEntry:
    """Eine Karte, die neu in Anki angelegt werden soll."""

    card: dict  # vollständige validierte Karte inkl. CardId und tags


@dataclass
class UpdateEntry:
    """Eine Anki-Notiz, die aktualisiert werden soll."""

    note_id: int
    card_id: str
    changed_fields: List[str]   # Namen der Felder/„tags", die sich unterscheiden
    new_fields: Dict[str, str]  # Nur ausdrücklich im JSON vorhandene Felder
    new_tags: List[str]         # Gewünschte nicht-geschützte Tags (aus cards.json)
    anki_tags: List[str]        # Aktuelle Tags der Anki-Notiz


@dataclass
class DeleteEntry:
    """Eine Anki-Notiz, die gelöscht werden soll."""

    note_id: int
    card_id: str
    german: str


@dataclass
class SyncPlan:
    """Ergebnis der Planungsphase; enthält keine Mutationen an Anki/Dateien."""

    to_add: List[AddEntry] = field(default_factory=list)
    to_update: List[UpdateEntry] = field(default_factory=list)
    unchanged_count: int = 0
    to_delete: List[DeleteEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    blocking_errors: List[str] = field(default_factory=list)
    has_stale_warning: bool = False


# ---------------------------------------------------------------------------
# Validierung (cards.json)
# ---------------------------------------------------------------------------


def _validate_json_cards(raw_cards):
    """Validiert alle Einträge aus cards.json.

    Gibt (validated, errors) zurück.  Bei mindestens einem Fehler ist
    validated leer und errors enthält alle gefundenen Probleme.
    """
    errors = []
    validated = []
    seen_ids: dict = {}  # card_id -> 1-basierter Index

    for index, card in enumerate(raw_cards, start=1):
        card_errors = []

        if not isinstance(card, dict):
            errors.append(f"Karte {index}: muss ein JSON-Objekt sein.")
            continue  # Weitere Validierung nicht möglich

        # --- CardId ---
        card_id_raw = card.get(CARD_ID_FIELD, "")
        try:
            card_id = normalize_text(card_id_raw)
        except ValueError as exc:
            card_errors.append(f"Karte {index}: CardId ungültig ({exc}).")
            card_id = ""

        if not card_id or not card_id.isdigit():
            card_errors.append(
                f"Karte {index}: CardId muss eine nicht-leere numerische "
                f"Zeichenkette sein (erhalten: {card_id_raw!r})."
            )
            card_id = ""
        elif card_id in seen_ids:
            card_errors.append(
                f"Karte {index}: doppelte CardId '{card_id}' "
                f"(bereits bei Karte {seen_ids[card_id]})."
            )
        else:
            seen_ids[card_id] = index

        label = card_id or "?"

        normalized = {CARD_ID_FIELD: card_id}
        for name in ALL_FIELDS:
            if name == CARD_ID_FIELD or name not in card:
                continue
            try:
                value = normalize_text(card[name])
                validate_markers(value)
                normalized[name] = value
            except ValueError as exc:
                card_errors.append(f"Karte {index} (CardId {label}): {name} ungültig ({exc}).")

        # --- tags ---
        try:
            tags = normalize_tags(card.get("tags"))
        except ValueError as exc:
            card_errors.append(
                f"Karte {index} (CardId {label}): tags ungültig ({exc})."
            )
            tags = []

        if card_errors:
            errors.extend(card_errors)
        else:
            normalized["tags"] = tags
            validated.append(normalized)

    if errors:
        return [], errors
    return validated, []


# ---------------------------------------------------------------------------
# Planungsphase
# ---------------------------------------------------------------------------


def plan_sync() -> SyncPlan:
    """Analysiert den Sync-Bedarf, ohne Anki oder cards.json zu verändern.

    Wirft RuntimeError oder requests.RequestException bei Verbindungsfehlern.
    Gibt einen SyncPlan zurück; bei blocking_errors sind alle Aktionslisten leer.
    """
    plan = SyncPlan()

    # 1. Vorab-Prüfung (Verbindung, Deck, Note-Type, Felder, Profil)
    preflight_check()

    # 2. cards.json laden
    raw_cards = load_cards()

    # 3. Alle Karten vollständig validieren (Abbruch bei jedem Fehler)
    validated_cards, json_errors = _validate_json_cards(raw_cards)
    if json_errors:
        plan.blocking_errors.extend(json_errors)
        return plan

    json_card_ids = {c[CARD_ID_FIELD] for c in validated_cards}
    max_json_id = max((int(cid) for cid in json_card_ids), default=0)

    # 4. Vorhandene Anki-Notizen laden
    anki_notes = find_notes_info(deck_query())

    # 4b. Alle Notizen des Note-Types laden (für Duplikaterkennung außerhalb des Decks)
    all_model_notes = find_notes_info(model_query())
    outside_deck_notes: dict = {}  # card_id_str -> note_id
    deck_note_ids = {n["noteId"] for n in anki_notes}
    for n in all_model_notes:
        if n["noteId"] not in deck_note_ids:
            raw_cid = n["fields"].get(CARD_ID_FIELD, {}).get("value", "").strip()
            if raw_cid and raw_cid.isdigit():
                outside_deck_notes[raw_cid] = n["noteId"]

    # Index aufbauen; Duplikate und leere CardIds separat behandeln
    anki_index: dict = {}   # card_id_str -> note-dict
    anki_dupes: dict = {}   # card_id_str -> [note_ids]
    max_anki_id = 0

    for note in anki_notes:
        raw_cid = note["fields"].get(CARD_ID_FIELD, {}).get("value", "").strip()

        # 7. Notizen ohne gültige (numerische) CardId: nur warnen, nie anfassen
        if not raw_cid or not raw_cid.isdigit():
            german = note["fields"].get("German", {}).get("value", "").strip()
            plan.warnings.append(
                f"Notiz {note['noteId']} hat keine gültige CardId "
                f"(German: {german[:60]!r}) – wird übersprungen."
            )
            continue

        numeric_id = int(raw_cid)
        if numeric_id > max_anki_id:
            max_anki_id = numeric_id

        # 5. Duplikat-Erkennung in Anki
        if raw_cid in anki_index:
            if raw_cid not in anki_dupes:
                anki_dupes[raw_cid] = [anki_index[raw_cid]["noteId"]]
            anki_dupes[raw_cid].append(note["noteId"])
        else:
            anki_index[raw_cid] = note

    # 5. (Forts.) Duplikate in Anki → blockierender Fehler, kein Auto-Delete
    if anki_dupes:
        for cid, note_ids in sorted(anki_dupes.items(), key=lambda kv: int(kv[0])):
            ids_str = ", ".join(str(nid) for nid in note_ids)
            plan.blocking_errors.append(
                f"Doppelte CardId '{cid}' in Anki (Notiz-IDs: {ids_str}). "
                "Bitte Duplikate manuell in Anki bereinigen."
            )
        return plan

    # 6. Stale-file-Warnung
    if max_anki_id > max_json_id:
        msg = (
            f"WARNUNG: cards.json ist möglicherweise veraltet – "
            f"höchste CardId in Anki: {max_anki_id}, "
            f"in cards.json: {max_json_id}. "
            "Ggf. zuerst 'Export nach cards.json' ausführen."
        )
        plan.warnings.append(msg)
        plan.has_stale_warning = True

    # 8./9. JSON-Karten mit Anki-Notizen abgleichen
    for card in validated_cards:
        card_id = card[CARD_ID_FIELD]

        if card_id not in anki_index:
            if card_id in outside_deck_notes:
                plan.blocking_errors.append(
                    f"CardId {card_id} existiert bereits außerhalb des Decks '{DECK_NAME}' "
                    f"(Notiz {outside_deck_notes[card_id]}). Bitte die Karte in Anki "
                    f"zurückverschieben oder aus cards.json entfernen."
                )
            else:
                missing = [name for name in ("German", "English") if not card.get(name)]
                if missing:
                    plan.blocking_errors.append(
                        f"CardId {card_id}: Neue Karten benötigen {', '.join(missing)}."
                    )
                else:
                    plan.to_add.append(AddEntry(card=card))
            continue

        note = anki_index[card_id]
        anki_tags = note.get("tags", [])
        anki_fields = note.get("fields", {})

        # Feldvergleich (exakter String-Vergleich nach strip())
        changed = []
        for fname in ALL_FIELDS:
            if fname not in card:
                continue
            anki_val = anki_fields.get(fname, {}).get("value", "").strip()
            json_val = card.get(fname, "").strip()
            if anki_val != json_val:
                changed.append(fname)

        # Tag-Vergleich: nur nicht-geschützte Tags, case-insensitiv
        anki_non_protected = [t for t in anki_tags if not is_protected_tag(t)]
        json_tags_card = card["tags"]
        if {t.lower() for t in anki_non_protected} != {t.lower() for t in json_tags_card}:
            changed.append("tags")

        if changed:
            new_fields = {fname: card[fname] for fname in ALL_FIELDS if fname in card}
            plan.to_update.append(
                UpdateEntry(
                    note_id=note["noteId"],
                    card_id=card_id,
                    changed_fields=changed,
                    new_fields=new_fields,
                    new_tags=json_tags_card,
                    anki_tags=anki_tags,
                )
            )
        else:
            plan.unchanged_count += 1

    # 10. Zu löschende Notizen: in Anki vorhanden, aber nicht in JSON
    seen_delete_ids: set = set()
    for card_id, note in anki_index.items():
        if card_id not in json_card_ids:
            note_id = note["noteId"]
            if note_id not in seen_delete_ids:
                seen_delete_ids.add(note_id)
                german = note["fields"].get("German", {}).get("value", "").strip()
                plan.to_delete.append(
                    DeleteEntry(note_id=note_id, card_id=card_id, german=german)
                )

    return plan


# ---------------------------------------------------------------------------
# Anwendungsphase
# ---------------------------------------------------------------------------


def _apply_tag_sync(note_id: int, anki_tags: List[str], new_tags: List[str]) -> None:
    """Synchronisiert nicht-geschützte Tags einer Notiz.

    Geschützte Tags (leech, marked) werden niemals angefasst.
    """
    anki_np = {t.lower(): t for t in anki_tags if not is_protected_tag(t)}
    new_np = {t.lower(): t for t in new_tags}

    to_add = [new_np[k] for k in new_np if k not in anki_np]
    to_remove = [anki_np[k] for k in anki_np if k not in new_np]

    if to_add:
        invoke_anki("addTags", {"notes": [note_id], "tags": " ".join(sorted(to_add))})
    if to_remove:
        invoke_anki(
            "removeTags", {"notes": [note_id], "tags": " ".join(sorted(to_remove))}
        )


def apply_sync(plan: SyncPlan) -> None:
    """Führt den SyncPlan aus.

    Reihenfolge: Hinzufügen → Aktualisieren → Verifizieren → Löschen.
    Löschen wird vollständig übersprungen, wenn beim Hinzufügen oder
    Aktualisieren Fehler aufgetreten sind.
    """
    if plan.blocking_errors:
        raise RuntimeError(
            "Sync wurde nicht ausgeführt – blockierende Fehler:\n"
            + "\n".join(plan.blocking_errors)
        )

    added = 0
    updated = 0
    error_count = 0
    verify_errors = 0
    updated_entries: List[UpdateEntry] = []

    # --- Hinzufügen ---
    for entry in plan.to_add:
        card = entry.card
        note = {
            "deckName": DECK_NAME,
            "modelName": MODEL_NAME,
            "fields": {fname: card.get(fname, "") for fname in ALL_FIELDS},
            "tags": card["tags"],
            "options": {"allowDuplicate": True},
        }
        try:
            result = invoke_anki("addNote", {"note": note})
            if result is None:
                raise RuntimeError("AnkiConnect hat keine Notiz-ID zurückgegeben.")
            added += 1
        except Exception as exc:
            error_count += 1
            print(
                f"Fehler beim Hinzufügen "
                f"(CardId {card[CARD_ID_FIELD]}, German: {card['German']!r}): {exc}"
            )

    # --- Aktualisieren ---
    for entry in plan.to_update:
        try:
            invoke_anki(
                "updateNoteFields",
                {"note": {"id": entry.note_id, "fields": entry.new_fields}},
            )
            _apply_tag_sync(entry.note_id, entry.anki_tags, entry.new_tags)
            updated += 1
            updated_entries.append(entry)
        except Exception as exc:
            error_count += 1
            print(
                f"Fehler beim Aktualisieren "
                f"(CardId {entry.card_id}, Notiz {entry.note_id}): {exc}"
            )

    # --- Verifizieren (Schutz gegen 'Notiz im Browse-Fenster geöffnet') ---
    if updated_entries:
        try:
            verified = notes_info_by_ids([e.note_id for e in updated_entries])
            verified_map = {n["noteId"]: n for n in verified}

            for entry in updated_entries:
                note = verified_map.get(entry.note_id)
                if note is None:
                    continue
                saved = note.get("fields", {})
                for fname in entry.new_fields:
                    actual = saved.get(fname, {}).get("value", "").strip()
                    expected = entry.new_fields.get(fname, "").strip()
                    if actual != expected:
                        verify_errors += 1
                        print(
                            f"Notiz {entry.card_id} wurde nicht gespeichert – "
                            "ist sie im Anki-Browser geöffnet? "
                            "Browser schließen und erneut synchronisieren."
                        )
                        break  # Eine Meldung pro Notiz
        except Exception as exc:
            print(f"Warnung: Verifikation der Aktualisierungen fehlgeschlagen: {exc}")

    # --- Löschen (nur wenn keine Add-/Update-Fehler) ---
    deleted = 0
    if error_count > 0 or verify_errors > 0:
        if plan.to_delete:
            reason = "Fehler beim Hinzufügen/Aktualisieren aufgetreten sind"
            if verify_errors > 0 and error_count == 0:
                reason = "das Speichern (Verifikation) fehlgeschlagen ist"
            print(
                f"Löschen übersprungen ({len(plan.to_delete)} Notiz(en)), "
                f"da {reason}."
            )
    else:
        ids_to_delete = [e.note_id for e in plan.to_delete]
        if ids_to_delete:
            try:
                invoke_anki("deleteNotes", {"notes": ids_to_delete})
                deleted = len(ids_to_delete)
            except Exception as exc:
                error_count += 1
                print(f"Fehler beim Löschen: {exc}")

    # --- Zusammenfassung ---
    print(f"Hinzugefügt:  {added}")
    print(f"Aktualisiert: {updated}")
    print(f"Unverändert:  {plan.unchanged_count}")
    print(f"Gelöscht:     {deleted}")
    total_errors = error_count + verify_errors
    if total_errors:
        print(f"Fehler:       {total_errors}")


# ---------------------------------------------------------------------------
# Plan-Zusammenfassung (für CLI und GUI-Statusbox)
# ---------------------------------------------------------------------------


def print_plan_summary(plan: SyncPlan) -> None:
    """Gibt eine lesbare Zusammenfassung des SyncPlans auf stdout aus."""
    for w in plan.warnings:
        print(w)

    if plan.blocking_errors:
        print("Sync blockiert – folgende Fehler müssen behoben werden:")
        for err in plan.blocking_errors:
            print(f"  \u2022 {err}")
        return

    nothing = not plan.to_add and not plan.to_update and not plan.to_delete
    if nothing:
        print("Keine Änderungen.")
        return

    if plan.to_add:
        print(f"Neu hinzuzufügen:  {len(plan.to_add)}")
        for e in plan.to_add:
            print(f"  + {e.card[CARD_ID_FIELD]}: {e.card['German']}")

    if plan.to_update:
        print(f"Zu aktualisieren:  {len(plan.to_update)}")
        for e in plan.to_update:
            print(f"  \u007e {e.card_id}: geändert: {', '.join(e.changed_fields)}")

    if plan.unchanged_count:
        print(f"Unverändert:       {plan.unchanged_count}")

    if plan.to_delete:
        print(f"Zu löschen:        {len(plan.to_delete)}")
        for e in plan.to_delete:
            print(f"  - {e.card_id}: {e.german}")


# ---------------------------------------------------------------------------
# CLI-Einstiegspunkt
# ---------------------------------------------------------------------------


def sync_cards() -> None:
    """CLI-Einstiegspunkt: plant, zeigt Plan, fragt bei Löschungen nach."""
    plan = plan_sync()
    print_plan_summary(plan)

    if plan.blocking_errors:
        return

    nothing = not plan.to_add and not plan.to_update and not plan.to_delete
    if nothing:
        return  # "Keine Änderungen." wurde bereits gedruckt

    if plan.to_delete:
        print(
            f"\nACHTUNG: Der Sync würde {len(plan.to_delete)} Notiz(en) in Anki LÖSCHEN."
        )
        antwort = input("Wirklich fortfahren? Nur 'ja' bestätigt: ").strip().lower()
        if antwort != "ja":
            print("Abgebrochen – nichts gelöscht.")
            # Weiter mit Adds/Updates, aber ohne Löschungen
            plan = dataclasses.replace(plan, to_delete=[])
            if not plan.to_add and not plan.to_update:
                return

    apply_sync(plan)


def main() -> None:
    try:
        sync_cards()
    except requests.RequestException as exc:
        print(f"Verbindung zu AnkiConnect fehlgeschlagen: {exc}")
    except Exception as exc:
        print(f"Fehler: {exc}")


if __name__ == "__main__":
    main()

"""Sichert und erweitert den Notiztyp, ohne Notizen oder Lernstände zu ändern."""

import json
from datetime import datetime

from anki_client import invoke_anki, preflight_check
from card_fields import NEW_FIELDS
from card_template import BACK_HTML, CSS, FRONT_HTML
from config import BACKUP_DIR, MODEL_NAME

FULL_SYNC_REMINDER = (
    "Jetzt auf diesem Gerät in Anki synchronisieren und 'Zu AnkiWeb hochladen' wählen. "
    "Danach auf den anderen Geräten synchronisieren und bei Nachfrage "
    "'Von AnkiWeb herunterladen' wählen."
)


def setup_note_type(confirm_callback):
    preflight_check(mode="setup")
    params = {"modelName": MODEL_NAME}
    fields = invoke_anki("modelFieldNames", params)
    templates = invoke_anki("modelTemplates", params)
    styling = invoke_anki("modelStyling", params)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"notetype_backup_{timestamp}.json"
    # Exklusives Erstellen verhindert, dass ein früheres Backup überschrieben wird.
    try:
        with backup_path.open("x", encoding="utf-8") as backup:
            json.dump({"modelName": MODEL_NAME, "fieldNames": fields,
                       "templates": templates, "css": styling["css"]},
                      backup, ensure_ascii=False, indent=2)
    except OSError as exc:
        raise RuntimeError(
            f"Sicherung konnte nicht erstellt werden: {backup_path}. "
            "Es wurde nichts geändert. Bitte erneut versuchen."
        ) from exc
    print(f"Sicherung des Notiztyps: {backup_path}")
    if len(templates) != 1:
        raise RuntimeError(
            "Der Notiztyp muss genau eine Kartenvorlage enthalten. "
            f"Gefunden: {len(templates)}. Es wurde nichts geändert."
        )

    missing = [name for name in NEW_FIELDS if name not in fields]
    if missing:
        message = (
            f"Es werden neue Felder hinzugefügt: {', '.join(missing)}. "
            "Danach verlangt Anki beim nächsten Synchronisieren einen vollständigen Abgleich.\n"
            "Vorher MUSS auf allen anderen Geräten (iPhone, anderer PC) in Anki synchronisiert "
            "worden sein, sonst gehen dort ungesyncte Wiederholungen verloren.\n"
            "Danach auf diesem Gerät in Anki synchronisieren und 'Zu AnkiWeb hochladen' wählen. Fortfahren?"
        )
        if not confirm_callback(message):
            print("Abgebrochen – der Notiztyp wurde nicht geändert.")
            return

    added = []
    try:
        for name in missing:
            try:
                invoke_anki("modelFieldAdd", {"modelName": MODEL_NAME, "fieldName": name})
            except RuntimeError as exc:
                if "unsupported action" in str(exc).lower() or "unknown action" in str(exc).lower():
                    raise RuntimeError(
                        "Felder konnten nicht hinzugefügt werden. Bitte AnkiConnect aktualisieren "
                        "(modelFieldAdd wird nicht unterstützt)."
                    ) from exc
                raise
            added.append(name)
        template_name = next(iter(templates))
        desired = {template_name: {"Front": FRONT_HTML, "Back": BACK_HTML}}
        invoke_anki("updateModelTemplates", {"model": {"name": MODEL_NAME, "templates": desired}})
        invoke_anki("updateModelStyling", {"model": {"name": MODEL_NAME, "css": CSS}})
        actual_fields = invoke_anki("modelFieldNames", params)
        actual_templates = invoke_anki("modelTemplates", params)
        actual_css = invoke_anki("modelStyling", params)
        if actual_fields != fields + missing or actual_templates != desired or actual_css["css"] != CSS:
            raise RuntimeError("Die Prüfung des gespeicherten Kartenlayouts ist fehlgeschlagen.")
    except Exception:
        print(f"Einrichtung fehlgeschlagen. Mögliche Teiländerungen prüfen; Sicherung: {backup_path}")
        raise
    finally:
        if added:
            print("Vollständiger Abgleich erforderlich: " + FULL_SYNC_REMINDER)

    print("Felder hinzugefügt: " + (", ".join(added) or "keine"))
    print(f"Kartenvorlage '{template_name}' und CSS aktualisiert und geprüft.")
    print(f"Backup: {backup_path}")

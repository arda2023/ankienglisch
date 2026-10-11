"""Gemeinsame Felddefinitionen und Prüfung der unveränderten Textmarker."""

import re

BASE_FIELDS = ["CardId", "German", "English", "Alternative1", "Alternative2"]
NEW_FIELDS = ["Hint", "Trap", "Pattern", "Transfer1", "Transfer2", "Rule"]
ALL_FIELDS = BASE_FIELDS + NEW_FIELDS
JSON_KEY_ORDER = [
    "CardId", "German", "Hint", "English", "Trap", "Pattern",
    "Transfer1", "Transfer2", "Rule", "Alternative1", "Alternative2", "tags",
]


def validate_markers(text):
    """Prüft doppelte Klammern; einzelne Klammern bleiben Platzhalter."""
    start = None
    for match in re.finditer(r"\[\[|\]\]", text):
        if match.group() == "[[":
            if start is not None:
                raise ValueError("Verschachtelte [[…]]-Marker sind nicht erlaubt.")
            start = match.end()
        else:
            if start is None:
                raise ValueError("Zu ]] fehlt der öffnende [[-Marker.")
            if not text[start:match.start()].strip():
                raise ValueError("Leere [[…]]-Marker sind nicht erlaubt.")
            start = None
    if start is not None:
        raise ValueError("Zu [[ fehlt der schließende ]]-Marker.")

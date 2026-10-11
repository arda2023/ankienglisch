"""Regressionstests ohne Zugriff auf Anki oder die echte cards.json."""
import contextlib
import copy
import importlib
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch

# config.py hat Dateisystem-Seiteneffekte; im Test ausschließlich temporäre Daten.
_modules = {}
with tempfile.TemporaryDirectory() as folder:
    config = types.ModuleType("config")
    for key, value in dict(BACKUP_DIR=Path(folder), CARDS_FILE=Path(folder)/"cards.json",
                           DATA_DIR=Path(folder), DECK_NAME="Englisch", MODEL_NAME="English Active Speaking",
                           EXPECTED_PROFILE=None, MAX_AUTO_DELETE=3, ANKI_CONNECT_URL="http://localhost:8765").items():
        setattr(config, key, value)
    with patch.dict(sys.modules, {"config": config}):
        for name in ("card_fields", "card_template", "anki_client", "cards_file", "import_cards",
                     "export_cards", "sync_cards", "setup_note_type", "main"):
            _modules[name] = importlib.import_module(name)

fields = _modules["card_fields"]
imp = _modules["import_cards"]
exp = _modules["export_cards"]
sync = _modules["sync_cards"]
setup = _modules["setup_note_type"]
client = _modules["anki_client"]
gui = _modules["main"]


def note(card=None):
    values = {name: "" for name in fields.ALL_FIELDS}
    values.update(CardId="1", German="Hallo", English="Hello", Hint="Behalten", Pattern="[[Hello]]")
    values.update(card or {})
    return {"noteId": 42, "fields": {k: {"value": v} for k, v in values.items()},
            "tags": ["leech", "marked"]}


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.output.__exit__(None, None, None)

    def test_markers(self):
        for good in ("", "[people] + [[who]]", "[[one]] [[two]]", "[[a\nb]]"):
            fields.validate_markers(good)
        for bad in ("[[", "]]", "[[]]", "[[ ]]", "[[a [[b]] c]]", "[[a]] ]]"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fields.validate_markers(bad)

    def test_import_validates_all_cards_and_warns(self):
        with self.assertRaises(ValueError) as error:
            imp.validate_cards([{"German": "[[", "English": "hi"}, {"German": "hi", "Hint": "[[]]", "English": "hi"}])
        self.assertIn("Karte 1", str(error.exception))
        self.assertIn("Karte 2", str(error.exception))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            card = imp.validate_cards([{"German": "Hallo", "English": "Hello", "Pattern": "[x]", "Hint": "a"*61, "Rule": "b"*161}])[0]
        self.assertEqual(output.getvalue().count("Warnung: Karte 1:"), 3)
        self.assertEqual(card["Transfer1"], "")

    def test_import_export_roundtrip_and_order(self):
        raw = {name: "[[Inhalt]]" for name in fields.ALL_FIELDS if name != "CardId"}
        saved = []
        calls = []
        with patch.multiple(imp, preflight_check=Mock(), load_cards_from_clipboard=Mock(return_value=[raw]),
                            build_existing_german_keys=Mock(return_value=set()), get_highest_card_id_in_anki=Mock(return_value=0),
                            get_highest_card_id_in_file=Mock(return_value=0), load_cards=Mock(return_value=[]),
                            save_cards=Mock(side_effect=lambda cards: saved.extend(cards)),
                            invoke_anki=Mock(side_effect=lambda a,p: calls.append((a,p)) or 42)):
            imp.import_cards()
        self.assertEqual(list(saved[0]), fields.JSON_KEY_ORDER)
        imported = calls[0][1]["note"]["fields"]
        self.assertEqual(set(imported), set(fields.ALL_FIELDS))
        self.assertEqual(exp.build_card(note(imported)), saved[0])
        old = note()
        old["fields"] = {k:v for k,v in old["fields"].items() if k in fields.BASE_FIELDS}
        self.assertEqual(set(exp.build_card(old)), set(fields.BASE_FIELDS + ["tags"]))

    def plan(self, cards, current=None):
        current = current or note()
        with patch.multiple(sync, preflight_check=Mock(), load_cards=Mock(return_value=cards),
                            find_notes_info=Mock(return_value=[current])):
            return sync.plan_sync()

    def test_missing_fields_preserved_and_present_empty_clears(self):
        plan = self.plan([{"CardId": "1", "English": "[[Hi]]", "Hint": ""}])
        self.assertFalse(plan.blocking_errors)
        entry = plan.to_update[0]
        self.assertEqual(entry.new_fields, {"CardId": "1", "English": "[[Hi]]", "Hint": ""})
        calls = []
        with patch.object(sync, "invoke_anki", side_effect=lambda a,p: calls.append((a,p))), \
             patch.object(sync, "notes_info_by_ids", return_value=[note(entry.new_fields)]):
            sync.apply_sync(plan)
        payload = calls[0][1]["note"]["fields"]
        self.assertNotIn("Pattern", payload)
        self.assertNotIn("German", payload)
        self.assertFalse(any(a in ("removeTags", "deleteNotes") for a,p in calls))

    def test_explicit_empty_text_fields_are_updates(self):
        plan = self.plan([{"CardId": "1", "English": "", "German": ""}])
        self.assertFalse(plan.blocking_errors)
        self.assertEqual(plan.to_update[0].new_fields, {"CardId": "1", "German": "", "English": ""})

    def test_old_file_leaves_new_fields_unchanged(self):
        card = {k:v["value"] for k,v in note()["fields"].items() if k in fields.BASE_FIELDS}
        plan = self.plan([card])
        self.assertEqual(plan.unchanged_count, 1)
        self.assertFalse(plan.to_update)

    def test_invalid_sync_blocks_everything(self):
        plan = self.plan([{"CardId": "1", "Rule": "[[bad"}])
        self.assertTrue(plan.blocking_errors)
        self.assertFalse(plan.to_add or plan.to_update or plan.to_delete)
        with self.assertRaises(RuntimeError):
            sync.apply_sync(plan)
        self.assertTrue(self.plan([{"CardId": "2"}]).blocking_errors)

    def test_preflight_modes(self):
        def invoke(action, params=None):
            return {"version": 6, "deckNames": ["Englisch"], "modelNames": [setup.MODEL_NAME],
                    "modelFieldNames": fields.BASE_FIELDS}[action]
        with patch.object(client, "invoke_anki", side_effect=invoke):
            with self.assertRaisesRegex(RuntimeError, "Kartenlayout einrichten"):
                client.preflight_check()
            self.assertEqual(client.preflight_check("export"), fields.BASE_FIELDS)
            self.assertEqual(client.preflight_check("setup"), fields.BASE_FIELDS)

    def run_setup(self, confirmed=True, extra_template=False, complete=False, unsupported=False):
        state = {"fields": list(fields.ALL_FIELDS if complete else fields.BASE_FIELDS),
                 "templates": {"Karte 1": {"Front": "alt", "Back": "alt"}}, "css": "alt"}
        if extra_template:
            state["templates"]["Karte 2"] = {"Front": "alt", "Back": "alt"}
        original = copy.deepcopy(state)
        calls = []
        def invoke(action, params):
            calls.append((action, params))
            if action == "modelFieldNames": return list(state["fields"])
            if action == "modelTemplates": return copy.deepcopy(state["templates"])
            if action == "modelStyling": return {"css": state["css"]}
            if action == "modelFieldAdd":
                self.assertNotIn("index", params)
                if unsupported: raise RuntimeError("unsupported action")
                state["fields"].append(params["fieldName"])
            elif action == "updateModelTemplates": state["templates"] = params["model"]["templates"]
            elif action == "updateModelStyling": state["css"] = params["model"]["css"]
            else: self.fail("Unerlaubte Aktion: " + action)
        confirmation = Mock(return_value=confirmed)
        with tempfile.TemporaryDirectory() as folder, patch.object(setup, "BACKUP_DIR", Path(folder)), \
             patch.object(setup, "preflight_check"), patch.object(setup, "invoke_anki", side_effect=invoke):
            if extra_template or unsupported:
                with self.assertRaisesRegex(RuntimeError, "genau eine|AnkiConnect aktualisieren"):
                    setup.setup_note_type(confirmation)
            else:
                setup.setup_note_type(confirmation)
            backup = json.loads(next(Path(folder).glob("*.json")).read_text())
        self.assertEqual(backup["fieldNames"], original["fields"])
        self.assertEqual(backup["templates"], original["templates"])
        if not confirmed or extra_template or unsupported:
            self.assertEqual(state, original)
        else:
            self.assertEqual(state["fields"], fields.ALL_FIELDS)
            self.assertEqual(state["css"], setup.CSS)
        if complete or extra_template: confirmation.assert_not_called()
        return calls

    def test_setup_cancel(self): self.run_setup(confirmed=False)
    def test_setup_success(self): self.run_setup()
    def test_setup_existing_fields(self): self.run_setup(complete=True)
    def test_setup_multiple_templates(self): self.run_setup(extra_template=True)
    def test_setup_unsupported_action(self): self.run_setup(unsupported=True)

    def test_confirmation_main_thread_and_dialog_failure_releases_worker(self):
        for raises in (False, True):
            app = types.SimpleNamespace(queue=queue.Queue())
            result = []
            def worker():
                try: result.append(gui.AnkiEnglishManagerApp._confirm_layout(app, "Frage"))
                except RuntimeError: result.append("Fehler")
            thread = threading.Thread(target=worker)
            thread.start()
            task = app.queue.get(timeout=2)
            def ask(*args, **kwargs):
                self.assertEqual(threading.current_thread(), threading.main_thread())
                self.assertEqual(kwargs["default"], gui.tkinter.messagebox.NO)
                if raises: raise RuntimeError("Dialogfehler")
                return False
            with patch.object(gui.tkinter.messagebox, "askyesno", side_effect=ask): task()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result, ["Fehler" if raises else False])


if __name__ == "__main__":
    unittest.main()

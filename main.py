import contextlib
import io
import os
import queue
import sys
import threading
import tkinter
import tkinter.messagebox
import traceback

if sys.platform == "darwin":
    os.environ.setdefault("LANG", "en_US.UTF-8")

import customtkinter as ctk
import pyperclip
import requests

from platform_utils import open_path


# ---------------------------------------------------------------------------
# Modulimporte – Fehler hier erzeugen kein Konsolenfenster in der EXE
# ---------------------------------------------------------------------------

try:
    import export_cards as export_cards_module
    import import_cards as import_cards_module
    import sync_cards as sync_cards_module

    from config import CARDS_FILE, MAX_AUTO_DELETE, DATA_DIR
except Exception as _startup_exc:  # noqa: BLE001
    _root = tkinter.Tk()
    _root.withdraw()
    tkinter.messagebox.showerror(
        "Anki English Manager",
        f"Die App konnte nicht gestartet werden:\n\n{_startup_exc}\n\n"
        "Bitte config.json prüfen oder löschen (wird dann neu erstellt).",
    )
    raise SystemExit(1) from _startup_exc


class AnkiEnglishManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Anki English Manager")
        self.geometry("760x520")
        self.minsize(640, 420)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        self.button_frame.grid_columnconfigure((0, 1), weight=1)

        self.buttons = []
        self.add_button("Import aus Zwischenablage", self.import_from_clipboard, 0, 0)
        self.add_button("Export nach cards.json", self.export_to_json, 0, 1)
        self.add_button(
            "Export & JSON in Zwischenablage kopieren",
            self.export_and_copy_json,
            1,
            0,
        )
        self.add_button("Synchronisieren", self.sync_cards, 1, 1)
        self.add_button("cards.json öffnen", self.open_cards_json, 2, 0)
        self.add_button("Datenordner öffnen", self.open_data_folder, 2, 1)

        self.status_box = ctk.CTkTextbox(self, wrap="word")
        self.status_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        
        self.queue = queue.Queue()
        self.after(100, self._process_queue)
        
        self.status_box.insert("end", f"Datenordner: {DATA_DIR}\nBereit.\n")
        self.status_box.configure(state="disabled")

    def _process_queue(self):
        while not self.queue.empty():
            try:
                task = self.queue.get_nowait()
                task()
            except queue.Empty:
                break
        self.after(100, self._process_queue)

    def add_button(self, text, command, row, column):
        button = ctk.CTkButton(self.button_frame, text=text, command=command)
        button.grid(row=row, column=column, sticky="ew", padx=6, pady=6)
        self.buttons.append(button)

    def append_status(self, text):
        self.status_box.configure(state="normal")
        self.status_box.insert("end", text)
        self.status_box.see("end")
        self.status_box.configure(state="disabled")

    def set_buttons_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for button in self.buttons:
            button.configure(state=state)

    def run_task(self, title, task):
        self.set_buttons_enabled(False)
        self.append_status(f"\n--- {title} ---\n")

        def worker():
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    task()
            except (RuntimeError, ValueError, FileNotFoundError, requests.RequestException) as exc:
                print(f"Fehler: {exc}", file=output)
            except Exception:
                traceback.print_exc(file=output)

            text = output.getvalue()
            if not text.strip():
                text = "Fertig.\n"

            self.queue.put(lambda text=text: self.finish_task(text))

        threading.Thread(target=worker, daemon=True).start()

    def finish_task(self, text):
        self.append_status(text)
        if not text.endswith("\n"):
            self.append_status("\n")
        self.set_buttons_enabled(True)

    # ------------------------------------------------------------------
    # Aktionen
    # ------------------------------------------------------------------

    def import_from_clipboard(self):
        self.run_task("Import aus Zwischenablage", import_cards_module.import_cards)

    def export_to_json(self):
        self.run_task("Export nach cards.json", export_cards_module.export_cards)

    def export_and_copy_json(self):
        def task():
            export_cards_module.export_cards()
            pyperclip.copy(CARDS_FILE.read_text(encoding="utf-8"))
            print("cards.json wurde in die Zwischenablage kopiert.")

        self.run_task("Export & JSON kopieren", task)

    # ------------------------------------------------------------------
    # Synchronisieren — zwei Phasen (Plan + Anwendung)
    # ------------------------------------------------------------------

    def sync_cards(self):
        """Startet Phase 1: plan_sync() im Worker-Thread."""
        self.set_buttons_enabled(False)
        self.append_status("\n--- Synchronisieren ---\n")

        def phase1_worker():
            output = io.StringIO()
            plan = None
            try:
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    plan = sync_cards_module.plan_sync()
                    sync_cards_module.print_plan_summary(plan)
            except (
                RuntimeError,
                ValueError,
                FileNotFoundError,
                requests.RequestException,
            ) as exc:
                print(f"Fehler: {exc}", file=output)
            except Exception:
                traceback.print_exc(file=output)

            captured_plan = plan
            captured_text = output.getvalue()
            self.queue.put(lambda cp=captured_plan, ct=captured_text: self._on_plan_ready(cp, ct))

        threading.Thread(target=phase1_worker, daemon=True).start()

    def _on_plan_ready(self, plan, plan_text):
        """Läuft auf dem Haupt-Thread nach Phase 1.

        Zeigt den Plan an, entscheidet ob ein Bestätigungsdialog nötig ist
        und startet ggf. Phase 2 (apply_sync).
        """
        # Planausgabe in Statusbox anzeigen
        if plan_text:
            self.append_status(plan_text)
            if not plan_text.endswith("\n"):
                self.append_status("\n")

        # Fehler während der Planung → sofort abbrechen
        if plan is None:
            self.set_buttons_enabled(True)
            return

        # Blockierende Fehler (ungültige cards.json, Duplikate in Anki…)
        if plan.blocking_errors:
            self.set_buttons_enabled(True)
            return

        # Nichts zu tun
        nothing = not plan.to_add and not plan.to_update and not plan.to_delete
        if nothing:
            self.set_buttons_enabled(True)
            return

        # Keine Löschungen → direkt anwenden
        if not plan.to_delete:
            self._run_apply(plan)
            return

        # Löschungen vorhanden → Bestätigungsdialog
        lines = []

        # Zusätzliche Warnung wenn Limit überschritten oder Datei veraltet
        if len(plan.to_delete) > MAX_AUTO_DELETE or plan.has_stale_warning:
            if plan.has_stale_warning:
                lines.append(
                    "WARNUNG: cards.json ist möglicherweise veraltet!"
                )
                lines.append(
                    "Bitte zuerst 'Export nach cards.json' ausführen."
                )
            if len(plan.to_delete) > MAX_AUTO_DELETE:
                lines.append(
                    f"WARNUNG: Es sollen {len(plan.to_delete)} Notizen gelöscht"
                    f" werden (konfiguriertes Limit: {MAX_AUTO_DELETE})."
                )
            lines.append("")

        lines.append(
            f"Folgende {len(plan.to_delete)} Notiz(en) werden aus Anki"
            " unwiderruflich gelöscht:"
        )
        max_shown = 15
        for entry in plan.to_delete[:max_shown]:
            german_display = (
                entry.german[:60] + "\u2026"
                if len(entry.german) > 60
                else entry.german
            )
            lines.append(f"  CardId {entry.card_id} \u2013 {german_display}")
        remaining = len(plan.to_delete) - max_shown
        if remaining > 0:
            lines.append(f"  \u2026und {remaining} weitere")
        lines.append("")
        lines.append("Wirklich fortfahren?")

        confirmed = tkinter.messagebox.askyesno(
            "Synchronisieren \u2013 Löschen bestätigen",
            "\n".join(lines),
            default=tkinter.messagebox.NO,
        )

        if not confirmed:
            self.append_status("Abgebrochen \u2013 nichts gelöscht.\n")
            self.set_buttons_enabled(True)
            return

        self._run_apply(plan)

    def _run_apply(self, plan):
        """Startet Phase 2: apply_sync() im Worker-Thread."""

        def worker():
            output = io.StringIO()
            try:
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    sync_cards_module.apply_sync(plan)
            except (
                RuntimeError,
                ValueError,
                FileNotFoundError,
                requests.RequestException,
            ) as exc:
                print(f"Fehler: {exc}", file=output)
            except Exception:
                traceback.print_exc(file=output)

            text = output.getvalue()
            if not text.strip():
                text = "Fertig.\n"
            self.queue.put(lambda text=text: self.finish_task(text))

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Hilfsfunktionen
    # ------------------------------------------------------------------

    def open_cards_json(self):
        if not CARDS_FILE.exists():
            self.append_status("\ncards.json wurde nicht gefunden.\n")
            return
        try:
            open_path(CARDS_FILE)
            self.append_status("\ncards.json geöffnet.\n")
        except Exception as exc:
            self.append_status(f"\nFehler beim Öffnen: {exc}\n")

    def open_data_folder(self):
        try:
            open_path(DATA_DIR)
            self.append_status("\nDatenordner geöffnet.\n")
        except Exception as exc:
            self.append_status(f"\nFehler beim Öffnen: {exc}\n")


if __name__ == "__main__":
    app = AnkiEnglishManagerApp()
    app.mainloop()

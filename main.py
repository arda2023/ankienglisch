import contextlib
import io
import os
import sys
import threading
import traceback
from pathlib import Path

import customtkinter as ctk
import pyperclip
import requests

import export_cards as export_cards_module
import import_cards as import_cards_module
import sync_cards as sync_cards_module


if getattr(sys, "frozen", False):
    PROJECT_DIR = Path(sys.executable).resolve().parent
else:
    PROJECT_DIR = Path(__file__).resolve().parent

CARDS_FILE = PROJECT_DIR / "cards.json"
export_cards_module.OUTPUT_FILE = CARDS_FILE
sync_cards_module.CARDS_FILE = CARDS_FILE


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
        self.add_button("Projektordner öffnen", self.open_project_folder, 2, 1)

        self.status_box = ctk.CTkTextbox(self, wrap="word")
        self.status_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.status_box.insert("end", "Bereit.\n")
        self.status_box.configure(state="disabled")

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
            except requests.RequestException as exc:
                print(f"Verbindung zu AnkiConnect fehlgeschlagen: {exc}", file=output)
            except Exception as exc:
                print(f"Fehler: {exc}", file=output)
                traceback.print_exc(file=output)

            text = output.getvalue()
            if not text.strip():
                text = "Fertig.\n"

            self.after(0, lambda: self.finish_task(text))

        threading.Thread(target=worker, daemon=True).start()

    def finish_task(self, text):
        self.append_status(text)
        if not text.endswith("\n"):
            self.append_status("\n")
        self.set_buttons_enabled(True)

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

    def sync_cards(self):
        self.run_task("Synchronisieren", sync_cards_module.sync_cards)

    def open_cards_json(self):
        if not CARDS_FILE.exists():
            self.append_status("\ncards.json wurde nicht gefunden.\n")
            return
        os.startfile(CARDS_FILE)
        self.append_status("\ncards.json geöffnet.\n")

    def open_project_folder(self):
        os.startfile(PROJECT_DIR)
        self.append_status("\nProjektordner geöffnet.\n")


if __name__ == "__main__":
    app = AnkiEnglishManagerApp()
    app.mainloop()

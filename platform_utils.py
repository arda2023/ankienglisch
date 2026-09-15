import os
import subprocess
import sys

def open_path(path):
    """
    Öffnet eine Datei oder ein Verzeichnis mit der Standard-App des Betriebssystems.
    Unter macOS werden .json Dateien explizit mit dem Standard-Texteditor geöffnet.
    Wirft einen RuntimeError mit deutscher Fehlermeldung bei Fehlschlag.
    """
    path_str = str(path)
    try:
        if sys.platform == "win32":
            os.startfile(path_str)
        elif sys.platform == "darwin":
            if path_str.lower().endswith(".json"):
                subprocess.run(["open", "-t", path_str], check=True)
            else:
                subprocess.run(["open", path_str], check=True)
        else:
            subprocess.run(["xdg-open", path_str], check=True)
    except Exception as exc:
        raise RuntimeError(f"Fehler beim Öffnen von '{path_str}': {exc}") from exc

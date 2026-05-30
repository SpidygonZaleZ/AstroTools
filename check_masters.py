import os
import tkinter as tk
from tkinter import filedialog

def choose_base_dir():
    root = tk.Tk()
    root.withdraw()          # nie pokazuj głównego okna
    root.attributes("-topmost", True)

    folder = filedialog.askdirectory(
        title="Wybierz katalog bazowy z danymi"
    )

    root.destroy()
    return folder

def check_masters_once(base_dir):
    if not os.path.isdir(base_dir):
        print(f"❌ Folder nie istnieje: {base_dir}")
        return

    print(f"🔍 Sprawdzam podfoldery w: {base_dir}\n")

    # Sprawdź tylko jeden poziom podfolderów
    subfolders = [os.path.join(base_dir, d) for d in os.listdir(base_dir)
                  if os.path.isdir(os.path.join(base_dir, d))]

    if not subfolders:
        print("⚠️ Brak podfolderów do sprawdzenia.")
        return

    for sub in subfolders:
        masters_path = os.path.join(sub, "masters")

        if not os.path.isdir(masters_path):
            print(f"📁 {os.path.basename(sub)} → brak folderu 'masters'")
            continue

        # Szukaj plików Dark* i Flat*
        files = os.listdir(masters_path)
        dark_files = [f for f in files if os.path.isfile(os.path.join(masters_path, f)) and f.lower().startswith("dark")]
        flat_files = [f for f in files if os.path.isfile(os.path.join(masters_path, f)) and f.lower().startswith("flat")]

        # Sprawdzenia warunków
        error_msgs = []
        if len(dark_files) == 0:
            error_msgs.append("❌ Brak Dark*")
        elif len(dark_files) > 1:
            error_msgs.append(f"❌ Powielone Dark* ({len(dark_files)})")

        if len(flat_files) == 0:
            error_msgs.append("❌ Brak Flat*")
        elif len(flat_files) > 1:
            error_msgs.append(f"❌ Powielone Flat* ({len(flat_files)})")

        # Wynik
        if error_msgs:
            print(f"📁 {os.path.basename(sub)} → " + " | ".join(error_msgs))
        else:
            print(f"✅ {os.path.basename(sub)} → OK (Dark: {dark_files[0]}, Flat: {flat_files[0]})")

    print("\n✔️ Sprawdzanie zakończone.")


if __name__ == "__main__":
    BASE_DIR = choose_base_dir()
    if not BASE_DIR:
        print("Nie wybrano katalogu.")
    else:
        check_masters_once(BASE_DIR)
    input("\nNaciśnij Enter, aby zakończyć...")


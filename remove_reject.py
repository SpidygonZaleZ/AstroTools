import os
import shutil
import tkinter as tk
from tkinter import filedialog

def choose_src_dir():
    root = tk.Tk()
    root.withdraw()          # nie pokazuj głównego okna
    root.attributes("-topmost", True)

    folder = filedialog.askdirectory(
        title="Wybierz katalog bazowy z danymi"
    )

    root.destroy()
    return folder

def make_dest_dir(src_dir):
    parent = os.path.dirname(src_dir)
    name = os.path.basename(src_dir)
    return os.path.join(parent, name + "_reject")
    
def przenies_rejecty(src_root, dest_root):
    total_files = 0

    for root, dirs, files in os.walk(src_root):
        if "reject" in dirs:
            reject_path = os.path.join(root, "reject")
            parent_name = os.path.basename(root)  # np. 'Projekt1'
            dest_folder = os.path.join(dest_root, parent_name)

            print(f"\nPrzenoszę zawartość: {reject_path} -> {dest_folder}")

            os.makedirs(dest_folder, exist_ok=True)

            # Licznik dla bieżącego folderu reject
            local_file_count = 0

            for item in os.listdir(reject_path):
                src_item = os.path.join(reject_path, item)
                dest_item = os.path.join(dest_folder, item)

                if os.path.isdir(src_item):
                    shutil.move(src_item, dest_item)
                    for _, _, files_in_subdir in os.walk(dest_item):
                        local_file_count += len(files_in_subdir)
                else:
                    shutil.move(src_item, dest_item)
                    local_file_count += 1

            print(f"📦 Przeniesiono {local_file_count} plików.")

            total_files += local_file_count

            # Usuń pusty folder 'reject'
            try:
                os.rmdir(reject_path)
            except OSError:
                print(f"⚠️ Nie można usunąć folderu {reject_path} – może nie jest pusty.")

    return total_files

if __name__ == "__main__":
    SRC_DIR = choose_src_dir()
    if not SRC_DIR:
        print("Nie wybrano katalogu.")
        input("Naciśnij Enter, aby zakończyć...")
        exit(0)

    DEST_DIR = make_dest_dir(SRC_DIR)

    print(f"SRC_DIR : {SRC_DIR}")
    print(f"DEST_DIR: {DEST_DIR}")

    # 🔒 ZABEZPIECZENIE
    src_abs = os.path.abspath(SRC_DIR)
    dest_abs = os.path.abspath(DEST_DIR)

    if src_abs == dest_abs:
        print("❌ BŁĄD: Folder źródłowy i docelowy są takie same!")
        input("Naciśnij Enter, aby zakończyć...")
        exit(1)

    os.makedirs(DEST_DIR, exist_ok=True)

    total_files = przenies_rejecty(SRC_DIR, DEST_DIR)
    print(f"\n✅ Łącznie przeniesiono {total_files} plików.")
    input("Naciśnij Enter, aby zakończyć...")

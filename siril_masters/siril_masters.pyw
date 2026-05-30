#!/usr/bin/env python
# Author: Radek Zaleski

import os
import subprocess
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import re
import shutil
import threading

# --- KONFIGURACJA ---
SIRIL_CLI_PATH = r"C:\Program Files\Siril\bin\siril-cli.exe"
SIRIL_VER = "1.4.1"

class SirilMasterApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Siril {SIRIL_VER} Master Stacker")
        self.root.geometry("500x450")
        
        tk.Label(root, text="Panel Kalibracji Siril", font=("Arial", 12, "bold")).pack(pady=15)
        
        self.btn_bias = tk.Button(root, text="⚡ MASTER BIAS", command=self.start_bias, width=35)
        self.btn_bias.pack(pady=5)
        
        self.btn_dark = tk.Button(root, text="🌡 MASTER DARK", command=self.start_dark, width=35)
        self.btn_dark.pack(pady=5)
        
        self.btn_flat = tk.Button(root, text="💡 MASTER FLAT (- Bias/DarkFlat)", command=self.start_flat, width=35)
        self.btn_flat.pack(pady=5)

        self.progress_label = tk.Label(root, text="Status: Oczekiwanie...", font=("Arial", 9), wraplength=450)
        self.progress_label.pack(pady=(20, 5))
        
        self.progress = ttk.Progressbar(root, orient="horizontal", length=380, mode="determinate")
        self.progress.pack(pady=5)
        
        self.status_info = tk.Label(root, text="", font=("Arial", 9, "bold"), wraplength=450)
        self.status_info.pack(pady=10)

    def check_existing_master(self, folder_path, output_name):
        """Sprawdza różne rozszerzenia i pyta czy nadpisać."""
        extensions = [".fit", ".fits", ".fit.fz", ".fits.fz"]
        for ext in extensions:
            full_path = os.path.join(folder_path, f"{output_name}{ext}")
            if os.path.exists(full_path):
                # Pytanie do użytkownika: Tak = Skasuj i rób od nowa, Nie/Anuluj = Przerwij
                answer = messagebox.askyesno(
                    "Master już istnieje",
                    f"W folderze jest już plik:\n{output_name}{ext}\n\n"
                    f"Czy chcesz go SKASOWAĆ i stworzyć nowy?\n"
                    f"(Wybranie 'Nie' przerwie operację)"
                )
                if answer: # Wybrano TAK
                    try:
                        os.remove(full_path)
                        return True
                    except Exception as e:
                        messagebox.showerror("Błąd", f"Nie udało się usunąć pliku: {e}")
                        return False
                else: # Wybrano NIE lub zamknięto okno
                    return False
        return True

    def create_python_symlinks(self, src_dir, dst_dir, prefix):
        if os.path.exists(dst_dir):
            shutil.rmtree(dst_dir)
        os.makedirs(dst_dir)
        
        files = [f for f in os.listdir(src_dir) if f.lower().endswith(('.fit', '.fits', '.fz'))]
        files.sort()
        
        for i, filename in enumerate(files):
            src_path = os.path.join(src_dir, filename)
            dst_path = os.path.join(dst_dir, f"{prefix}_{i:05d}.fit")
            try:
                os.symlink(src_path, dst_path)
            except OSError:
                shutil.copy2(src_path, dst_path)

    def update_status(self, percent, status_text):
        self.progress['value'] = percent
        self.progress_label.config(text=f"Status: {status_text}")
        self.root.update_idletasks()

    def run_siril_thread(self, commands, workdir, log_path, output_name):
        self.btn_bias.config(state=tk.DISABLED)
        self.btn_dark.config(state=tk.DISABLED)
        self.btn_flat.config(state=tk.DISABLED)
        self.status_info.config(text="")
        
        def task():
            script_path = os.path.join(workdir, "siril_temp_script.ssf")
            commands.insert(0, f"requires {SIRIL_VER}")
            
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("\n".join(commands))
            
            progress_pattern = re.compile(r'progress:.*?([\d\.]+)%')
            
            try:
                process = subprocess.Popen(
                    [SIRIL_CLI_PATH, "-s", script_path, "-d", workdir],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="cp1250", errors="replace"
                )

                for line in process.stdout:
                    match = progress_pattern.search(line)
                    if match:
                        percent = float(match.group(1))
                        self.root.after(0, self.update_status, percent, f"Przetwarzanie... {percent}%")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(line)

                process.wait()
                
                p_dir = os.path.join(workdir, "process")
                if os.path.exists(p_dir):
                    shutil.rmtree(p_dir)

                if process.returncode == 0:
                    self.root.after(0, lambda: self.status_info.config(text=f"✅ GOTOWE: {output_name}", fg="green"))
                else:
                    self.root.after(0, lambda: self.status_info.config(text="❌ BŁĄD SIRILA (Sprawdź logi)", fg="red"))

            except Exception as e:
                self.root.after(0, lambda: self.status_info.config(text=f"❗ BŁĄD: {str(e)}", fg="red"))
            finally:
                if os.path.exists(script_path): os.remove(script_path)
                self.root.after(0, lambda: [b.config(state=tk.NORMAL) for b in [self.btn_bias, self.btn_dark, self.btn_flat]])

        threading.Thread(target=task, daemon=True).start()

    def parse_folder_name(self, path):
        folder_name = os.path.basename(os.path.normpath(path))
        match = re.match(r"(\d{4}-\d{2}-\d{2})_(.*)", folder_name)
        if match:
            date, rest = match.groups()
            return f"{rest}_{date}"
        return folder_name

    def start_bias(self):
        path = filedialog.askdirectory(title="Wybierz folder BIAS")
        if not path: return
        p = os.path.normpath(path)
        out = self.parse_folder_name(p) + "_MASTER"
        
        if not self.check_existing_master(p, out): return

        self.update_status(0, "Tworzenie symlinków...")
        self.create_python_symlinks(p, os.path.join(p, "process"), "bias")
        
        s_path = p.replace('\\', '/')
        cmds = [
            f"cd '{s_path}/process'",
            "link bias -out=bias",
            f"stack bias rej winsorized 3 3 -nonorm -out=../{out}",
            "close"
        ]
        self.run_siril_thread(cmds, p, os.path.join(p, "siril_log.txt"), out)

    def start_dark(self):
        path = filedialog.askdirectory(title="Wybierz folder DARK")
        if not path: return
        p = os.path.normpath(path)
        out = self.parse_folder_name(p) + "_MASTER"
        
        if not self.check_existing_master(p, out): return

        self.update_status(0, "Tworzenie symlinków...")
        self.create_python_symlinks(p, os.path.join(p, "process"), "dark")
        
        s_path = p.replace('\\', '/')
        cmds = [
            f"cd '{s_path}/process'",
            "link dark -out=dark",
            f"stack dark rej winsorized 3 3 -nonorm -out=../{out}",
            "close"
        ]
        self.run_siril_thread(cmds, p, os.path.join(p, "siril_log.txt"), out)

    def start_flat(self):
        f_path = filedialog.askdirectory(title="Wybierz folder FLAT")
        if not f_path: return
        p = os.path.normpath(f_path)
        out = self.parse_folder_name(p) + "_MASTER"
        
        if not self.check_existing_master(p, out): return

        b_file = filedialog.askopenfilename(title="Wybierz MASTER BIAS / DARK-FLAT", filetypes=[("Fits", "*.fit *.fits *.fz")])
        if not b_file: return
        
        process_dir = os.path.join(p, "process")
        self.update_status(0, "Tworzenie symlinków...")
        self.create_python_symlinks(p, process_dir, "flat")
        
        tmp_bias = "master_bias_tmp.fit"
        shutil.copy2(b_file, os.path.join(process_dir, tmp_bias))
        
        s_path = p.replace('\\', '/')
        cmds = [
            f"cd '{s_path}/process'",
            "link flat -out=flat",
            f"calibrate flat -bias={tmp_bias}",
            f"stack pp_flat rej winsorized 3 3 -norm=mul -out=../{out}",
            "close"
        ]
        self.run_siril_thread(cmds, p, os.path.join(p, "siril_log.txt"), out)

if __name__ == "__main__":
    root = tk.Tk()
    app = SirilMasterApp(root)
    root.mainloop()
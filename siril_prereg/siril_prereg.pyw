#!/usr/bin/env python
# Author: Radek Zaleski

import os
import sys
import glob
import fnmatch
import subprocess
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk, messagebox
import re
import configparser
import threading
import time
import shutil
from datetime import datetime

def get_config_path(filename):
    if getattr(sys, 'frozen', False):  # uruchomione jako .exe
        app_dir = os.path.dirname(sys.executable)
    else:  # uruchomione jako .py
        app_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(app_dir, filename)

SIRIL_CLI_PATH = r"C:\Program Files\Siril\bin\siril-cli.exe"
SIRIL_VER = "1.4.1"
LOG_FILE = "siril_log.txt"
CONFIG_FILE = get_config_path("siril_prereg.ini")

class SirilApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Siril Preprocess & Register v{SIRIL_VER}")
        self.root.geometry("1200x900+10+10")
        
        self.config = configparser.ConfigParser()
        self.work_dir = tk.StringVar()
        self.is_mono = tk.BooleanVar()
        
        self.load_config()
        self.create_widgets()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE)
            if "Settings" in self.config:
                self.work_dir.set(self.config.get("Settings", "path", fallback=""))
                self.is_mono.set(self.config.getboolean("Settings", "mono", fallback=False))

    def save_config(self):
        if not self.config.has_section("Settings"):
            self.config.add_section("Settings")
        self.config.set("Settings", "path", self.work_dir.get())
        self.config.set("Settings", "mono", str(self.is_mono.get()))
        with open(CONFIG_FILE, "w") as f:
            self.config.write(f)

    def create_widgets(self):
        frame_top = tk.LabelFrame(self.root, text="Folder Nadrzędny", padx=10, pady=10)
        frame_top.pack(fill="x", padx=10, pady=5)
        frame_top.columnconfigure(0, weight=1)

        tk.Entry(frame_top, textvariable=self.work_dir).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        tk.Button(frame_top, text="Wybierz folder", command=self.browse_folder).grid(row=0, column=1)
        tk.Checkbutton(frame_top, text="Sensor MONO", variable=self.is_mono).grid(row=1, column=0, sticky="w")

        self.btn_run = tk.Button(self.root, text="URUCHOM", command=self.validate_and_start, bg="#e1e1e1", font=("Arial", 10, "bold"), height=2)
        self.btn_run.pack(pady=(10, 5), fill="x", padx=10)

        frame_prog = tk.Frame(self.root, padx=10)
        frame_prog.pack(fill="x")
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(frame_prog, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=2)
        self.status_label = tk.Label(frame_prog, text="Gotowy", font=("Arial", 9))
        self.status_label.pack(anchor="w", pady=(0, 5))

        self.console = scrolledtext.ScrolledText(self.root, height=25, bg="white", fg="black", font=("Segoe UI", 9))
        self.console.pack(padx=10, pady=5, fill="both", expand=True)
        
        # TAGI KOLORYSTYCZNE
        self.console.tag_config("bold", font=("Segoe UI", 9, "bold"))
        self.console.tag_config("blue", foreground="#0056b3")
        self.console.tag_config("gray", foreground="#6c757d")
        self.console.tag_config("purple", foreground="#6f42c1")
        self.console.tag_config("green", foreground="#28a745")
        self.console.tag_config("red", foreground="#dc3545")

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.work_dir.set(os.path.normpath(path))
            self.save_config()

    def log_to_console(self, text, indent=0, newline=True, tag=None):
        ts = datetime.now().strftime("[%H:%M:%S] ")
        prefix = ts if indent == 0 else "    "
        self.console.insert(tk.END, prefix)
        self.console.insert(tk.END, text, tag if tag else "")
        if newline: self.console.insert(tk.END, "\n")
        self.console.see(tk.END)
        self.root.update_idletasks()

    def validate_and_start(self):
        root_dir = self.work_dir.get()
        if not root_dir or not os.path.isdir(root_dir):
            messagebox.showerror("Błąd", "Wybierz poprawny folder!")
            return

        filter_folders = [f for f in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, f))]
        report = []
        missing_masters = []
        valid_structure = []
        single_light_warns = []

        for filt in filter_folders:
            filt_path = os.path.join(root_dir, filt)
            sessions = [s for s in os.listdir(filt_path) if os.path.isdir(os.path.join(filt_path, s))]
            filt_lights = 0
            for sub in sessions:
                light_sub = os.path.join(filt_path, sub)
                master_sub = os.path.join(light_sub, "masters")
                lights = [f for f in os.listdir(light_sub) if fnmatch.fnmatch(f.lower(), "light_*.fits")]
                if len(lights) == 1:
                    single_light_warns.append(f"{filt}/{sub}")
                if lights:
                    filt_lights += len(lights)
                    d = [f for f in os.listdir(master_sub) if "dark_" in f.lower()] if os.path.exists(master_sub) else []
                    fl = [f for f in os.listdir(master_sub) if "flat_" in f.lower()] if os.path.exists(master_sub) else []
                    if not d or not fl: missing_masters.append(f"{filt}/{sub}")
            if filt_lights > 0:
                report.append(f"• {filt}: {filt_lights} klatek")
                valid_structure.append(filt)

        if not valid_structure: return
        msg = "Analiza folderów:\n" + "\n".join(report)
        if single_light_warns:
            msg += "\n\n⚠️ POMINIĘTE (tylko 1 klatka LIGHT - Siril wymaga min. 2):\n" + "\n".join(single_light_warns[:5])
            if len(single_light_warns) > 5:
                msg += f"\n...oraz {len(single_light_warns) - 5} innych."
        if missing_masters:
            msg += "\n\n⚠️ BRAK MASTERÓW W:\n" + "\n".join(missing_masters[:5]) + "\n\nKontynuować?"
        else: msg += "\n\nUruchomić?"

        if messagebox.askyesno("Potwierdzenie", msg):
            self.start_thread(valid_structure)

    def run_siril_script(self, script_path, work_dir, log_file_obj):
        progress_pattern = re.compile(r'progress:.*?([\d\.]+)%')
        CREATE_NO_WINDOW = 0x08000000
        process = subprocess.Popen([SIRIL_CLI_PATH, "-s", script_path], cwd=work_dir, 
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=CREATE_NO_WINDOW)
        while True:
            line = process.stdout.readline()
            if not line: break
            log_file_obj.write(line)
            match = progress_pattern.search(line)
            if match:
                self.update_progress(float(match.group(1)))
        process.wait()
        return process.returncode

    def update_progress(self, val, status_text=None):
        self.progress_var.set(val)
        if status_text: self.status_label.config(text=status_text)
        self.root.update_idletasks()

    def start_thread(self, filter_list):
        self.btn_run.config(state="disabled")
        self.console.delete(1.0, tk.END)
        threading.Thread(target=self.main_process, args=(filter_list,), daemon=True).start()

    def main_process(self, filter_list):
        total_start_time = time.time()
        root_dir = self.work_dir.get()
        log_path = os.path.join(root_dir, LOG_FILE)
        
        self.log_to_console("🚀 Start", tag="bold")

        with open(log_path, "a", encoding="utf-8") as log_f:
            for filt in filter_list:
                filt_dir = os.path.join(root_dir, filt)
                sessions = [s for s in os.listdir(filt_dir) if os.path.isdir(os.path.join(filt_dir, s))]
                
                self.log_to_console(f"📂 Filtr: {filt}", tag="bold")
                
                for sub in sessions:
                    light_sub = os.path.join(filt_dir, sub)
                    master_sub = os.path.join(light_sub, "masters")
                    lights = [f for f in os.listdir(light_sub) if fnmatch.fnmatch(f.lower(), "light_*.fits")]
                    darks = [f for f in os.listdir(master_sub) if "dark_" in f.lower()] if os.path.exists(master_sub) else []
                    flats = [f for f in os.listdir(master_sub) if "flat_" in f.lower()] if os.path.exists(master_sub) else []

                    if len(lights) == 1:
                        self.log_to_console(f"  ⚠️ Pominięto sesję {sub}: Wykryto tylko 1 plik LIGHT (Siril wymaga min. 2)!", tag="red")
                        continue

                    if not (lights and darks and flats): continue

                    self.log_to_console(f"  🔄 Sesja: {sub} ({len(lights)} klatek) ... ", newline=False, tag="blue")
                    
                    dark = os.path.join(master_sub, darks[0])
                    flat = os.path.join(master_sub, flats[0])
                    ssf_path = os.path.join(filt_dir, f"calibrate_{sub}.ssf")
                    name = os.path.basename(os.path.normpath(light_sub))
                    
                    cal_line = f"calibrate Light_{name}_ -dark={dark} -flat={flat} -cc=dark 3 3"
                    if not self.is_mono.get(): cal_line += " -cfa -debayer -equalize_cfa"
                    
                    with open(ssf_path, "w") as f:
                        f.write(f"requires {SIRIL_VER}\ncd \"{light_sub}\"\nconvert Light_{name}_ -out=..\ncd ..\n{cal_line}\n")

                    self.update_progress(0, f"Filtr {filt} | {sub}")
                    if self.run_siril_script(ssf_path, light_sub, log_f) == 0:
                        self.console.insert(tk.END, "✅ OK\n", "green")
                    else:
                        self.console.insert(tk.END, "❌ BŁĄD\n", "red")
                        self.btn_run.config(state="normal")
                        return

                self.log_to_console(f"  🧹 Sprzątanie plików pośrednich {filt} ... ", newline=False, tag="gray")
                for f in glob.glob(os.path.join(filt_dir, "Light*.fit")): os.remove(f)
                self.console.insert(tk.END, "✅ OK\n", "green")

                self.log_to_console(f"  🎞 Sekwencja zbiorcza {filt} ... ", newline=False)
                seq_ssf = os.path.join(filt_dir, f"seq_{filt}.ssf")
                with open(seq_ssf, "w") as f:
                    f.write(f"requires {SIRIL_VER}\ncd \"{filt_dir}\"\nconvert {filt}_ -fitseq\n")
                
                self.update_progress(0, f"Sekwencja {filt}")
                if self.run_siril_script(seq_ssf, filt_dir, log_f) == 0:
                    self.console.insert(tk.END, "✅ OK\n", "green")
                else:
                    self.console.insert(tk.END, "❌ BŁĄD\n", "red")

                self.log_to_console(f"  📌 Rejestracja {filt} ... ", newline=False, tag="purple")
                reg_ssf = os.path.join(filt_dir, f"reg_{filt}.ssf")
                with open(reg_ssf, "w") as f:
                    f.write(f"requires {SIRIL_VER}\ncd \"{filt_dir}\"\nregister {filt}_ -2pass -layer=1 -transf=homography\n")
                
                self.update_progress(0, f"Rejestracja {filt}")
                if self.run_siril_script(reg_ssf, filt_dir, log_f) == 0:
                    self.console.insert(tk.END, "✅ OK\n", "green")
                else:
                    self.console.insert(tk.END, "❌ BŁĄD\n", "red")

                self.log_to_console(f"  📦 Finalizacja i czyszczenie folderu {filt} ... ", newline=False, tag="gray")
                final_files = [f"{filt}_.seq", f"{filt}_.fit.fz", f"{filt}_conversion.txt"]
                for fname in final_files:
                    src_path = os.path.join(filt_dir, fname)
                    if os.path.exists(src_path):
                        shutil.move(src_path, os.path.join(root_dir, fname))

                for item in os.listdir(filt_dir):
                    item_path = os.path.join(filt_dir, item)
                    if item not in sessions:
                        if os.path.isdir(item_path): shutil.rmtree(item_path, ignore_errors=True)
                        else: os.remove(item_path)
                
                self.console.insert(tk.END, "✅ OK\n", "green")

        elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - total_start_time))
        self.log_to_console(f"✅ Koniec (Czas: {elapsed})", tag="bold")
        self.update_progress(100, "Gotowe")
        self.btn_run.config(state="normal")

if __name__ == "__main__":
    def on_close():
        app.save_config()
        root.destroy()
        root.quit()
        
    root = tk.Tk()
    app = SirilApp(root)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
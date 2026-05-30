#!/usr/bin/env python
# Author: Radek Zaleski

import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext, messagebox
import os
import sys
import pathlib
import configparser
from astropy.io import fits
from collections import defaultdict
from datetime import datetime, timedelta

def get_config_path(filename):
    if getattr(sys, 'frozen', False):  # uruchomione jako .exe
        app_dir = os.path.dirname(sys.executable)
    else:  # uruchomione jako .py
        app_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(app_dir, filename)

CONFIG_FILE = get_config_path("symlink_maker.ini")

class MasterSelectionDialog(tk.Toplevel):
    def __init__(self, parent, final_groups, masters_pool):
        super().__init__(parent)
        self.title("Wybór Masterów dla folderów")
        self.geometry("1200x900+10+10")
        self.grab_set()
        
        self.final_groups = final_groups
        self.masters_pool = masters_pool
        self.result = None  
        
        self.create_widgets()
        
    def create_widgets(self):
        # Główny kontener
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Canvas i Scrollbar
        canvas = tk.Canvas(main_frame, borderwidth=0, background="#f0f0f0")
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        
        # Dynamiczna ramka wewnętrzna
        scrollable_frame = ttk.Frame(canvas)
        
        def configure_scrollable_frame(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        canvas.bind("<Configure>", configure_scrollable_frame)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Nagłówki kolumn
        headers = ["Folder Docelowy (Grupa)", "Wybór DARK", "Wybór FLAT"]
        for col, h_text in enumerate(headers):
            lbl = ttk.Label(scrollable_frame, text=h_text, font=("Segoe UI", 10, "bold"))
            lbl.grid(row=0, column=col, padx=10, pady=5, sticky="ew")
            
        scrollable_frame.columnconfigure(0, weight=0)
        scrollable_frame.columnconfigure(1, weight=1)
        scrollable_frame.columnconfigure(2, weight=1)
        
        self.selections = {}
        
        for idx, group in enumerate(self.final_groups):
            l_meta = group['meta']
            
            d_cands = [m for m in self.masters_pool if "DARK" in m['type'] and m['instrume'] == l_meta['instrume'] and m['gain'] == l_meta['gain'] 
                      and m['offset'] == l_meta['offset'] and abs(m['temp'] - l_meta['temp']) <= 2.0 and abs(m['exp'] - l_meta['exp']) < 0.1]
            f_cands = [m for m in self.masters_pool if "FLAT" in m['type'] and m['filter'] == l_meta['filter'] 
                       and m['telescop'] == l_meta['telescop'] and m['instrume'] == l_meta['instrume']]
            
            best_dark = min(d_cands, key=lambda m: abs((m['datetime'] - group['avg_dt']).total_seconds())) if d_cands else None
            best_flat = min(f_cands, key=lambda m: abs((m['datetime'] - group['avg_dt']).total_seconds())) if f_cands else None
            
            row_idx = idx + 1
            
            lbl_folder = ttk.Label(scrollable_frame, text=f"{group['rel_path']} ({len(group['lights'])} szt.)", font=("Segoe UI", 9))
            lbl_folder.grid(row=row_idx, column=0, padx=10, pady=5, sticky="w")
            
            dark_options = ["BRAK MASTERA"] + [f"{m['fname']} ({m['astro_date']})" for m in d_cands]
            combo_dark = ttk.Combobox(scrollable_frame, values=dark_options, state="readonly")
            if best_dark:
                combo_dark.set(f"{best_dark['fname']} ({best_dark['astro_date']})")
            else:
                combo_dark.set("BRAK MASTERA")
            combo_dark.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
            
            flat_options = ["BRAK MASTERA"] + [f"{m['fname']} ({m['astro_date']})" for m in f_cands]
            combo_flat = ttk.Combobox(scrollable_frame, values=flat_options, state="readonly")
            if best_flat:
                combo_flat.set(f"{best_flat['fname']} ({best_flat['astro_date']})")
            else:
                combo_flat.set("BRAK MASTERA")
            combo_flat.grid(row=row_idx, column=2, padx=5, pady=5, sticky="ew")
            
            dark_map = {f"{m['fname']} ({m['astro_date']})": m for m in d_cands}
            flat_map = {f"{m['fname']} ({m['astro_date']})": m for m in f_cands}
            
            self.selections[idx] = {
                'combo_dark': combo_dark, 'dark_map': dark_map,
                'combo_flat': combo_flat, 'flat_map': flat_map
            }
            
        # Dolny panel z przyciskami
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", side="bottom", padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Zatwierdź i przetwarzaj", command=self.on_accept).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Anuluj", command=self.on_cancel).pack(side="right", padx=5)

    def on_accept(self):
        self.result = {}
        for idx, widgets in self.selections.items():
            sel_dark_str = widgets['combo_dark'].get()
            sel_flat_str = widgets['combo_flat'].get()
            
            chosen_dark = widgets['dark_map'].get(sel_dark_str, None)
            chosen_flat = widgets['flat_map'].get(sel_flat_str, None)
            
            self.result[idx] = {'DARK': chosen_dark, 'FLAT': chosen_flat}
            
        self.destroy()
        
    def on_cancel(self):
        self.result = None
        self.destroy()

class SymlinkApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Astro Organizer")
        self.root.geometry("1200x900+20+20")

        self.source_dir = tk.StringVar()
        self.dest_dir = tk.StringVar()
        self.masters_dir = tk.StringVar()
        self.filter_text = tk.StringVar()

        self.load_config()
        self.create_widgets()
        self.populate_folder_list()

    def log(self, message, tag=None):
        self.log_area.insert(tk.END, message + "\n", tag)
        self.log_area.see(tk.END)
        self.root.update_idletasks()

    def create_widgets(self):
        self.combos = {}
        for label, var, key in [
            ("Lights", self.source_dir, "lights"),
            ("Masters", self.masters_dir, "masters"),
            ("Destination", self.dest_dir, "dest")
        ]:
            frame = ttk.LabelFrame(self.root, text=label)
            frame.pack(fill="x", padx=10, pady=2)
            frame.columnconfigure(0, weight=1)

            combo = ttk.Combobox(frame, textvariable=var)
            self.combos[key] = combo
            combo.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

            combo['values'] = self._get_history(key)

            btn = ttk.Button(frame, text="Browse", width=12,
                             command=lambda v=var, k=key: self.browse_dir(v, k))
            btn.grid(row=0, column=1, padx=5, pady=5)

            def on_select(event, v=var, k=key, c=combo):
                val = c.get()
                if val:
                    hist = self._set_history(k, val)
                    self.combos[k]['values'] = hist
                    self.save_config()
                    if k == "lights":
                        self.populate_folder_list()

            combo.bind("<<ComboboxSelected>>", on_select)

        mid_frame = ttk.Frame(self.root)
        mid_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(mid_frame, text="Filtr:").pack(side="left", padx=5)
        ttk.Entry(mid_frame, textvariable=self.filter_text).pack(side="left", padx=5, fill="x", expand=True)
        
        self.filter_text.trace_add("write", lambda *args: self.populate_folder_list())

        listbox_frame = ttk.Frame(self.root)
        listbox_frame.pack(padx=10, pady=5, fill="x")

        listbox_scroll = ttk.Scrollbar(listbox_frame, orient="vertical")
        listbox_scroll.pack(side="right", fill="y")

        self.folder_listbox = tk.Listbox(
            listbox_frame, 
            selectmode=tk.MULTIPLE, 
            height=10, 
            font=("Segoe UI", 9),
            yscrollcommand=listbox_scroll.set
        )
        self.folder_listbox.pack(side="left", fill="x", expand=True)

        listbox_scroll.config(command=self.folder_listbox.yview)

        ttk.Button(self.root, text="START PROCESSING", command=self.process_selected).pack(pady=10)

        log_frame = ttk.LabelFrame(self.root, text="Podsumowanie")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=20, bg="#ffffff", font=("Consolas", 10))
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.log_area.tag_config("blue", foreground="#0055ff", font=("Consolas", 10, "bold"))
        self.log_area.tag_config("green", foreground="#008800")
        self.log_area.tag_config("red", foreground="#cc0000", font=("Consolas", 10, "bold"))
        self.log_area.tag_config("gray", foreground="#666666")
        self.log_area.tag_config("header", foreground="#444444", font=("Consolas", 11, "bold"))

    def browse_dir(self, var, key):
        initial = var.get() if os.path.exists(var.get()) else os.getcwd()
        folder = filedialog.askdirectory(initialdir=initial)
        if folder:
            var.set(folder)
            hist = self._set_history(key, folder)
            self.combos[key]['values'] = hist
            self.save_config()
            self.populate_folder_list()

    def get_fits_metadata(self, filepath):
        try:
            with fits.open(filepath) as hdul:
                idx = 1 if filepath.lower().endswith('.fz') and len(hdul) > 1 else 0
                h = hdul[idx].header
                date_str = h.get('DATE-OBS', '')
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', ''))
                except:
                    dt = datetime.fromtimestamp(os.path.getmtime(filepath))
                astro_dt = dt - timedelta(hours=12)
                
                return {
                    "type": str(h.get('IMAGETYP', '')).upper(),
                    "filter": str(h.get('FILTER', 'NoFilter')).upper(),
                    "exp": float(h.get('EXPTIME', 0)),
                    "gain": str(h.get('GAIN', '0')),
                    "offset": str(h.get('OFFSET', '0')),
                    "temp": float(h.get('CCD-TEMP', h.get('SET-TEMP', 0))),
                    "instrume": str(h.get('INSTRUME', '')).strip(),
                    "telescop": str(h.get('TELESCOP', '')).strip(),
                    "path": filepath,
                    "fname": os.path.basename(filepath),
                    "object": str(h.get('OBJECT', 'Unknown')),
                    "datetime": dt,
                    "astro_date": astro_dt.strftime('%Y-%m-%d')
                }
        except: return None

    def process_selected(self):
        dest_root = self.dest_dir.get()
        if not dest_root: return
        if os.path.exists(dest_root) and os.listdir(dest_root):
            if not messagebox.askyesno("Uwaga", "Folder docelowy nie jest pusty. Kontynuować?"): return

        self.log_area.delete('1.0', tk.END)
        selected_indices = self.folder_listbox.curselection()
        if not selected_indices: return

        masters_pool = []
        if os.path.exists(self.masters_dir.get()):
            for root, _, files in os.walk(self.masters_dir.get()):
                for f in files:
                    if f.lower().endswith(('.fits', '.fit', '.fz')):
                        meta = self.get_fits_metadata(os.path.join(root, f))
                        if meta: masters_pool.append(meta)

        source_root = self.source_dir.get()
        groups_map = defaultdict(list)
        meta_files_map = defaultdict(set)
        
        sources_per_group = defaultdict(set)
        meta_to_find = ["AcquisitionDetails.csv", "ImageMetaData.csv", "WeatherData.csv"]
        
        for i in selected_indices:
            folder_name = self.folder_listbox.get(i)
            folder_path = os.path.join(source_root, folder_name)
            found_meta = [os.path.join(folder_path, m) for m in meta_to_find if os.path.exists(os.path.join(folder_path, m))]

            for fname in os.listdir(folder_path):
                if not fname.lower().endswith(('.fits', '.fit', '.fz')): continue
                meta = self.get_fits_metadata(os.path.join(folder_path, fname))
                if meta and "LIGHT" in meta['type']:
                    key = (meta['filter'], meta['exp'], meta['gain'], meta['offset'], meta['astro_date'])
                    groups_map[key].append(meta)
                    sources_per_group[key].add(folder_name)
                    for m_p in found_meta: meta_files_map[key].add(m_p)

        sort_order = ["L", "R", "G", "B", "S", "H", "O"]
        final_groups = []
        for key, lights in groups_map.items():
            rel_path = os.path.join(key[0], f"{key[1]}s_G{key[2]}_{key[4]}")
            final_groups.append({
                'key': key, 'rel_path': rel_path, 'lights': lights, 'meta': lights[0],
                'avg_dt': datetime.fromtimestamp(sum(l['datetime'].timestamp() for l in lights)/len(lights))
            })
        final_groups.sort(key=lambda x: (sort_order.index(x['meta']['filter']) if x['meta']['filter'] in sort_order else 999, x['rel_path']))

        # --- NOWA SEKCJA: WYŚWIETLENIE OKNA WYBORU ---
        dialog = MasterSelectionDialog(self.root, final_groups, masters_pool)
        self.root.wait_window(dialog)
        
        if dialog.result is None:
            self.log("Anulowano przetwarzanie przez użytkownika.")
            return
        user_masters = dialog.result
        # ---------------------------------------------

        report_stats = {"filters_time": defaultdict(float), "filters_details": defaultdict(lambda: defaultdict(int)), "objects": set(), "dates": []}
        last_filter = None

        for idx, group in enumerate(final_groups):
            curr_filter = group['meta']['filter']
            if curr_filter != last_filter:
                self.log(f"\n=============== FILTR: {curr_filter} ===============", "header")
                last_filter = curr_filter

            full_target_dir = os.path.join(dest_root, group['rel_path'])
            os.makedirs(os.path.join(full_target_dir, "masters"), exist_ok=True)

            self.log(f"Docelowy: {group['rel_path']} [{len(group['lights'])} lights]", "blue")
            self.log(f"  > Źródłowy: {', '.join(sorted(sources_per_group[group['key']]))}", "gray")

            for l in group['lights']:
                l_dst = os.path.join(full_target_dir, l['fname'])
                if not os.path.exists(l_dst): pathlib.Path(l_dst).symlink_to(l['path'])
                report_stats["filters_time"][l['filter']] += l['exp']
                report_stats["filters_details"][l['filter']][l['exp']] += 1
                report_stats["objects"].add(l['object'])
                report_stats["dates"].append(l['astro_date'])

            meta_paths = meta_files_map[group['key']]
            found_names = [os.path.basename(p) for p in meta_paths]
            for m_req in meta_to_find:
                if m_req not in found_names:
                    self.log(f"  > !!! BRAK PLIKU: {m_req} !!!", "red")
            
            for m_p in meta_paths:
                m_name = os.path.basename(m_p)
                m_dst = os.path.join(full_target_dir, m_name)
                if os.path.exists(m_dst):
                    prefix = os.path.basename(os.path.dirname(m_p))
                    m_dst = os.path.join(full_target_dir, f"{prefix}_{m_name}")
                if not os.path.exists(m_dst): pathlib.Path(m_dst).symlink_to(m_p)

            # Pobranie wyboru użytkownika z okna modalnego dla tej konkretnej grupy
            chosen_for_group = user_masters[idx]
            
            for label in ["DARK", "FLAT"]:
                best = chosen_for_group[label]
                if best:
                    m_dst = os.path.join(full_target_dir, "masters", best['fname'])
                    if not os.path.exists(m_dst): pathlib.Path(m_dst).symlink_to(best['path'])
                    self.log(f"  > {label}: {best['fname']} ({best['astro_date']})", "green")
                else:
                    self.log(f"  > {label}: !!! BRAK MASTERA !!!", "red")
            self.log("-" * 75, "gray")

        report_text = self.generate_text_report(dest_root, report_stats, sort_order)
        if report_text:
            self.log("\n" + report_text)
            
        self.log("\n*** ZAKOŃCZONO ***")

    def generate_text_report(self, dest_path, stats, sort_order):
        if not stats["dates"]: return None
        found_f = sorted(stats["filters_time"].keys(), key=lambda x: sort_order.index(x) if x in sort_order else 999)
        report = ["=== PODSUMOWANIE ===", f"Obiekty: {', '.join(sorted(stats['objects']))}", 
                  f"Daty: {min(stats['dates'])} do {max(stats['dates'])}", "-" * 30]
        total_s = 0
        for f in found_f:
            sec = stats["filters_time"][f]
            report.append(f"  * {f}: {sec / 3600.0:.2f} h")
            total_s += sec
        report.append("-" * 30)
        for f in found_f:
            details = stats["filters_details"][f]
            d_str = ", ".join([f"{e}s x {details[e]}" for e in sorted(details.keys())])
            report.append(f"  * {f}: {d_str}")
        report.append(f"\nŁączny czas: {total_s / 3600.0:.2f} h")
        
        full_report = "\n".join(report)
        with open(os.path.join(dest_path, "session_summary.txt"), "w", encoding="utf-8") as f: 
            f.write(full_report)
            
        return full_report

    def populate_folder_list(self):
        self.folder_listbox.delete(0, tk.END)
        source = self.source_dir.get()
        if os.path.exists(source):
            f_text = self.filter_text.get().lower()
            try:
                folders = sorted([d for d in os.listdir(source) if os.path.isdir(os.path.join(source, d))])
                for d in folders:
                    if f_text in d.lower(): self.folder_listbox.insert(tk.END, d)
            except: pass

    def _get_history(self, key):
        if not self.config.has_section("History"):
            return []
        raw = self.config.get("History", key, fallback="")
        return [h for h in raw.split("|") if h]
    
    def _set_history(self, key, value):
        hist = [h for h in self._get_history(key) if h]

        if value in hist:
            hist.remove(value)
        hist.insert(0, value)
        hist = hist[:6]

        if not self.config.has_section("History"):
            self.config["History"] = {}

        self.config["History"][key] = "|".join(hist)
        return hist
    
    def load_config(self):
        self.config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            self.config.read(CONFIG_FILE)
            self.source_dir.set(self.config.get("Paths", "source_dir", fallback=""))
            self.dest_dir.set(self.config.get("Paths", "dest_dir", fallback=""))
            self.masters_dir.set(self.config.get("Paths", "masters_dir", fallback=""))
        else:
            self.config["Paths"] = {}

    def save_config(self):
        if not self.config.has_section("Paths"):
            self.config["Paths"] = {}

        self.config["Paths"]["source_dir"] = self.source_dir.get()
        self.config["Paths"]["dest_dir"] = self.dest_dir.get()
        self.config["Paths"]["masters_dir"] = self.masters_dir.get()

        with open(CONFIG_FILE, "w") as f:
            self.config.write(f)

if __name__ == "__main__":
    def on_close():
        app.save_config()
        root.destroy()
        root.quit()
        
    root = tk.Tk()
    app = SymlinkApp(root)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
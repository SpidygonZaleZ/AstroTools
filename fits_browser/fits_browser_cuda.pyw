import os
import sys
import time
import math
import shutil
import configparser
import pandas as pd
import numpy as np
paths_to_add = [
    r"C:\Python311\Lib\site-packages\nvidia\cuda_nvrtc\bin",
    r"C:\Python311\Lib\site-packages\nvidia\cuda_runtime\bin",
    r"C:\Python311\Lib\site-packages\nvidia\cudnn\bin"
]

for p in paths_to_add:
    if os.path.exists(p):
        os.add_dll_directory(p)
        # Dodatkowo dodajemy do PATH dla starszych wersji zależności
        os.environ['PATH'] = p + os.pathsep + os.environ['PATH']

try:
    import cupy as cp
    # Wymuszamy inicjalizację, żeby sprawdzić błędy DLL od razu
    cp.array([1, 2, 3]).sum() 
    CUDA_AVAILABLE = True
    print("CUDA zainicjowane pomyślnie.")
except Exception as e:
    CUDA_AVAILABLE = False
    print(f"Błąd inicjalizacji CUDA: {e}")
from astropy.io import fits
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.widgets import SpanSelector
from matplotlib.ticker import MaxNLocator
from PIL import Image, ImageTk, ImageDraw
import tkinter as tk
from tkinter import filedialog, ttk

def get_config_path(filename):
    if getattr(sys, 'frozen', False):  # uruchomione jako .exe
        app_dir = os.path.dirname(sys.executable)
    else:  # uruchomione jako .py
        app_dir = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(app_dir, filename)

class FITSViewerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("FITS Browser")
        screen_height = self.root.winfo_screenheight()
        min_height = int(screen_height * 0.9)
        self.root.minsize(800, min_height)
        self.root.geometry("+5+5")

        self.folder_path = tk.StringVar()
        self.fits_files = []
        self.current_index = None
        self.reference_file = None
        self.metadata_df = None
        self.debayer_var = tk.BooleanVar(value=True)

        self.config_path = get_config_path("fits_browser.ini")
        self.config = configparser.ConfigParser()

        self.current_image_full = None
        self.reference_image_full = None
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.display_scale = 1.0
        self.max_image_width = 700
        self.max_image_height = 600

        self.create_widgets()
        self.load_config()
        self.update_subfolder()
        self.load_path()

    def create_widgets(self):
        # --- Górny pasek folderu ---
        folder_frame = ttk.Frame(self.root)
        folder_frame.pack(fill="x", padx=10, pady=5)
        ttk.Label(folder_frame, text="Folder:").pack(side="left")
        self.folder_entry = ttk.Entry(folder_frame, textvariable=self.folder_path, width=100)
        self.folder_entry.pack(side="left", padx=5)
        self.folder_entry.bind("<Return>", self.update_folder)
        ttk.Button(folder_frame, text="Browse", command=self.browse_folder).pack(side="left")
        self.subfolder_var = tk.StringVar()
        self.subfolder_combobox = ttk.Combobox(
            folder_frame, textvariable=self.subfolder_var, width=80, state="readonly"
        )
        self.subfolder_combobox.pack(side="left", padx=(5, 0))
        self.subfolder_combobox.bind("<<ComboboxSelected>>", self.load_path)

        # --- Główny kontener ---
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # --- Lewa kolumna z listą plików ---
        self.list_frame = ttk.Frame(main_frame)
        self.list_frame.pack(side="left", fill="both", expand=True)

        # Paski przewijania
        self.scrollbar_y = ttk.Scrollbar(self.list_frame, orient="vertical")
        self.scrollbar_x = ttk.Scrollbar(self.list_frame, orient="horizontal")

        # Listbox
        self.listbox = tk.Listbox(self.list_frame, width=40, height=30,
                                  selectmode=tk.EXTENDED,
                                  yscrollcommand=self.scrollbar_y.set,
                                  xscrollcommand=self.scrollbar_x.set, 
                                  exportselection=False)
        self.listbox.grid(row=0, column=0, sticky="nsew")

        self.scrollbar_y.config(command=self.listbox.yview)
        self.scrollbar_y.grid(row=0, column=1, sticky="ns")

        self.scrollbar_x.config(command=self.listbox.xview)
        self.scrollbar_x.grid(row=1, column=0, sticky="ew")

        # Konfiguracja rozciągania
        self.list_frame.grid_rowconfigure(0, weight=1)  # listbox rośnie pionowo
        self.list_frame.grid_columnconfigure(0, weight=1)  # listbox rośnie poziomo

        # Kontener na label i przycisk w jednej linii
        bottom_frame = ttk.Frame(self.list_frame)
        bottom_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(2, 0))

        self.listbox_label = tk.Label(bottom_frame, text="Space: reject/restore", anchor="w")
        self.listbox_label.pack(side="left")

        self.reference_button = ttk.Button(bottom_frame, text="Set as reference", command=self.set_manual_reference)
        self.reference_button.pack(side="left", padx=(10, 0))

        self.chk_debayer = ttk.Checkbutton(bottom_frame, text="Debayer", variable=self.debayer_var, command=self.apply_processing)
        self.chk_debayer.pack(side="left", padx=(10, 5))
        
        # Dropdown do wyboru metryki na lewej osi
        self.left_axis_label = tk.Label(bottom_frame, text="Plot:", anchor="w")
        self.left_axis_label.pack(side="left")
        self.left_axis_var = tk.StringVar()
        self.left_axis_var.set("ADU")  # domyślna wartość

        self.left_axis_menu = ttk.OptionMenu(
            bottom_frame,
            self.left_axis_var,
            self.left_axis_var.get(),
            "ADU", "HFR", "RMS",
            command=lambda _: self.update_plot()
        )
        self.left_axis_menu.pack(side="left")

        # Panel Image Processing
        self.proc_frame = ttk.LabelFrame(self.list_frame, text="Image processing")
        self.proc_frame.grid(row=4, column=0, columnspan=2, pady=0, sticky="ew")

        # Konfiguracja wag wierszy - tylko listbox rośnie, reszta ma wagę 0
        self.list_frame.grid_rowconfigure(1, weight=0)  # scrollbar poziomy
        self.list_frame.grid_rowconfigure(2, weight=0)  # przycisk
        self.list_frame.grid_rowconfigure(3, weight=0)  # label
        self.list_frame.grid_rowconfigure(4, weight=0)  # panel proc

        # Wiązanie zdarzeń
        self.listbox.bind("<<ListboxSelect>>", self.file_select)
        self.listbox.bind("<space>", self.toggle_reject)
        self.listbox.bind("<Left>", self.select_prev)
        self.listbox.bind("<Right>", self.select_next)

        # --- Panel kontroli procesowania ---
        proc_row = ttk.Frame(self.proc_frame)
        proc_row.pack(padx=5, pady=5)

        ttk.Label(proc_row, text="Lo").pack(side="left")
        self.low_entry = tk.Spinbox(proc_row, from_=0, to=100, increment=0.1, width=4)
        self.low_entry.pack(side="left", padx=(2, 2))
        self.low_entry.delete(0, tk.END)
        self.low_entry.insert(0, "1")

        ttk.Label(proc_row, text="Hi").pack(side="left")
        self.high_entry = tk.Spinbox(proc_row, from_=0, to=100, increment=0.1, width=4)
        self.high_entry.pack(side="left", padx=(2, 2))
        self.high_entry.delete(0, tk.END)
        self.high_entry.insert(0, "99")

        ttk.Label(proc_row, text="Bin").pack(side="left")
        self.binning_var = tk.StringVar()
        self.binning_combo = ttk.Combobox(proc_row, textvariable=self.binning_var, width=2, state="readonly")
        self.binning_combo['values'] = ("x1", "x2", "x4")
        self.binning_combo.current(0)
        self.binning_combo.pack(side="left", padx=(2, 2))

        ttk.Label(proc_row, text="Gamma").pack(side="left")
        self.gamma_entry = tk.Spinbox(proc_row, from_=0.0, to=5.0, increment=0.05, width=4)
        self.gamma_entry.pack(side="left", padx=(2, 2))
        self.gamma_entry.delete(0, tk.END)
        self.gamma_entry.insert(0, "1.0")

        ttk.Button(proc_row, text="Apply", command=self.apply_processing).pack(side="left", padx=(2, 2))

        # Histogram RGB
        self.hist_fig, self.hist_ax = plt.subplots(figsize=(4, 2))
        self.hist_canvas = FigureCanvasTkAgg(self.hist_fig, master=self.proc_frame)
        self.hist_canvas.get_tk_widget().pack(fill="x", padx=5, pady=5)

        # --- Prawa kolumna z obrazami i wykresem ---
        image_plot_frame = ttk.Frame(main_frame)
        image_plot_frame.pack(side="left", padx=10, fill="both", expand=True)

        # Obszar obrazów
        image_frame = ttk.Frame(image_plot_frame)
        image_frame.pack(side="top", pady=5)

        self.image_label = ttk.Label(image_frame)
        self.image_label.grid(row=1, column=0, padx=5)
        self.label_title = ttk.Label(image_frame, text="Current")
        self.label_title.grid(row=0, column=0)

        self.ref_image_label = ttk.Label(image_frame)
        self.ref_image_label.grid(row=1, column=1, padx=5)
        self.label_ref_title = ttk.Label(image_frame, text="Reference")
        self.label_ref_title.grid(row=0, column=1)

        for label in (self.image_label, self.ref_image_label):
            label.bind("<MouseWheel>", self.on_mouse_wheel)
            label.bind("<ButtonPress-1>", self.on_mouse_drag_start)
            label.bind("<B1-Motion>", self.on_mouse_drag_motion)

        # Obszar wykresu i panelu kontrolnego pod obrazami
        plot_frame = ttk.Frame(image_plot_frame)
        plot_frame.pack(side="top", fill="both", expand=True)

        # --- Panel Y-Axis Limits po lewej ---
        self.y1_min_var = tk.StringVar()
        self.y1_max_var = tk.StringVar()
        self.y2_min_var = tk.StringVar()
        self.y2_max_var = tk.StringVar()

        def on_ylim_change(event=None):
            self.update_plot()

        def reset_y_limits():
            self.y1_min_var.set("")
            self.y1_max_var.set("")
            self.y2_min_var.set("")
            self.y2_max_var.set("")
            self.update_plot()

        # --- Panel wejściowy ---
        y_limits_panel = ttk.Frame(plot_frame)
        y_limits_panel.pack(side="left", fill="y", padx=5, pady=5)

        # --- L Max ---
        ttk.Label(y_limits_panel, text="L max").pack(anchor="w", pady=(0,2))
        entry_y1_max = ttk.Entry(y_limits_panel, textvariable=self.y1_max_var, width=5)
        entry_y1_max.pack(anchor="w", pady=(0,5))
        entry_y1_max.bind("<Return>", on_ylim_change)
        entry_y1_max.bind("<FocusOut>", on_ylim_change)

        # --- L Min ---
        ttk.Label(y_limits_panel, text="L min").pack(anchor="w", pady=(0,2))
        entry_y1_min = ttk.Entry(y_limits_panel, textvariable=self.y1_min_var, width=5)
        entry_y1_min.pack(anchor="w", pady=(0,5))
        entry_y1_min.bind("<Return>", on_ylim_change)
        entry_y1_min.bind("<FocusOut>", on_ylim_change)

        # --- R Max ---
        ttk.Label(y_limits_panel, text="R max").pack(anchor="w", pady=(0,2))
        entry_y2_max = ttk.Entry(y_limits_panel, textvariable=self.y2_max_var, width=5)
        entry_y2_max.pack(anchor="w", pady=(0,5))
        entry_y2_max.bind("<Return>", on_ylim_change)
        entry_y2_max.bind("<FocusOut>", on_ylim_change)

        # --- R Min ---
        ttk.Label(y_limits_panel, text="R min").pack(anchor="w", pady=(0,2))
        entry_y2_min = ttk.Entry(y_limits_panel, textvariable=self.y2_min_var, width=5)
        entry_y2_min.pack(anchor="w", pady=(0,5))
        entry_y2_min.bind("<Return>", on_ylim_change)
        entry_y2_min.bind("<FocusOut>", on_ylim_change)

        # --- Przycisk Reset ---
        ttk.Button(y_limits_panel, text="Reset", width=5, command=reset_y_limits).pack(anchor="w", pady=(10, 0))

        # --- Wykres matplotlib obok panelu ---
        plot_canvas_frame = ttk.Frame(plot_frame)
        plot_canvas_frame.pack(side="left", fill="both", expand=True)

        self.fig, self.ax1 = plt.subplots(figsize=(10, 1))
        self.ax2 = self.ax1.twinx()
        self.fig.subplots_adjust(left=0.07, right=0.93, top=0.99, bottom=0.1)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_canvas_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self.plot_click)

        self.selector = SpanSelector(
            self.ax1,
            onselect=self.plot_select,
            direction='horizontal',
            useblit=True,
            button=1,
            minspan=1,
            interactive=True,
            props=dict(
                facecolor='red',
                edgecolor='red',
                alpha=0.3,
                fill=True,
                linestyle='--',
                linewidth=1
            )
        )
        
        # Panel FITS Header (tabela)
        header_panel = ttk.Frame(plot_frame, width=250)
        header_panel.pack(side="left", fill="y", padx=5, pady=5)
        header_panel.grid_propagate(False)  # WYŁĄCZ propagację rozmiaru gridu w panelu

        # Treeview jako tabela bez nagłówków
        self.header_tree = ttk.Treeview(
            header_panel,
            columns=("key", "value"),
            show="",
            height=15
        )
        self.header_tree.grid(row=0, column=0, sticky="nsew")

        # Ustaw kolumny na stałe szerokości i stretch=False
        self.header_tree.column("key", width=90, anchor="w", stretch=False)
        self.header_tree.column("value", width=300, anchor="w", stretch=False)

        # Scrollbary
        header_scrollbar_y = ttk.Scrollbar(header_panel, orient="vertical", command=self.header_tree.yview)
        header_scrollbar_y.grid(row=0, column=1, sticky="ns")

        header_scrollbar_x = ttk.Scrollbar(header_panel, orient="horizontal", command=self.header_tree.xview)
        header_scrollbar_x.grid(row=1, column=0, sticky="ew")

        self.header_tree.configure(
            yscrollcommand=header_scrollbar_y.set,
            xscrollcommand=header_scrollbar_x.set
        )

        # Rozciąganie gridu - kluczowe, żeby Treeview rozciągał się na panel
        header_panel.grid_rowconfigure(0, weight=1)
        header_panel.grid_columnconfigure(0, weight=1)
        
        # Pasek stanu na samym dole
        self.status_frame = tk.Frame(self.root)
        self.status_frame.pack(side="bottom", fill="x")

        self.time_label = tk.Label(self.status_frame, text="Render time: 0ms", fg="blue", anchor="e")
        self.time_label.pack(side="right", padx=10)

    def update_subfolder(self):
        folder = self.folder_path.get()
        subfolders = ["."]
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isdir(path):
                    subfolders.append(name)

        subfolders.sort()
        self.subfolder_combobox['values'] = subfolders

        current = self.subfolder_var.get()
        if current not in subfolders:
            self.subfolder_var.set(".")

    def full_folder(self):
        base_folder = self.folder_path.get()
        subfolder = self.subfolder_var.get() if hasattr(self, 'subfolder_var') else ""

        if subfolder and subfolder != ".":
            return os.path.join(base_folder, subfolder)
        else:
            return base_folder

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.update_subfolder()
            self.subfolder_var.set(".")
            self.load_path()
        self.listbox.focus_set()
        
    def update_folder(self, event):
        folder = self.folder_path.get()
        if os.path.isdir(folder):
            self.update_subfolder()
            self.subfolder_var.set(".")
            self.load_path()
        self.listbox.focus_set()        

    def load_fits_files(self, folder):
        rejected_files = set()
        reject_folder = os.path.join(folder, "reject")

        if self.metadata_df is None:
            # Brak CSV - ładujemy pliki normalnie i z reject, łączymy i sortujemy
            files_normal = [f for f in sorted(os.listdir(folder))
                            if f.lower().endswith((".fit", ".fits")) and os.path.isfile(os.path.join(folder, f))]
            if os.path.isdir(reject_folder):
                rejected_files = set(os.listdir(reject_folder))
                files_reject = [f for f in sorted(os.listdir(reject_folder))
                                if f.lower().endswith((".fit", ".fits"))]
            else:
                files_reject = []
            self.fits_files = files_normal + files_reject
        else:
            # CSV jest - wyciągamy tylko nazwy plików z pełnych ścieżek w CSV
            files_from_csv = [os.path.basename(fp) for fp in self.metadata_df["FilePath"].tolist()]
            self.fits_files = files_from_csv

            if os.path.isdir(reject_folder):
                rejected_files = set(os.listdir(reject_folder))

        self.listbox.delete(0, tk.END)

        for f in self.fits_files:
            self.listbox.insert(tk.END, f)

            path_normal = os.path.join(folder, f)
            path_reject = os.path.join(reject_folder, f)

            if os.path.exists(path_reject):
                self.listbox.itemconfig(tk.END, {'fg': 'red'})
            elif os.path.exists(path_normal):
                self.listbox.itemconfig(tk.END, {'fg': 'black'})
            else:
                self.listbox.itemconfig(tk.END, {'fg': 'gray'})

    def color_list_items(self):
        folder = self.full_folder()
        reject_folder = os.path.join(folder, "reject")
        rejected_files = set()
        if os.path.isdir(reject_folder):
            rejected_files = set(os.listdir(reject_folder))

        for i, file_name in enumerate(self.fits_files):
            if file_name in rejected_files:
                self.listbox.itemconfig(i, fg="red")
            else:
                self.listbox.itemconfig(i, fg="black")

    def load_metadata(self, folder):
        csv_path = os.path.join(folder, "ImageMetaData.csv")

        if os.path.exists(csv_path):
            try:
                self.metadata_df = pd.read_csv(csv_path)
                self.update_reject_column()
                self.update_plot()
            except Exception as e:
                print(f"Error reading ImageMetaData.csv: {e}")
                self.metadata_df = None
                self.ax1.clear()
                self.ax2.clear()
                self.canvas.draw()
        else:
            # Spróbuj znaleźć alternatywny plik *_history.csv
            history_files = [f for f in os.listdir(folder) if f.endswith("_history.csv")]
            if history_files:
                history_path = os.path.join(folder, history_files[0])
                try:
                    df = pd.read_csv(history_path)

                    # Mapowanie kolumn
                    rename_map = {
                        "Filename": "FilePath",
                        "Median": "ADUMedian",
                        "HFR": "HFR",
                        "Rms Total": "GuidingRMS",
                        "Stars": "DetectedStars"
                    }
                    df.rename(columns=rename_map, inplace=True)

                    # Upewnij się, że "FilePath" to pełne ścieżki
                    df["FilePath"] = df["FilePath"].apply(lambda x: os.path.join(folder, os.path.basename(x)))

                    self.metadata_df = df
                    self.update_reject_column()
                    self.update_plot()
                    print(f"Wczytano alternatywny plik: {history_path}")
                except Exception as e:
                    print(f"Error reading history CSV: {e}")
                    self.metadata_df = None
                    self.ax1.clear()
                    self.ax2.clear()
                    self.canvas.draw()
            else:
                self.metadata_df = None
                self.ax1.clear()
                self.ax2.clear()
                self.canvas.draw()

    def file_select(self, event):
        if not self.fits_files:
            return
        
        indices = self.listbox.curselection()  # Zmieniamy na pobranie wszystkich zaznaczonych elementów
        if not indices:
            return
        
        self.current_index = indices[0]  # Możemy nadal ustawić pierwszy zaznaczony indeks jako główny
        file_name = self.fits_files[self.current_index]
        self.show_fits_image(file_name)
        self.update_plot()  # Przekazujemy wszystkie zaznaczone indeksy
        self.listbox.focus_set()

    def toggle_reject(self, event):
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            return

        folder = self.full_folder()
        reject_folder = os.path.join(folder, "reject")
        os.makedirs(reject_folder, exist_ok=True)

        for index in selected_indices:
            file_name = self.fits_files[index]
            src = os.path.join(folder, file_name)
            dst = os.path.join(reject_folder, file_name)
            if not os.path.exists(src) and not os.path.exists(dst):
                continue

            if os.path.exists(dst):  # Już w reject – przywróć
                shutil.move(dst, src)
            elif os.path.exists(src):  # Przenieś do reject
                shutil.move(src, dst)

            # Aktualizacja koloru
            if os.path.exists(os.path.join(reject_folder, file_name)):
                self.listbox.itemconfig(index, fg="red")
            else:
                self.listbox.itemconfig(index, fg="black")

        # Odśwież dane
        self.update_reject_column()
        self.update_plot()

        # Odśwież podgląd pierwszego zaznaczonego
        if len(selected_indices) == 1:
            file_name = self.fits_files[selected_indices[0]]
            self.show_fits_image(file_name)
        else:
            self.show_fits_image(None)
            
        for idx in selected_indices:
            self.listbox.selection_set(idx)
        return "break"        
        self.listbox.focus_set()

    def update_reject_column(self):
        if self.metadata_df is None:
            return

        folder = self.full_folder()
        reject_folder = os.path.join(folder, "reject")
        rejected_files = set()
        if os.path.isdir(reject_folder):
            rejected_files = set(os.listdir(reject_folder))

        def is_rejected(file_path):
            name = os.path.basename(file_path)
            return 1 if name in rejected_files else 0

        def is_not_found(file_path):
            name = os.path.basename(file_path)
            path_normal = os.path.join(folder, name)
            path_reject = os.path.join(reject_folder, name)
            return 1 if (not os.path.exists(path_normal) and not os.path.exists(path_reject)) else 0

        self.metadata_df["Rejected"] = self.metadata_df["FilePath"].apply(is_rejected)
        self.metadata_df["NotFound"] = self.metadata_df["FilePath"].apply(is_not_found)

        csv_path = os.path.join(folder, "ImageMetaData.csv")
        try:
            self.metadata_df.to_csv(csv_path, index=False)
        except Exception as e:
            print(f"Error saving metadata CSV: {e}")

    def select_prev(self, event):
        cur = self.listbox.curselection()
        if cur:
            index = cur[0]
            if index > 0:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(index - 1)
                self.listbox.activate(index - 1)
                self.listbox.see(index - 1)
                self.file_select(None)  # wywołaj aktualizację
        self.listbox.focus_set()

    def select_next(self, event):
        cur = self.listbox.curselection()
        if cur:
            index = cur[0]
            if index < self.listbox.size() - 1:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(index + 1)
                self.listbox.activate(index + 1)
                self.listbox.see(index + 1)
                self.file_select(None)
        self.listbox.focus_set()

    def plot_rgb_histogram(self, rgb_img):
        self.hist_ax.clear()
        if rgb_img is None:
            # brak danych — odśwież i wyjdź
            self.hist_canvas.draw()
            return
            
        colors = ['red', 'green', 'blue']
        labels = ['R', 'G', 'B']

        x = np.arange(256)

        for i, color in enumerate(colors):
            hist, bins = np.histogram(rgb_img[:, :, i].flatten(), bins=256, range=(0, 256))

            # Zamiana zer na np.nan (lub 0 jeśli wolisz minimalną wartość 1)
            hist = hist.astype(float)  # żeby można było użyć nan
            hist[hist == 0] = np.nan

            # Dodajemy 1 tylko tam, gdzie hist != nan, żeby uniknąć log(0)
            hist = np.where(np.isnan(hist), np.nan, hist + 1)

            self.hist_ax.step(x, hist, color=color, label=labels[i], where='mid', linewidth=2)

        self.hist_ax.set_xlabel("Brightness")
        self.hist_ax.set_ylabel("Pixels")
        self.hist_ax.set_yscale("log")
        self.hist_ax.legend(loc="upper right", fontsize=8)
        self.hist_ax.set_xlim(0, 255)

        self.hist_fig.tight_layout()
        self.hist_canvas.draw()

    def render_zoomed(self, img_full):
        w, h = img_full.size
        crop_w = int(w / self.zoom_factor)
        crop_h = int(h / self.zoom_factor)

        if crop_w < 1 or crop_h < 1:
            return img_full

        max_pan_x = w - crop_w
        max_pan_y = h - crop_h

        self.pan_x = max(0, min(self.pan_x, max_pan_x))
        self.pan_y = max(0, min(self.pan_y, max_pan_y))

        x0 = self.pan_x
        y0 = self.pan_y
        x1 = x0 + crop_w
        y1 = y0 + crop_h

        cropped = img_full.crop((x0, y0, x1, y1))

        max_width = self.max_image_width
        max_height = self.max_image_height

        # Oblicz współczynnik skalowania do szerokości i wysokości
        scale_w = max_width / crop_w
        scale_h = max_height / crop_h

        # Użyj najmniejszego, by zmieścić się w oba wymiary
        scale = min(scale_w, scale_h)

        new_w = int(crop_w * scale)
        new_h = int(crop_h * scale)

        resized = cropped.resize((new_w, new_h), Image.BOX)
        # resized = cropped.resize((new_w, new_h), Image.LANCZOS)

        self.display_scale = scale

        return resized

    def on_mouse_wheel(self, event):
        if len(self.listbox.curselection()) != 1:
            return

        delta = 1.1 if event.delta > 0 else 0.9
        new_zoom = self.zoom_factor * delta
        new_zoom = max(1.0, min(new_zoom, 20.0))  # minimalny zoom 1.0, maksymalny 20

        if new_zoom == self.zoom_factor:
            return  # brak zmiany zoomu

        mouse_x = event.x
        mouse_y = event.y

        img_w, img_h = self.current_image_full.size

        crop_w = int(img_w / self.zoom_factor)
        crop_h = int(img_h / self.zoom_factor)
        scale = 600 / crop_h

        cursor_img_x = self.pan_x + mouse_x / scale
        cursor_img_y = self.pan_y + mouse_y / scale

        new_crop_w = int(img_w / new_zoom)
        new_crop_h = int(img_h / new_zoom)

        new_pan_x = cursor_img_x - (mouse_x / (600 / new_crop_h))
        new_pan_y = cursor_img_y - (mouse_y / (600 / new_crop_h))

        max_pan_x = img_w - new_crop_w
        max_pan_y = img_h - new_crop_h

        new_pan_x = max(0, min(new_pan_x, max_pan_x))
        new_pan_y = max(0, min(new_pan_y, max_pan_y))

        self.zoom_factor = new_zoom
        self.pan_x = int(new_pan_x)
        self.pan_y = int(new_pan_y)

        self.update_zoom_view()

    def on_mouse_drag_start(self, event):
        if len(self.listbox.curselection()) != 1:
            return

        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def on_mouse_drag_motion(self, event):
        if len(self.listbox.curselection()) != 1:
            return

        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        self._drag_start_x = event.x
        self._drag_start_y = event.y

        self.pan_x -= int(dx / self.display_scale)
        self.pan_y -= int(dy / self.display_scale)

        img_w, img_h = self.current_image_full.size
        crop_w = int(img_w / self.zoom_factor)
        crop_h = int(img_h / self.zoom_factor)

        max_pan_x = img_w - crop_w
        max_pan_y = img_h - crop_h

        self.pan_x = max(0, min(self.pan_x, max_pan_x))
        self.pan_y = max(0, min(self.pan_y, max_pan_y))

        self.update_zoom_view()

    def update_zoom_view(self):
        if len(self.listbox.curselection()) != 1:
            return
        if self.current_image_full:
            img1 = self.render_zoomed(self.current_image_full)
            img1_tk = ImageTk.PhotoImage(img1)
            self.image_label.configure(image=img1_tk)
            self.image_label.image = img1_tk

        if self.reference_image_full:
            img2 = self.render_zoomed(self.reference_image_full)
            img2_tk = ImageTk.PhotoImage(img2)
            self.ref_image_label.configure(image=img2_tk)
            self.ref_image_label.image = img2_tk
        
        self.label_title.config(text=f"{self.fits_files[self.current_index]} (zoom {round(self.display_scale*100)}%)")

    def _display_blank_image(self, label, color="white", size=(600, 600)):
        img = Image.new("RGB", size, color=color)
        img_tk = ImageTk.PhotoImage(img)
        label.configure(image=img_tk)
        label.image = img_tk

    def _display_cross_image(self, label, size=(600, 600)):
        img = Image.new("RGB", size, color="black")
        draw = ImageDraw.Draw(img)
        w, h = size
        draw.line((0, 0, w, h), fill="red", width=5)
        draw.line((0, h, w, 0), fill="red", width=5)

        img_tk = ImageTk.PhotoImage(img)
        label.configure(image=img_tk)
        label.image = img_tk

    def load_and_display_fits(self, file_name, label, full_image_attr, plot_histogram=False):
        start_time = time.time()
        folder = self.full_folder()
        reject_folder = os.path.join(folder, "reject")

        # Sprawdź czy plik istnieje w głównym folderze lub w reject
        path = os.path.join(folder, file_name)
        is_reject = False
        if not os.path.exists(path):
            path_reject = os.path.join(reject_folder, file_name)
            if os.path.exists(path_reject):
                path = path_reject
                is_reject = True
            else:
                # plik nie istnieje nigdzie – pokaż czarny obraz z czerwonym krzyżem
                self._display_cross_image(label)
                if plot_histogram:
                    self.plot_rgb_histogram(None)
                return

        try:
            with fits.open(path) as hdul:
                data = hdul[0].data
                
                if data is None:
                    return
                if data.ndim > 2:
                    data = data[0]
                self.current_fits_header = hdul[0].header

                # data = np.nan_to_num(data)
                rgb = self.debayer_rggb(data, do_debayer=self.debayer_var.get())

                img = Image.fromarray(rgb)
                setattr(self, full_image_attr, img)
                img = self.render_zoomed(img)

                if is_reject:
                    draw = ImageDraw.Draw(img)
                    w, h = img.size
                    draw.line((0, 0, w, h), fill="red", width=5)
                    draw.line((0, h, w, 0), fill="red", width=5)

                img_tk = ImageTk.PhotoImage(img)
                label.configure(image=img_tk)
                label.image = img_tk

                if plot_histogram:
                    self.plot_rgb_histogram(rgb)
                    
                end_time = time.time()
                elapsed_ms = int((end_time - start_time) * 1000)
                self.time_label.config(text=f"Render time: {elapsed_ms}ms")      

        except Exception as e:
            print(f"Error loading FITS file: {e}")
            self.current_fits_header = None

    def nina_stretch_lut(self, data, low, high, gamma):
        # 1. Przygotowanie tablicy LUT dla 16-bitów (0-65535)
        # Obliczamy to tylko raz na klatkę/kanał zamiast dla każdego piksela
        lut = np.arange(65536, dtype=np.float32)
        
        # 2. Obliczamy progi i gammę na małej tablicy 64k elementów
        np.clip(lut, low, high, out=lut)
        lut = ((lut - low) / (high - low + 1e-9)) ** (1.0 / gamma)
        lut = (lut * 255).astype(np.uint8)

        # 3. Mapowanie - najszybsza możliwa operacja w NumPy
        # Konwersja do uint16 służy jako indeksowanie tablicy LUT
        return lut[data.astype(np.uint16, copy=False)]
        
    def nina_stretch_lut_cuda(self, data_gpu, low, high, gamma):
        """Wykonuje stretching bezpośrednio na GPU (bez LUT)."""
        data_gpu = cp.clip(data_gpu, low, high)
        data_gpu = ((data_gpu - low) / (high - low + 1e-9)) ** (1.0 / gamma)
        return (data_gpu * 255).astype(cp.uint8)

    def debayer_rggb(self, raw, do_debayer=True):
        bin_f = {"x1": 1, "x2": 2, "x4": 4}.get(getattr(self, "binning", "x1"), 1)
        low_p = getattr(self, "low_percent", 1.0)
        high_p = getattr(self, "high_percent", 99.0)
        gam = getattr(self, "gamma", 1.0)
        
        # Statystyki na małej próbce (CPU jest tu b. szybkie)
        sample = raw[::20, ::20]
        low = np.percentile(sample, low_p)
        high = np.percentile(sample, high_p)
        diff = high - low + 1e-9

        # --- CUDA START ---
        if CUDA_AVAILABLE and raw.nbytes > 10**6:
            raw_gpu = cp.asarray(raw)
            
            if do_debayer:
                # Szybki debayering i binning na GPU
                if bin_f == 1:
                    R = raw_gpu[0::2, 0::2]
                    G = (raw_gpu[0::2, 1::2].astype(cp.float32) + raw_gpu[1::2, 0::2]) / 2.0
                    B = raw_gpu[1::2, 1::2]
                else:
                    step = bin_f * 2
                    h_b, w_b = raw_gpu.shape[0] // step, raw_gpu.shape[1] // step
                    view = raw_gpu[:h_b*step, :w_b*step].reshape(h_b, step, w_b, step)
                    R = view[:, 0::2, :, 0::2].mean(axis=(1, 3))
                    G = (view[:, 0::2, :, 1::2].mean(axis=(1, 3)) + view[:, 1::2, :, 0::2].mean(axis=(1, 3))) / 2.0
                    B = view[:, 1::2, :, 1::2].mean(axis=(1, 3))
                
                rgb = cp.stack([R, G, B], axis=2)
            else:
                # Tryb Mono
                if bin_f > 1:
                    h_b, w_b = raw_gpu.shape[0] // bin_f, raw_gpu.shape[1] // bin_f
                    mono = raw_gpu[:h_b*bin_f, :w_b*bin_f].reshape(h_b, bin_f, w_b, bin_f).mean(axis=(1, 3))
                else:
                    mono = raw_gpu
                rgb = cp.stack([mono] * 3, axis=2)

            # Stretching (Stosujemy operacje wektorowe na całym RGB naraz)
            rgb = cp.clip(rgb, low, high)
            rgb = ((rgb - low) / diff) ** (1.0 / gam)
            res = (rgb * 255).astype(cp.uint8)
            
            return cp.asnumpy(res) # Jedyny transfer powrotny
        
        # --- FALLBACK CPU (Twoja stara logika) ---
        else:
            # ... tutaj kod CPU ...
            return result_from_cpu
              
    def show_fits_image(self, file_name=None):
        selected = self.listbox.curselection()
        if len(selected) != 1:
            self._display_blank_image(self.image_label, color="white")
            self.label_title.config(text=f"Selected {len(selected)} images")
            if hasattr(self, "header_tree"):
                self.header_tree.delete(*self.header_tree.get_children())
            return

        if file_name is None or file_name != self.fits_files[selected[0]]:
            file_name = self.fits_files[selected[0]]

        self.load_and_display_fits(
            file_name=file_name,
            label=self.image_label,
            full_image_attr="current_image_full",
            plot_histogram=True
        )

        self.label_title.config(text=f"{file_name} (zoom {round(self.display_scale * 100)}%)")

        # --- Wyświetlenie nagłówka FITS ---
        if hasattr(self, "current_fits_header") and self.current_fits_header is not None:
            self.header_tree.delete(*self.header_tree.get_children())  # wyczyść tabelkę
            for key, value in self.current_fits_header.items():
                self.header_tree.insert("", "end", values=(key, value))

    def show_reference_image(self, file_name):
        self.load_and_display_fits(
            file_name=file_name,
            label=self.ref_image_label,
            full_image_attr="reference_image_full",
            plot_histogram=False
        )

    def set_reference_image(self):
        if self.metadata_df is None or "DetectedStars" not in self.metadata_df.columns:
            return

        df = self.metadata_df.copy()
        folder = self.full_folder()
        reject_folder = os.path.join(folder, "reject")

        # Sortuj malejąco po DetectedStars i wybierz pierwszy istniejący plik
        df_sorted = df.sort_values("DetectedStars", ascending=False)

        for _, row in df_sorted.iterrows():
            file_path = row["FilePath"]
            file_name = os.path.basename(file_path)

            # Sprawdź, czy plik istnieje (w folderze lub reject)
            normal_path = os.path.join(folder, file_name)
            reject_path = os.path.join(reject_folder, file_name)

            if os.path.exists(normal_path) or os.path.exists(reject_path):
                self.reference_file = file_name
                self.show_reference_image(file_name)
                self.label_ref_title.config(text=f"Reference: {file_name}")
                return

        # Jeśli nie znaleziono żadnego pliku
        self.reference_file = None
        self.label_ref_title.config(text="Reference: (none)")
        self.ref_image_label.configure(image="")
        self.ref_image_label.image = None

    def set_manual_reference(self):
        if self.current_index is None:
            return

        file_name = self.fits_files[self.current_index]
        folder = self.full_folder()
        reject_folder = os.path.join(folder, "reject")

        path = os.path.join(folder, file_name)
        if not os.path.exists(path):
            path = os.path.join(reject_folder, file_name)

        if os.path.exists(path):
            self.show_reference_image(path)
            self.label_ref_title.config(text=f"Reference: {file_name}")
        self.listbox.focus_set()

    def apply_processing(self):
        try:
            self.low_percent = float(self.low_entry.get())
            self.high_percent = float(self.high_entry.get())
            self.gamma = float(self.gamma_entry.get())
            self.binning = self.binning_var.get()
        except ValueError:
            print("Incorrect parameter values.")
            return

        self.save_config()

        if self.current_index is not None:
            file_name = self.fits_files[self.current_index]
            self.show_fits_image(file_name)
            if self.reference_file:
                self.show_reference_image(self.reference_file)
        self.listbox.focus_set()

    def update_plot(self):
        # Pobierz aktualnie zaznaczone indeksy w listboxie
        selected_indices = self.listbox.curselection()

        # Jeśli nic nie jest zaznaczone, nie robimy nic
        if not selected_indices:
            return

        # Domyślne wartości – "ADU"
        selected_metric = "ADU"
        y1_label = "ADU Median"
        y1_color = "blue"

        # Jeśli GUI już zainicjowane i dropdown istnieje – pobierz wartość
        if hasattr(self, "left_axis_var"):
            selected_metric = self.left_axis_var.get()

        # Czyszczenie osi
        self.ax1.clear()
        self.ax2.clear()

        # Jeśli mamy dane do rysowania, to generujemy wykres
        if self.metadata_df is not None:
            x = np.arange(len(self.metadata_df))

            # Przypisanie odpowiednich danych i etykiet na podstawie metryki
            if selected_metric == "ADU":
                y1 = self.metadata_df.get("ADUMedian", self.metadata_df.get("Median", np.zeros_like(x)))
                y1_label = "ADU Median"
                y1_color = "blue"
            elif selected_metric == "HFR":
                y1 = self.metadata_df.get("HFR", np.zeros_like(x))
                y1_label = "HFR"
                y1_color = "purple"
            elif selected_metric == "RMS":
                y1 = self.metadata_df.get("GuidingRMS", self.metadata_df.get("Rms Total", np.zeros_like(x)))
                y1_label = "RMS"
                y1_color = "saddlebrown"
            else:
                y1 = np.zeros_like(x)
                y1_label = ""
                y1_color = "gray"
                
                # Ustaw podpisy osi i kolory PO wyznaczeniu y1_label/y1_color
            self.ax1.set_ylabel(y1_label, color=y1_color)
            self.ax1.tick_params(axis="y", labelcolor=y1_color)
            self.ax1.set_zorder(2)
            self.ax1.patch.set_visible(False)

            y2 = self.metadata_df.get("DetectedStars", np.zeros_like(x))
            self.ax2.set_ylabel("Detected Stars", color="green")
            self.ax2.tick_params(axis="y", labelcolor="green")
            self.ax2.yaxis.set_label_position("right")
            self.ax2.yaxis.tick_right()
            self.ax2.set_zorder(1)
            self.ax2.patch.set_visible(False)
            
            rejects = self.metadata_df.get("Rejected", pd.Series([0] * len(x)))
            not_found = self.metadata_df.get("NotFound", pd.Series([0] * len(x)))

            # Wykresy – ADU Median i Detected Stars
            self.ax1.plot(x, y1, color=y1_color, marker="o")
            self.ax2.plot(x, y2, color="green", marker="o")
            self.ax1.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=20))

            # Rysowanie "X" dla odrzuconych (Rejected) i nieznalezionych (NotFound) punktów — na obu osiach
            for i in range(len(x)):
                if rejects[i] == 1:
                    # Białe kółko na ax1 i ax2
                    self.ax1.plot(i, y1[i], marker='o', color='white', alpha=0.6, markersize=7, markeredgecolor='red', markeredgewidth=1)
                    self.ax2.plot(i, y2[i], marker='o', color='white', alpha=0.6, markersize=7, markeredgecolor='red', markeredgewidth=1)
                if not_found[i] == 1:
                    # Białe kółko z szarą obwódką
                    self.ax1.plot(i, y1[i], marker='o', color='white', alpha=0.9, markersize=7, markeredgecolor='gray', markeredgewidth=1.5)
                    self.ax2.plot(i, y2[i], marker='o', color='white', alpha=0.9, markersize=7, markeredgecolor='gray', markeredgewidth=1.5)

            # Pionowe linie i adnotacje dla zaznaczonych
            for index in selected_indices:
                index = int(index)
                if 0 <= index < len(x):
                    self.ax1.axvline(index, color="black", linestyle="--", linewidth=0.5)                    
                    if len(selected_indices) == 1:
                        # Adnotacja: ADUMedian / HFR / RMS
                        y_val1 = y1[index]
                        label_text = f"{y_val1:.2f}" if selected_metric in ("HFR", "RMS") else f"{y_val1:.0f}"
                        self.ax1.annotate(label_text,
                                         (index, y_val1),
                                         textcoords="offset points",
                                         xytext=(5, 5),
                                         ha='left',
                                         va='center',
                                         fontsize=8,
                                         color=y1_color,
                                         bbox=dict(
                                                boxstyle="round,pad=0.2",
                                                fc="white",
                                                ec="none",
                                                alpha=0.8
                                            )
                                         )
                        # Adnotacja: DetectedStars
                        y_val2 = y2[index]
                        self.ax2.annotate(f"{y_val2:.0f}",
                                         (index, y_val2),
                                         textcoords="offset points",
                                         xytext=(-5, -5),
                                         ha='right',
                                         va='center',
                                         fontsize=8,
                                         color="darkgreen",
                                             bbox=dict(
                                                boxstyle="round,pad=0.2",
                                                fc="white",
                                                ec="none",
                                                alpha=0.8
                                            )
                                         )
            # Axis limits
            try:
                y1_min = float(self.y1_min_var.get()) if self.y1_min_var.get() else None
                y1_max = float(self.y1_max_var.get()) if self.y1_max_var.get() else None
                y2_min = float(self.y2_min_var.get()) if self.y2_min_var.get() else None
                y2_max = float(self.y2_max_var.get()) if self.y2_max_var.get() else None

                if y1_min is not None or y1_max is not None:
                    self.ax1.set_ylim(bottom=y1_min, top=y1_max)

                if y2_min is not None or y2_max is not None:
                    self.ax2.set_ylim(bottom=y2_min, top=y2_max)
            except ValueError:
                pass  # ignorujemy błędne wpisy

            self.canvas.draw()
        self.listbox.focus_set()

    def plot_click(self, event):
        if event.inaxes not in self.fig.axes:
            return

        if event.xdata is None:
            return  # Kliknięcie poza obszarem danych

        clicked_index = int(round(event.xdata))

        if 0 <= clicked_index < len(self.fits_files):
            self.current_index = clicked_index
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(clicked_index)
            self.listbox.activate(clicked_index)
            self.listbox.see(clicked_index)

            file_name = self.fits_files[clicked_index]
            self.show_fits_image(file_name)
            self.update_plot()
        self.listbox.focus_set()

    def plot_select(self, xmin, xmax):
        x1, x2 = sorted([xmin, xmax])
        
        i1 = int(math.ceil(x1))
        i2 = int(math.floor(x2))

        i1 = max(0, min(i1, len(self.fits_files) - 1))
        i2 = max(0, min(i2, len(self.fits_files) - 1))

        if i1 <= i2:
            self.listbox.selection_clear(0, tk.END)
            for i in range(i1, i2 + 1):
                self.listbox.selection_set(i)

            self.listbox.see(i1)
            self.listbox.activate(i1)
            
            file_name = self.fits_files[i1]
            self.show_fits_image(file_name)
            self.update_plot()
        else:
            # Jeśli zaznaczenie nie zawiera żadnego punktu
            self.listbox.selection_clear(0, tk.END)
        self.listbox.focus_set()

    def load_path(self, event=None):
        folder = self.full_folder()           
        if os.path.isdir(folder):
            self.load_metadata(folder)   # najpierw metadane
            self.load_fits_files(folder) # potem pliki (bazując na metadanych)

            if self.fits_files:
                self.current_index = 0
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(0)
                self.listbox.activate(0)
                self.listbox.see(0)
                file_name = self.fits_files[0]
                self.show_fits_image(file_name)
                self.update_plot()
                self.set_reference_image()
        self.listbox.focus_set()

    def load_config(self):
        # Domyślne wartości, niezależne od pliku ini
        self.low_percent = 1.0
        self.high_percent = 99.0
        self.gamma = 1.0
        self.binning = "x1"
        default_subfolder = "."

        if os.path.exists(self.config_path):
            self.config.read(self.config_path)
            self.folder_path.set(self.config.get("LastSession", "folder", fallback=""))
            self.subfolder_var.set(self.config.get("LastSession", "subfolder", fallback=default_subfolder))
            self.debayer_var.set(self.config.getboolean("LastSession", "debayer", fallback=True))
            self.low_percent = self.config.getfloat("LastSession", "low_percent", fallback=self.low_percent)
            self.high_percent = self.config.getfloat("LastSession", "high_percent", fallback=self.high_percent)
            self.gamma = self.config.getfloat("LastSession", "gamma", fallback=self.gamma)
            self.binning = self.config.get("LastSession", "binning", fallback=self.binning)

        # <- AKTUALIZUJ KONTROLKI:
        if hasattr(self, "low_entry"):
            self.low_entry.delete(0, tk.END)
            self.low_entry.insert(0, str(self.low_percent))

        if hasattr(self, "high_entry"):
            self.high_entry.delete(0, tk.END)
            self.high_entry.insert(0, str(self.high_percent))

        if hasattr(self, "gamma_entry"):
            self.gamma_entry.delete(0, tk.END)
            self.gamma_entry.insert(0, str(self.gamma))

        if hasattr(self, "binning_var"):
            self.binning_var.set(self.binning)
        
        if hasattr(self, "subfolder_combobox"):
            self.subfolder_combobox.set(self.subfolder_var.get())

    def save_config(self):
        self.config["LastSession"] = {
            "folder": self.folder_path.get(),
            "subfolder": self.subfolder_var.get() if hasattr(self, "subfolder_var") else ".",
            "debayer": self.debayer_var.get(),
            "low_percent": getattr(self, "low_percent", 1.0),
            "high_percent": getattr(self, "high_percent", 99.0),
            "gamma": getattr(self, "gamma", 1.0),
            "binning": getattr(self, "binning", "x1")
        }
        with open(self.config_path, "w") as f:
            self.config.write(f)

if __name__ == "__main__":
    def on_close():
        app.save_config()
        root.destroy()
        root.quit()

    root = tk.Tk()
    app = FITSViewerApp(root)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

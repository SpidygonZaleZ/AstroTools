import os
from astropy.io import fits

# --- KONFIGURACJA ---
folder_path = r"d:\astro-img\img-i3\NINA\2026-05-09_NGC6853_DiaboloNebula_EdgeHD8_ATR2600C"
# --------------------

# Sprawdź czy folder istnieje
if not os.path.exists(folder_path):
    print(f"Błąd: Folder {folder_path} nie istnieje!")
else:
    # Pobierz listę plików kończących się na .fits lub .fit
    files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.fits', '.fit'))]
    
    print(f"Znaleziono {len(files)} plików FITS. Rozpoczynam sprawdzanie...")

    for filename in files:
        # Pełna ścieżka do pliku
        file_path = os.path.join(folder_path, filename)
        
        # Zapisz oryginalne czasy pliku
        stat = os.stat(file_path)
        atime = stat.st_atime
        mtime = stat.st_mtime

        try:
            # Otwórz FITS w trybie update
            with fits.open(file_path, mode="update") as hdul:
                hdr = hdul[0].header
                
                # Sprawdź czy klucz istnieje i czy wymaga poprawki
                if "FILTER" in hdr and hdr["FILTER"] == "BB":
                    hdr["FILTER"] = "DB"
                    print(f"Zmieniono {filename}: BB -> DB")
                    hdul.flush()  # Zapisz zmiany tylko jeśli wystąpiła zmiana
                
            # Przywróć oryginalne czasy modyfikacji
            os.utime(file_path, (atime, mtime))
            
        except Exception as e:
            print(f"Błąd przy pliku {filename}: {e}")

    print("Gotowe!")
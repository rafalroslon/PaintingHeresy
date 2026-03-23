"""
PaintingHeresy Launcher — automatyczny updater
Plik: launcher.py
Buduj: py -3.11 -m pyinstaller launcher.spec
"""

import sys
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk
import requests
import json
import time

# ═══════════════════════════════════════════════
#  KONFIGURACJA
# ═══════════════════════════════════════════════

APP_VERSION  = "1.0.0"
UPDATE_URL   = "https://web-production-ca07e.up.railway.app/version"
APP_EXE      = "PaintingHeresy_app.exe"   # właściwa aplikacja
LAUNCHER_EXE = "PaintingHeresy.exe"       # ten launcher

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) \
           else os.path.dirname(os.path.abspath(__file__))

APP_PATH     = os.path.join(BASE_DIR, APP_EXE)
TEMP_PATH    = os.path.join(BASE_DIR, "_update_temp.exe")
VERSION_FILE = os.path.join(BASE_DIR, "_version.txt")

# ═══════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════

def get_local_version():
    try:
        with open(VERSION_FILE, 'r') as f:
            return f.read().strip()
    except Exception:
        return APP_VERSION

def save_local_version(version):
    try:
        with open(VERSION_FILE, 'w') as f:
            f.write(version)
    except Exception:
        pass

def version_gt(v1, v2):
    try:
        a = [int(x) for x in v1.split('.')]
        b = [int(x) for x in v2.split('.')]
        return a > b
    except Exception:
        return False

def launch_app():
    """Uruchom główną aplikację i zamknij launcher"""
    if os.path.exists(APP_PATH):
        subprocess.Popen([APP_PATH], cwd=BASE_DIR)
    else:
        tk.messagebox.showerror(
            "Błąd",
            f"Nie znaleziono {APP_EXE}!\nUpewnij się że plik jest w tym samym folderze."
        )
        return
    sys.exit(0)

# ═══════════════════════════════════════════════
#  LAUNCHER UI
# ═══════════════════════════════════════════════

class LauncherApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Painting Heresy Launcher")
        self.root.geometry("480x280")
        self.root.resizable(False, False)
        self.root.configure(bg="#0e0e1a")
        self.root.overrideredirect(False)

        # Wycentruj okno
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - 480) // 2
        y = (self.root.winfo_screenheight() - 280) // 2
        self.root.geometry(f"480x280+{x}+{y}")

        self._build_ui()
        self.download_done   = False
        self.update_data     = None
        self.download_thread = None

    def _build_ui(self):
        # Tytuł
        tk.Label(self.root,
                 text="⚔  PAINTING HERESY",
                 font=("Segoe UI", 18, "bold"),
                 fg="#c9a84c", bg="#0e0e1a").pack(pady=(28, 4))

        tk.Label(self.root,
                 text="LAUNCHER",
                 font=("Segoe UI", 9),
                 fg="#7a7a96", bg="#0e0e1a").pack()

        # Separator
        tk.Frame(self.root, bg="#c9a84c", height=1).pack(fill="x", padx=40, pady=(12, 16))

        # Status
        self.status_var = tk.StringVar(value="Checking for updates...")
        tk.Label(self.root,
                 textvariable=self.status_var,
                 font=("Segoe UI", 10),
                 fg="#a0a0b0", bg="#0e0e1a").pack()

        # Pasek postępu
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Gold.Horizontal.TProgressbar",
                        troughcolor="#1e1e2e",
                        background="#c9a84c",
                        bordercolor="#1e1e2e",
                        lightcolor="#c9a84c",
                        darkcolor="#c9a84c")

        self.progress = ttk.Progressbar(
            self.root,
            style="Gold.Horizontal.TProgressbar",
            orient="horizontal",
            length=380,
            mode="indeterminate"
        )
        self.progress.pack(pady=(12, 8))
        self.progress.start(12)

        # Przyciski (ukryte na start)
        self.btn_frame = tk.Frame(self.root, bg="#0e0e1a")
        self.btn_frame.pack(pady=(8, 0))

        self.btn_later = tk.Button(
            self.btn_frame,
            text="Launch without update",
            font=("Segoe UI", 9),
            fg="#7a7a96", bg="#1e1e2e",
            activeforeground="#ffffff",
            activebackground="#2a2a3e",
            bd=0, padx=16, pady=8,
            cursor="hand2",
            command=self._launch_without_update
        )

        self.btn_restart = tk.Button(
            self.btn_frame,
            text="⚔  Restart & Install Update",
            font=("Segoe UI", 10, "bold"),
            fg="#0e0e1a", bg="#c9a84c",
            activeforeground="#0e0e1a",
            activebackground="#f0c84a",
            bd=0, padx=20, pady=10,
            cursor="hand2",
            command=self._install_update
        )

        # Wersja
        local_ver = get_local_version()
        tk.Label(self.root,
                 text=f"v{local_ver}",
                 font=("Segoe UI", 8),
                 fg="#3a3a58", bg="#0e0e1a").pack(side="bottom", pady=8)

    def _set_status(self, text):
        self.root.after(0, lambda: self.status_var.set(text))

    def _show_update_ready(self, new_version):
        def _update():
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress["value"] = 100
            self.status_var.set(f"Update v{new_version} ready to install!")
            self.btn_later.pack(side="left", padx=(0, 10))
            self.btn_restart.pack(side="left")
        self.root.after(0, _update)

    def _show_no_update(self):
        def _update():
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.progress["value"] = 100
            self.status_var.set("You're up to date! Launching...")
        self.root.after(0, _update)
        self.root.after(800, lambda: self.root.after(0, launch_app))

    def _show_error(self, msg):
        def _update():
            self.progress.stop()
            self.status_var.set(f"Update check failed — launching anyway...")
        self.root.after(0, _update)
        self.root.after(1200, lambda: self.root.after(0, launch_app))

    def _launch_without_update(self):
        # Usuń pobrany plik tymczasowy
        if os.path.exists(TEMP_PATH):
            try:
                os.remove(TEMP_PATH)
            except Exception:
                pass
        launch_app()

    def _install_update(self):
        if not os.path.exists(TEMP_PATH):
            launch_app()
            return

        new_version = self.update_data.get('version', '') if self.update_data else ''

        # Skrypt bat który podmieni plik i uruchomi nową wersję
        bat_path = os.path.join(BASE_DIR, "_update.bat")
        bat_content = f"""@echo off
timeout /t 2 /nobreak >nul
move /y "{TEMP_PATH}" "{APP_PATH}"
start "" "{APP_PATH}"
del "%~f0"
"""
        with open(bat_path, 'w') as f:
            f.write(bat_content)

        if new_version:
            save_local_version(new_version)

        subprocess.Popen(
            ['cmd', '/c', bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        sys.exit(0)

    def _check_and_download(self):
        try:
            # Sprawdź wersję
            self._set_status("Checking for updates...")
            resp = requests.get(UPDATE_URL, timeout=8,
                               headers={'User-Agent': f'PaintingHeresy/{APP_VERSION}'})
            data = resp.json()

            remote_version = data.get('version', '0.0.0')
            local_version  = get_local_version()

            if not version_gt(remote_version, local_version):
                self._show_no_update()
                return

            # Jest aktualizacja — pobierz
            download_url = data.get('download_url', '')
            if not download_url:
                self._show_no_update()
                return

            self.update_data = data
            self._set_status(f"Downloading v{remote_version}...")

            # Pobierz plik z paskiem postępu
            self.root.after(0, lambda: self.progress.configure(mode="determinate"))
            r = requests.get(download_url, stream=True, timeout=60)
            total    = int(r.headers.get('content-length', 0))
            downloaded = 0

            with open(TEMP_PATH, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int(downloaded / total * 100)
                            self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                            self.root.after(0, lambda p=pct: self.status_var.set(
                                f"Downloading v{remote_version}... {p}%"))

            self.download_done = True
            self._show_update_ready(remote_version)

        except Exception as e:
            self._show_error(str(e))

    def run(self):
        # Uruchom sprawdzanie w wątku
        t = threading.Thread(target=self._check_and_download, daemon=True)
        t.start()
        self.root.mainloop()


# ═══════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════

if __name__ == '__main__':
    app = LauncherApp()
    app.run()

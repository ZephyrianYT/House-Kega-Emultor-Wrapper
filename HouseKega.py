#!/usr/bin/env python3
"""
HouseKega first-launch wizard + launcher (single file)

- First run: asks for ROM folder, scans, normalizes names, logs results.
- Then asks for Kega Fusion (fusion.exe).
- Opens main GUI with game list and Launch functionality.

Requirements: Python 3.10+, PySide6.
"""

from __future__ import annotations
import sys, os, json, logging, subprocess, traceback
from pathlib import Path
from typing import Optional, List, Dict

# Force working directory to script directory so double-click works
SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(str(SCRIPT_DIR))

# Paths
HK_DIR = SCRIPT_DIR / "HouseKega"
CONFIG_DIR = HK_DIR / "Config"
LOG_DIR = HK_DIR / "Logs"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
SCAN_LOG = LOG_DIR / "scan.log"

# Ensure directories
for d in (HK_DIR, CONFIG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(filename=str(SCAN_LOG), level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Supported extensions for Kega Fusion (cartridges and discs)
SUPPORTED_EXTS = {
    ".bin", ".md", ".smd", ".32x", ".gg", ".sms",    # cartridges
    ".iso", ".cue", ".chd"                            # disc images (Sega CD)
}

DEFAULT_SETTINGS = {
    "version": "0.4",
    "fusion_path": "",
    "rom_root": "",
    "include_subfolders": True,
    "auto_scan": True
}

def load_settings() -> dict:
    try:
        if not SETTINGS_FILE.exists():
            SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, indent=4), encoding="utf-8")
            return dict(DEFAULT_SETTINGS)
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        for k,v in DEFAULT_SETTINGS.items():
            data.setdefault(k,v)
        return data
    except Exception:
        # backup corrupted file
        try:
            SETTINGS_FILE.rename(SETTINGS_FILE.with_suffix(".json.corrupt"))
        except Exception:
            pass
        SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, indent=4), encoding="utf-8")
        return dict(DEFAULT_SETTINGS)

def save_settings(s: dict):
    SETTINGS_FILE.write_text(json.dumps(s, indent=4), encoding="utf-8")

def normalize_path(p) -> Path:
    try:
        return Path(p).expanduser().resolve()
    except Exception:
        return Path(p)

def is_executable_file(p: Path) -> bool:
    try:
        return p.is_file() and (p.suffix.lower() in [".exe", ".app"] or os.access(str(p), os.X_OK))
    except Exception:
        return False

# Best-effort normalization: remove common tokens, replace underscores, trim headers
def normalize_name_from_filename(fn: str) -> str:
    name = Path(fn).stem
    # common header patterns to strip
    for token in ["(U)", "(E)", "(J)", "[!]", "[b]", "[t+f]"]:
        name = name.replace(token, "")
    name = name.replace("_", " ").replace("-", " ").strip()
    # collapse multiple spaces
    name = " ".join(name.split())
    # Title case
    return name.title()

# Stub: placeholder for DAT/DB verification (No-Intro/Redump)
# You can implement DAT parsing and checksum verification here.
def verify_against_db_stub(file_path: Path) -> Dict[str, Optional[str]]:
    # returns dict: {"status": "unknown"|"verified", "canonical_name": str or None, "db": "no-intro"|"redump"|None}
    # For now, we return unknown and suggested normalized name
    return {"status": "unknown", "canonical_name": normalize_name_from_filename(file_path.name), "db": None}

# Scanning function
def scan_rom_folder(rom_root: Path, include_subfolders: bool=True) -> List[Dict]:
    results = []
    if not rom_root.exists():
        return results
    iterator = rom_root.rglob("*") if include_subfolders else rom_root.iterdir()
    for p in iterator:
        try:
            if not p.is_file():
                continue
            if p.suffix.lower() in SUPPORTED_EXTS:
                info = verify_against_db_stub(p)
                entry = {
                    "path": str(p),
                    "filename": p.name,
                    "suggested_name": info.get("canonical_name"),
                    "status": info.get("status"),
                    "db": info.get("db")
                }
                results.append(entry)
                logging.info("Found: %s -> %s (%s)", p, entry["suggested_name"], entry["status"])
        except Exception as e:
            logging.exception("Scan error for %s: %s", p, e)
    return results

# GUI code (PySide6)
def ensure_pyside6() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except Exception:
        print("PySide6 is required. Install now? (y/N): ", end="")
        ans = input().strip().lower()
        if ans == "y":
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "PySide6"])
                import PySide6  # noqa: F401
                return True
            except Exception as e:
                print("Failed to install PySide6:", e)
                return False
        return False

if not ensure_pyside6():
    print("PySide6 not available. Exiting.")
    sys.exit(1)

from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QVBoxLayout, QWidget, QProgressBar, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QTimer

# First-launch wizard dialogs
class RomFolderDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Set ROM Directory")
        self.settings = settings
        self.selected = None
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.rom_edit = QLineEdit(settings.get("rom_root", ""))
        browse_btn = QPushButton("Browse")
        h = QHBoxLayout()
        h.addWidget(self.rom_edit)
        h.addWidget(browse_btn)
        form.addRow("ROM folder:", h)
        self.sub_chk = QPushButton("Include subfolders")
        self.sub_chk.setCheckable(True)
        self.sub_chk.setChecked(settings.get("include_subfolders", True))
        form.addRow("", self.sub_chk)
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        ok = QPushButton("Next: Scan")
        cancel = QPushButton("Cancel")
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)
        browse_btn.clicked.connect(self.on_browse)
        ok.clicked.connect(self.on_ok)
        cancel.clicked.connect(self.reject)

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select ROM Folder", str(SCRIPT_DIR))
        if folder:
            self.rom_edit.setText(str(folder))

    def on_ok(self):
        path = self.rom_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "Select ROM folder", "Please select a ROM folder to continue.")
            return
        self.settings["rom_root"] = str(normalize_path(path))
        self.settings["include_subfolders"] = bool(self.sub_chk.isChecked())
        save_settings(self.settings)
        self.selected = self.settings["rom_root"]
        self.accept()

class ScanDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Scanning ROMs")
        self.settings = settings
        self.results = []
        self.resize(700, 400)
        layout = QVBoxLayout(self)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, stretch=1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Filename", "Suggested Name", "Status", "DB"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table, stretch=2)
        btn_row = QHBoxLayout()
        done = QPushButton("Done")
        done.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(done)
        layout.addLayout(btn_row)
        QTimer.singleShot(100, self.start_scan)

    def start_scan(self):
        rom_root = Path(self.settings.get("rom_root", ""))
        include_sub = bool(self.settings.get("include_subfolders", True))
        self.log.append(f"Scanning {rom_root} (subfolders={include_sub})...")
        results = scan_rom_folder(rom_root, include_sub)
        self.results = results
        self.progress.setMaximum(max(1, len(results)))
        for i, r in enumerate(results, start=1):
            self.log.append(f"Found: {r['filename']} -> {r['suggested_name']} ({r['status']})")
            self.table.insertRow(self.table.rowCount())
            self.table.setItem(self.table.rowCount()-1, 0, QTableWidgetItem(r['filename']))
            self.table.setItem(self.table.rowCount()-1, 1, QTableWidgetItem(r['suggested_name'] or ""))
            self.table.setItem(self.table.rowCount()-1, 2, QTableWidgetItem(r['status'] or ""))
            self.table.setItem(self.table.rowCount()-1, 3, QTableWidgetItem(r['db'] or ""))
            self.progress.setValue(i)
        self.log.append(f"Scan complete: {len(results)} items found.")
        logging.info("Scan complete: %d items", len(results))

class FusionSelectDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Select Kega Fusion Executable")
        self.settings = settings
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fusion_edit = QLineEdit(settings.get("fusion_path", ""))
        browse = QPushButton("Browse")
        h = QHBoxLayout()
        h.addWidget(self.fusion_edit)
        h.addWidget(browse)
        form.addRow("Fusion exe:", h)
        layout.addLayout(form)
        btn_row = QHBoxLayout()
        ok = QPushButton("Finish")
        cancel = QPushButton("Cancel")
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)
        browse.clicked.connect(self.on_browse)
        ok.clicked.connect(self.on_ok)
        cancel.clicked.connect(self.reject)

    def on_browse(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Select Fusion Executable", str(SCRIPT_DIR), "Executables (*.exe);;All Files (*)")
        if fn:
            self.fusion_edit.setText(str(fn))

    def on_ok(self):
        p = self.fusion_edit.text().strip()
        if not p or not is_executable_file(Path(p)):
            QMessageBox.warning(self, "Invalid executable", "Please select a valid Fusion executable.")
            return
        self.settings["fusion_path"] = str(normalize_path(p))
        save_settings(self.settings)
        self.accept()

# Main launcher window
class MainWindow(QMainWindow):
    def __init__(self, settings, scan_results):
        super().__init__()
        self.settings = settings
        self.scan_results = scan_results
        self.setWindowTitle("HouseKega")
        self.resize(900, 600)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("<b>HouseKega</b>"))
        status_box = QGroupBox("Status")
        sv = QVBoxLayout()
        sv.addWidget(QLabel(f"Fusion: {settings.get('fusion_path','(not set)')}"))
        sv.addWidget(QLabel(f"ROM folder: {settings.get('rom_root','(not set)')}"))
        status_box.setLayout(sv)
        layout.addWidget(status_box)
        self.list = QListWidget()
        for r in scan_results:
            item = QListWidgetItem(r['suggested_name'] or r['filename'])
            item.setData(Qt.UserRole, r['path'])
            self.list.addItem(item)
        layout.addWidget(self.list, stretch=1)
        btn_row = QHBoxLayout()
        launch_btn = QPushButton("Launch Selected")
        browse_btn = QPushButton("Change ROM Folder")
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        btn_row.addWidget(launch_btn)
        layout.addLayout(btn_row)
        launch_btn.clicked.connect(self.on_launch)
        browse_btn.clicked.connect(self.on_change_rom_folder)
        self.list.itemDoubleClicked.connect(self.on_double_click)

    def on_double_click(self, item):
        path = item.data(Qt.UserRole)
        self.launch_with_fusion(path)

    def on_launch(self):
        sel = self.list.currentItem()
        if not sel:
            QMessageBox.information(self, "Select a game", "Please select a game to launch.")
            return
        path = sel.data(Qt.UserRole)
        self.launch_with_fusion(path)

    def launch_with_fusion(self, rom_path):
        fusion = self.settings.get("fusion_path", "")
        if not fusion or not is_executable_file(Path(fusion)):
            QMessageBox.warning(self, "Fusion not set", "Please set the Fusion executable first.")
            return
        ok = launch_fusion_from_path(fusion, rom_path)
        if not ok:
            QMessageBox.critical(self, "Launch failed", "Failed to launch Fusion. Check logs.")
        else:
            QMessageBox.information(self, "Launched", "Fusion launched with selected ROM.")

    def on_change_rom_folder(self):
        dlg = RomFolderDialog(self.settings)
        if dlg.exec():
            # re-scan and update list
            scan_dlg = ScanDialog(self.settings)
            scan_dlg.exec()
            self.list.clear()
            for r in scan_dlg.results:
                item = QListWidgetItem(r['suggested_name'] or r['filename'])
                item.setData(Qt.UserRole, r['path'])
                self.list.addItem(item)

# Helper to launch fusion detached
def launch_fusion_from_path(fusion_path: str | Path, rom_path: Optional[str | Path] = None) -> bool:
    fusion = normalize_path(fusion_path)
    if not is_executable_file(fusion):
        logging.error("Fusion not executable: %s", fusion)
        return False
    cmd = [str(fusion)]
    if rom_path:
        cmd.append(str(normalize_path(rom_path)))
    try:
        if sys.platform.startswith("win"):
            DETACHED = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd, cwd=str(fusion.parent), close_fds=True, creationflags=DETACHED)
        else:
            subprocess.Popen(cmd, cwd=str(fusion.parent), close_fds=True)
        logging.info("Launched Fusion: %s %s", fusion, rom_path or "")
        return True
    except Exception as e:
        logging.exception("Launch error: %s", e)
        return False

# First-run flow
def first_launch_flow(settings):
    # 1) ROM folder selection
    if not settings.get("rom_root"):
        dlg = RomFolderDialog(settings)
        if dlg.exec() != QDialog.Accepted:
            return None, None
    # 2) Scan
    scan_dlg = ScanDialog(settings)
    scan_dlg.exec()
    results = scan_dlg.results
    # 3) Fusion selection
    if not settings.get("fusion_path") or not is_executable_file(Path(settings.get("fusion_path",""))):
        fdlg = FusionSelectDialog(settings)
        if fdlg.exec() != QDialog.Accepted:
            return results, settings
    return results, settings

# Application entry
def main():
    settings = load_settings()
    app = QApplication(sys.argv)
    # If no rom_root or first-run, run wizard
    if not settings.get("rom_root") or not settings.get("fusion_path"):
        results, settings = first_launch_flow(settings)
        if results is None:
            print("User cancelled setup.")
            sys.exit(0)
    else:
        # auto-scan if requested
        if settings.get("auto_scan", True):
            results = scan_rom_folder(Path(settings.get("rom_root")), settings.get("include_subfolders", True))
        else:
            results = []
    # Open main window
    win = MainWindow(settings, results)
    win.show()
    app.exec()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        LOG = LOG_DIR / "launcher_error.log"
        LOG.write_text("".join(traceback.format_exception(type(e), e, e.__traceback__)), encoding="utf-8")
        print("Launcher crashed. See log:", LOG)
        raise

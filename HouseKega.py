#!/usr/bin/env python3
"""
HouseKega first-launch wizard + launcher (single file)

- First run: asks for ROM folder, scans, normalizes names, logs results.
- Then asks for Kega Fusion (fusion.exe).
- Opens main GUI with game list and Launch functionality.

Requirements: Python 3.10+, PySide6.
"""

from __future__ import annotations
import sys, os, re, json, time, logging, subprocess, traceback
from pathlib import Path
from typing import Callable, Optional, List, Dict

# Force working directory to script directory so double-click works
SCRIPT_DIR = Path(__file__).parent.resolve()
os.chdir(str(SCRIPT_DIR))

# Paths
HK_DIR = SCRIPT_DIR / "HouseKega"
CONFIG_DIR = HK_DIR / "Config"
LOG_DIR = HK_DIR / "Logs"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
APP_LOG = LOG_DIR / "housekega.log"
ERROR_LOG = LOG_DIR / "launcher_error.log"

IS_WINDOWS = sys.platform.startswith("win")

# Ensure directories
for d in (HK_DIR, CONFIG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Logging
logging.basicConfig(filename=str(APP_LOG), level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Supported extensions for Kega Fusion (cartridges and discs)
SUPPORTED_EXTS = {
    ".bin", ".gen", ".md", ".smd", ".32x", ".gg", ".sms", ".sg", ".zip",  # cartridges
    ".iso", ".cue"                                                         # disc images (Sega CD)
}

# Executable names looked for next to this script on first run
LOCAL_FUSION_NAMES = ["Fusion.exe", "fusion.exe", "Fusion.app", "Kega Fusion.app"]

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
        if not isinstance(data, dict):
            raise ValueError("settings.json is not a JSON object")
        for k,v in DEFAULT_SETTINGS.items():
            data.setdefault(k,v)
        return data
    except Exception:
        # backup corrupted file (timestamped so an older backup never blocks the rename)
        backup = SETTINGS_FILE.with_name(f"settings.corrupt-{time.strftime('%Y%m%d-%H%M%S')}.json")
        try:
            SETTINGS_FILE.replace(backup)
            logging.warning("Corrupt settings backed up to %s", backup)
        except Exception:
            logging.exception("Could not back up corrupt settings")
        SETTINGS_FILE.write_text(json.dumps(DEFAULT_SETTINGS, indent=4), encoding="utf-8")
        return dict(DEFAULT_SETTINGS)

def save_settings(s: dict):
    SETTINGS_FILE.write_text(json.dumps(s, indent=4), encoding="utf-8")

def normalize_path(p) -> Path:
    try:
        return Path(p).expanduser().resolve()
    except Exception:
        return Path(p)

def path_key(p) -> str:
    # Comparable form of a path (case-insensitive on Windows)
    return os.path.normcase(str(normalize_path(p)))

def is_app_bundle(p: Path) -> bool:
    return p.suffix.lower() == ".app" and p.is_dir()

def is_executable_file(p: Path) -> bool:
    try:
        if not str(p) or str(p) == ".":
            return False
        # macOS .app bundles are folders
        if p.suffix.lower() == ".app":
            return p.is_dir()
        return p.is_file() and (p.suffix.lower() == ".exe" or os.access(str(p), os.X_OK))
    except Exception:
        return False

def is_valid_rom_root(p) -> bool:
    return bool(p) and Path(p).is_dir()

def find_local_fusion() -> Optional[Path]:
    # Prefer a Fusion executable sitting next to this script
    for name in LOCAL_FUSION_NAMES:
        p = SCRIPT_DIR / name
        if is_executable_file(p):
            return p
    return None

# Best-effort normalization: drop (...) and [...] tags, replace underscores
TAG_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
ROMAN_RE = re.compile(r"\b(?:Ii|Iii|Iv|Vi|Vii|Viii|Ix)\b")

def normalize_name_from_filename(fn: str) -> str:
    stem = Path(fn).stem
    name = TAG_RE.sub("", stem).replace("_", " ")
    # collapse multiple spaces, trim leftover separators
    name = " ".join(name.split()).strip(" -.")
    # Only fix casing for all-lowercase names; keeps "NBA", "II", "CD" intact
    if name.islower():
        name = ROMAN_RE.sub(lambda m: m.group(0).upper(), name.title())
    return name or stem

# Stub: placeholder for DAT/DB verification (No-Intro/Redump)
# You can implement DAT parsing and checksum verification here.
def verify_against_db_stub(file_path: Path) -> Dict[str, Optional[str]]:
    # returns dict: {"status": "unknown"|"verified", "canonical_name": str or None, "db": "no-intro"|"redump"|None}
    # For now, we return unknown and suggested normalized name
    return {"status": "unknown", "canonical_name": normalize_name_from_filename(file_path.name), "db": None}

CUE_FILE_RE = re.compile(r'^\s*FILE\s+(?:"([^"]+)"|(\S+))', re.IGNORECASE)

def cue_referenced_files(cue: Path) -> set[str]:
    # Track files (.bin/.iso/...) a .cue sheet points to, as path_key() strings
    refs = set()
    try:
        for line in cue.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = CUE_FILE_RE.match(line)
            if m:
                refs.add(path_key(cue.parent / (m.group(1) or m.group(2))))
    except Exception as e:
        logging.exception("Could not read cue sheet %s: %s", cue, e)
    return refs

# Scanning function
def scan_rom_folder(rom_root: Path, include_subfolders: bool=True,
                    on_found: Optional[Callable[[Dict], None]] = None) -> List[Dict]:
    results = []
    if not is_valid_rom_root(rom_root):
        return results
    iterator = rom_root.rglob("*") if include_subfolders else rom_root.iterdir()
    candidates = []
    for p in iterator:
        try:
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
                candidates.append(p)
        except Exception as e:
            logging.exception("Scan error for %s: %s", p, e)
    # Sega CD: list the .cue only, not every track file it references
    track_files = set()
    for p in candidates:
        if p.suffix.lower() == ".cue":
            track_files |= cue_referenced_files(p)
    for p in sorted(candidates, key=lambda c: str(c).lower()):
        try:
            if p.suffix.lower() != ".cue" and path_key(p) in track_files:
                continue
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
            if on_found:
                on_found(entry)
        except Exception as e:
            logging.exception("Scan error for %s: %s", p, e)
    return results

def write_launcher_bat():
    # Windows convenience: double-clickable launcher without a console window
    if not IS_WINDOWS or getattr(sys, "frozen", False):
        return
    bat = SCRIPT_DIR / "run_housekega.bat"
    if bat.exists():
        return
    try:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        bat.write_text(f'@echo off\r\nstart "" "{exe}" "%~dp0{Path(__file__).name}"\r\n', encoding="utf-8")
        logging.info("Wrote %s", bat)
    except Exception as e:
        logging.exception("Could not write %s: %s", bat, e)

# GUI code (PySide6)
def show_fatal(msg: str):
    # Works with or without a console (pythonw / double-click has none)
    try:
        ERROR_LOG.write_text(msg + "\n", encoding="utf-8")
    except Exception:
        pass
    print(msg)
    if IS_WINDOWS and (sys.stdout is None or not sys.stdout.isatty()):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "HouseKega", 0x10)
        except Exception:
            pass

def can_prompt() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False

def ensure_pyside6() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except Exception:
        if not can_prompt():
            show_fatal("PySide6 is required. Install it with:\n\n"
                       f'"{sys.executable}" -m pip install PySide6\n\n'
                       "or run HouseKega from a terminal to install it automatically.")
            return False
        print("PySide6 is required. Install now? (y/N): ", end="")
        try:
            ans = input().strip().lower()
        except EOFError:
            ans = ""
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
from PySide6.QtCore import Qt, QTimer, QThread, Signal

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
        if not is_valid_rom_root(normalize_path(path)):
            QMessageBox.warning(self, "Folder not found", f"This folder does not exist:\n{path}")
            return
        self.settings["rom_root"] = str(normalize_path(path))
        self.settings["include_subfolders"] = bool(self.sub_chk.isChecked())
        save_settings(self.settings)
        self.selected = self.settings["rom_root"]
        self.accept()

class ScanWorker(QThread):
    found = Signal(dict)
    finished_scan = Signal(list)

    def __init__(self, rom_root: Path, include_sub: bool):
        super().__init__()
        self.rom_root = rom_root
        self.include_sub = include_sub

    def run(self):
        try:
            results = scan_rom_folder(self.rom_root, self.include_sub, on_found=self.found.emit)
        except Exception as e:
            logging.exception("Scan failed: %s", e)
            results = []
        self.finished_scan.emit(results)

class ScanDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Scanning ROMs")
        self.settings = settings
        self.results = []
        self.worker = None
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
        self.done_btn = QPushButton("Done")
        self.done_btn.setEnabled(False)
        self.done_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(self.done_btn)
        layout.addLayout(btn_row)
        QTimer.singleShot(100, self.start_scan)

    def start_scan(self):
        rom_root = Path(self.settings.get("rom_root", ""))
        include_sub = bool(self.settings.get("include_subfolders", True))
        self.log.append(f"Scanning {rom_root} (subfolders={include_sub})...")
        # Busy indicator: the total isn't known until the folder walk ends
        self.progress.setRange(0, 0)
        self.worker = ScanWorker(rom_root, include_sub)
        self.worker.found.connect(self.on_found)
        self.worker.finished_scan.connect(self.on_finished)
        self.worker.start()

    def on_found(self, r: dict):
        self.log.append(f"Found: {r['filename']} -> {r['suggested_name']} ({r['status']})")
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(r['filename']))
        self.table.setItem(row, 1, QTableWidgetItem(r['suggested_name'] or ""))
        self.table.setItem(row, 2, QTableWidgetItem(r['status'] or ""))
        self.table.setItem(row, 3, QTableWidgetItem(r['db'] or ""))

    def on_finished(self, results: list):
        self.results = results
        self.worker.wait()
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.log.append(f"Scan complete: {len(results)} items found.")
        logging.info("Scan complete: %d items", len(results))
        self.done_btn.setEnabled(True)

    def reject(self):
        # Don't close (Esc / window X) while the worker thread is still running
        if self.worker is not None and self.worker.isRunning():
            return
        super().reject()

class FusionSelectDialog(QDialog):
    def __init__(self, settings):
        super().__init__()
        self.setWindowTitle("Select Kega Fusion Executable")
        self.settings = settings
        layout = QVBoxLayout(self)
        form = QFormLayout()
        current = settings.get("fusion_path", "")
        if not (current and is_executable_file(Path(current))):
            local = find_local_fusion()
            if local:
                current = str(local)
        self.fusion_edit = QLineEdit(current)
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
        fn, _ = QFileDialog.getOpenFileName(self, "Select Fusion Executable", str(SCRIPT_DIR), "Executables (*.exe *.app);;All Files (*)")
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
        self.fusion_label = QLabel()
        self.rom_label = QLabel()
        sv.addWidget(self.fusion_label)
        sv.addWidget(self.rom_label)
        status_box.setLayout(sv)
        layout.addWidget(status_box)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search games...")
        self.search.setClearButtonEnabled(True)
        layout.addWidget(self.search)
        self.list = QListWidget()
        layout.addWidget(self.list, stretch=1)
        btn_row = QHBoxLayout()
        launch_btn = QPushButton("Launch Selected")
        browse_btn = QPushButton("Change ROM Folder")
        fusion_btn = QPushButton("Change Fusion")
        rescan_btn = QPushButton("Rescan")
        btn_row.addWidget(browse_btn)
        btn_row.addWidget(fusion_btn)
        btn_row.addWidget(rescan_btn)
        btn_row.addStretch()
        btn_row.addWidget(launch_btn)
        layout.addLayout(btn_row)
        launch_btn.clicked.connect(self.on_launch)
        browse_btn.clicked.connect(self.on_change_rom_folder)
        fusion_btn.clicked.connect(self.on_change_fusion)
        rescan_btn.clicked.connect(self.on_rescan)
        self.search.textChanged.connect(self.apply_filter)
        self.list.itemDoubleClicked.connect(self.on_double_click)
        self.refresh_status()
        self.populate(scan_results)

    def refresh_status(self):
        self.fusion_label.setText(f"Fusion: {self.settings.get('fusion_path') or '(not set)'}")
        self.rom_label.setText(f"ROM folder: {self.settings.get('rom_root') or '(not set)'}")

    def populate(self, results):
        self.scan_results = results
        self.list.clear()
        for r in results:
            item = QListWidgetItem(r['suggested_name'] or r['filename'])
            item.setData(Qt.UserRole, r['path'])
            item.setToolTip(r['path'])
            self.list.addItem(item)
        self.apply_filter(self.search.text())
        self.statusBar().showMessage(f"{len(results)} games")

    def apply_filter(self, text):
        needle = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            haystack = f"{item.text()} {Path(item.data(Qt.UserRole)).name}".lower()
            item.setHidden(bool(needle) and needle not in haystack)

    def on_double_click(self, item):
        path = item.data(Qt.UserRole)
        self.launch_with_fusion(path)

    def on_launch(self):
        sel = self.list.currentItem()
        if not sel or sel.isHidden():
            QMessageBox.information(self, "Select a game", "Please select a game to launch.")
            return
        path = sel.data(Qt.UserRole)
        self.launch_with_fusion(path)

    def launch_with_fusion(self, rom_path):
        fusion = self.settings.get("fusion_path", "")
        if not fusion or not is_executable_file(Path(fusion)):
            QMessageBox.warning(self, "Fusion not set", "Please set the Fusion executable first (Change Fusion).")
            return
        ok = launch_fusion_from_path(fusion, rom_path)
        if not ok:
            QMessageBox.critical(self, "Launch failed", f"Failed to launch Fusion. See log:\n{APP_LOG}")
        else:
            self.statusBar().showMessage(f"Launched {Path(rom_path).name}", 5000)

    def on_rescan(self):
        if not is_valid_rom_root(self.settings.get("rom_root")):
            self.on_change_rom_folder()
            return
        scan_dlg = ScanDialog(self.settings)
        scan_dlg.exec()
        self.populate(scan_dlg.results)

    def on_change_rom_folder(self):
        dlg = RomFolderDialog(self.settings)
        if dlg.exec():
            self.refresh_status()
            # re-scan and update list
            scan_dlg = ScanDialog(self.settings)
            scan_dlg.exec()
            self.populate(scan_dlg.results)

    def on_change_fusion(self):
        dlg = FusionSelectDialog(self.settings)
        if dlg.exec():
            self.refresh_status()

def build_launch_cmd(fusion: Path, rom_path: Optional[str | Path]) -> List[str]:
    if is_app_bundle(fusion):
        # macOS: open the bundle, passing the ROM as the document
        cmd = ["open", "-a", str(fusion)]
    else:
        cmd = [str(fusion)]
    if rom_path:
        cmd.append(str(normalize_path(rom_path)))
    return cmd

# Helper to launch fusion detached
def launch_fusion_from_path(fusion_path: str | Path, rom_path: Optional[str | Path] = None) -> bool:
    fusion = normalize_path(fusion_path)
    if not is_executable_file(fusion):
        logging.error("Fusion not executable: %s", fusion)
        return False
    cmd = build_launch_cmd(fusion, rom_path)
    try:
        if IS_WINDOWS:
            DETACHED = subprocess.CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd, cwd=str(fusion.parent), close_fds=True, creationflags=DETACHED)
        else:
            subprocess.Popen(cmd, cwd=str(fusion.parent), close_fds=True)
        logging.info("Launched Fusion: %s", cmd)
        return True
    except Exception as e:
        logging.exception("Launch error: %s", e)
        return False

# First-run flow
def first_launch_flow(settings):
    # 1) ROM folder selection (also when the saved folder has disappeared)
    if not is_valid_rom_root(settings.get("rom_root")):
        dlg = RomFolderDialog(settings)
        if dlg.exec() != QDialog.Accepted:
            return None, None
    # 2) Scan
    scan_dlg = ScanDialog(settings)
    scan_dlg.exec()
    results = scan_dlg.results
    # 3) Fusion selection (also when the saved exe has moved)
    if not is_executable_file(Path(settings.get("fusion_path") or "")):
        fdlg = FusionSelectDialog(settings)
        fdlg.exec()
    return results, settings

# Application entry
def main():
    settings = load_settings()
    app = QApplication(sys.argv)
    write_launcher_bat()
    rom_ok = is_valid_rom_root(settings.get("rom_root"))
    fusion_ok = is_executable_file(Path(settings.get("fusion_path") or ""))
    # First run, or a saved path no longer exists: run wizard
    if not rom_ok or not fusion_ok:
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
        ERROR_LOG.write_text("".join(traceback.format_exception(type(e), e, e.__traceback__)), encoding="utf-8")
        print("Launcher crashed. See log:", ERROR_LOG)
        raise

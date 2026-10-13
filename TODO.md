# HouseKega To-Do

Ordered from **least** to **most** important. Items come from the code review of `HouseKega.py`.

- [x] **14. README matches the code.** Remove claims for features that don't exist (telemetry, full DAT verification) and implement the cheap ones (search box, auto-detecting `fusion.exe` next to the script, generating `run_housekega.bat`).
- [x] **13. Drop the "Launched" pop-up.** Show a status-bar message instead of a dialog on every launch.
- [x] **12. Clear log location.** All logging goes to `HouseKega/Logs/housekega.log` (not `scan.log`), and the "Launch failed" message names the file.
- [x] **11. Keep corrupt settings backups.** Back up a bad `settings.json` with a timestamped name so an older backup can't block it, and treat valid JSON that isn't an object as corrupt.
- [x] **10. Status panel is accurate.** Show "(not set)" for empty values and refresh after the ROM folder or Fusion path changes.
- [x] **9. Rescan button.** With `auto_scan` off (or after adding ROMs) the list can be refreshed without re-picking the folder.
- [x] **8. Validate the ROM folder.** Reject a folder that doesn't exist instead of silently scanning nothing.
- [x] **7. Scan without freezing the window.** Run the scan on a background thread, with live progress and table updates; the dialog can't be closed mid-scan.
- [x] **6. Better name cleanup.** Strip every `(...)` / `[...]` tag, keep hyphens (`X-Men`), and stop `.title()` from breaking acronyms and Roman numerals (`NBA`, `II`).
- [x] **5. macOS `.app` support.** Accept `.app` bundles (they are folders) and launch them through `open -a`.
- [x] **4. Correct file-type list.** Remove `.chd` (Fusion can't open it); add `.gen`, `.sg`, `.zip`.
- [x] **3. No crash when started without a console.** If PySide6 is missing under `pythonw`/double-click, log the error and show a message box instead of crashing on `input()`.
- [x] **2. One entry per Sega CD game.** `.bin` tracks referenced by a `.cue` are hidden so only the `.cue` is listed.
- [x] **1. Recover from a broken Fusion path.** If the saved `fusion.exe` (or ROM folder) no longer exists, re-run the setup step, and add a "Change Fusion" button to the main window.

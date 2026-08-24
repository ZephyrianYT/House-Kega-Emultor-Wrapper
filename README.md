HouseKega — a single‑file launcher and installer for Kega Fusion that guides first‑time users through ROM folder selection, scans and normalizes game names, verifies entries at a basic level, and launches games with a clear Select and Launch workflow.
One‑line Tagline

Single‑file Kega Fusion wrapper that installs required subsystems, sets your ROM folder, and launches games with one click.
Elevator Pitch

HouseKega makes running Kega Fusion effortless. On first run it performs mandatory environment checks, prompts you to choose a ROM directory and scans it for supported Sega formats, asks you to point to fusion.exe, then opens a simple, searchable game list where you can double‑click or press Launch to start a game. All code is visible for audit and the installer only runs with your consent.
Key Features

    Mandatory installer checks for modern Python and GUI dependencies with an option to auto‑install.

    First‑run wizard that forces ROM folder selection, scans supported file types, and logs results.

    Best‑effort name normalization with hooks for DAT verification (No‑Intro, Redump, TOSEC).

    Fusion detection and selection with default preference for fusion.exe in the same folder.

    Clear launcher UI: searchable game list, select + Launch button, and double‑click to play.

    Single‑file distribution for easy auditing and optional PyInstaller packaging for a standalone exe.

    Transparent logging and settings stored under HouseKega/Config and HouseKega/Logs.

Quick Install Note

Requires Python 3.10 or newer. Drop the single file into your chosen folder, run it once to complete the wizard, point it at your ROM folder and fusion.exe, and use the generated run_housekega.bat or packaged exe for easy double‑click launches.
Legal and Privacy Reminder

HouseKega does not include ROMs or BIOS files and will not download copyrighted content. Users must supply their own dumps and verify them against public databases; telemetry is opt‑in only.

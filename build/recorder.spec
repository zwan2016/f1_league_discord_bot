# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the F1 25 Telemetry Recorder.
# Build with:
#   pip install pyinstaller
#   pyinstaller build/recorder.spec
#
# Output: dist/F1_Recorder.exe  (single file, no installation needed)

block_cipher = None

a = Analysis(
    ["../recorder_app.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[
        # sqlite3 is stdlib but PyInstaller sometimes misses it on Windows
        "sqlite3",
        "_sqlite3",
        "udp_capture",
        "udp_capture.capture",
        "udp_capture.recorder",
        "udp_capture.packets",
        "udp_capture.packets.header",
        "udp_capture.packets.lap_data",
        "udp_capture.packets.participants",
        "udp_capture.packets.session",
        "udp_capture.packets.event",
        "udp_capture.packets.final_classification",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages not needed by the recorder
        "matplotlib", "PIL", "discord", "aiohttp", "anthropic",
        "aiosqlite", "tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="F1_Recorder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,               # compress; set to False if UPX not available
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,           # keep console window — user needs to see output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # add an .ico path here if you have one
)

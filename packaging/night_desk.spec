# -*- mode: python ; coding: utf-8 -*-
import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hiddenimports = [], [], []
for pkg in ("rapidocr_onnxruntime", "onnxruntime", "cv2"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

for dll_name in ("MSVCP140.dll", "MSVCP140_1.dll", "VCRUNTIME140.dll", "VCRUNTIME140_1.dll"):
    binaries.append((os.path.join(sys.prefix, dll_name), "."))

hiddenimports += collect_submodules("pynput")
hiddenimports += [
    "wechat_draft_brain",
    "wechat_draft_brain.app",
    "wechat_draft_brain.ui.main_window",
    "PIL.ImageGrab",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "shapely",
    "pyclipper",
]

datas += [
    (os.path.join(root, "config", "default.yaml"), "config"),
    (os.path.join(root, "packaging", "icon.ico"), "."),
]

a = Analysis(
    [os.path.join(root, "packaging", "launch.py")],
    pathex=[root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
        "PySide6.QtWebEngine",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPdf",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtTextToSpeech",
    ],
    noarchive=False,
)

# Qt uses the Windows system ICU shim. A foreign icuuc.dll found on PATH (for
# example Poppler's versioned ICU build) shadows that shim and makes QtCore fail
# with ERROR_PROC_NOT_FOUND at startup.
a.binaries = [
    entry for entry in a.binaries if entry[0].lower() not in {"icuuc.dll", "icudt78.dll"}
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NightDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=os.path.join(root, "packaging", "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="NightDesk",
)

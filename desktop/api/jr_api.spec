# PyInstaller spec for jr-dashboard FastAPI sidecar.
# Run with: pyinstaller jr_api.spec --noconfirm
#
# Output: dist/jr-api/jr-api.exe (onedir) — onedir is preferred over onefile
# for faster cold-start (no temp-dir extraction).
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = [
    # uvicorn protocol implementations are loaded by string name
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]
hiddenimports += collect_submodules("pandas")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Big packages we don't need in the sidecar
        "matplotlib", "tkinter", "qlib", "lightgbm", "akshare", "scipy",
        "sklearn", "torch", "tensorflow", "PyQt5", "PyQt6", "PySide2",
        "PySide6", "IPython", "notebook", "jupyter",
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
    [],
    exclude_binaries=True,
    name="jr-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,           # keep console so Tauri can read sidecar stderr
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="jr-api",
)

"""
Dev-mode launcher for jr-dashboard.

Starts FastAPI (port 8765) + Vite (port 1420) as subprocesses, then opens
the browser to localhost:1420. Ctrl+C kills both.

For the proper Tauri native window, run:
    cd desktop/frontend && npm run tauri:dev
(first run will compile Rust crates for several minutes)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

THIS = Path(__file__).resolve().parent
PROJ = THIS.parent
VENV_PY = PROJ / ".venv" / "Scripts" / "python.exe"
API_MAIN = THIS / "api" / "main.py"
FRONTEND = THIS / "frontend"

if not VENV_PY.exists():
    sys.exit(f"[fatal] venv python not found at {VENV_PY}")
if not API_MAIN.exists():
    sys.exit(f"[fatal] api/main.py not found at {API_MAIN}")
if not FRONTEND.exists():
    sys.exit(f"[fatal] frontend not found at {FRONTEND}")

procs: list[subprocess.Popen] = []


def spawn(name: str, cmd: list[str], cwd: Path) -> subprocess.Popen:
    print(f"[start] {name}: {' '.join(cmd)}")
    p = subprocess.Popen(cmd, cwd=str(cwd),
                          stdout=sys.stdout, stderr=sys.stderr,
                          creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    procs.append(p)
    return p


def kill_all():
    for p in procs:
        try:
            if os.name == "nt":
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for p in procs:
        if p.poll() is None:
            try: p.kill()
            except Exception: pass


def main():
    try:
        spawn("FastAPI", [str(VENV_PY), str(API_MAIN)], cwd=PROJ)
        spawn("Vite", ["npm.cmd" if os.name == "nt" else "npm", "run", "dev"], cwd=FRONTEND)
        # wait a little for both
        time.sleep(3)
        print("\n[ready] http://localhost:1420 (opening browser)\n")
        webbrowser.open("http://localhost:1420")
        # block until either dies
        while True:
            for p in procs:
                if p.poll() is not None:
                    print(f"\n[warn] subprocess exited rc={p.returncode}")
                    kill_all()
                    sys.exit(p.returncode or 1)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\n[exit] killing children")
        kill_all()


if __name__ == "__main__":
    main()

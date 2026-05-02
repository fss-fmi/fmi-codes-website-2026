#!/usr/bin/env python3
"""
dev.py — Start backend (Flask + Werkzeug hot-reload) and frontend (Vite HMR) together.

Usage:
    python dev.py

Press Ctrl+C to stop both servers.

Backend  → http://localhost:5001
Frontend → http://localhost:5173  (proxies /api and /static to backend)
"""

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"

# ANSI colours
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
BOLD = "\033[1m"


def stream(proc: "subprocess.Popen[str]", label: str, colour: str) -> None:
    """Forward a process's combined stdout/stderr to our stdout with a labelled prefix."""
    prefix = f"{colour}{BOLD}[{label}]{RESET} "
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.write(prefix + line)
        sys.stdout.flush()


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the process and its entire child tree."""
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            proc.terminate()


def main() -> None:
    python = sys.executable
    npm = "npm.cmd" if sys.platform == "win32" else "npm"

    popen_kwargs: dict[str, Any] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    # On Unix, put each child in its own process group so kill_tree can SIGTERM
    # the whole group (e.g. Werkzeug reloader child + Vite child processes).
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True

    print(f"\n{BOLD}Starting FMI Codes dev environment…{RESET}")
    print("  Backend  → http://localhost:5001")
    print("  Frontend → http://localhost:5173\n")

    backend_proc = subprocess.Popen(
        [python, "run_server.py"],
        cwd=BACKEND_DIR,
        **popen_kwargs,
    )
    frontend_proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=FRONTEND_DIR,
        **popen_kwargs,
    )

    procs = [backend_proc, frontend_proc]

    threads = [
        threading.Thread(target=stream, args=(backend_proc, "BACKEND ", CYAN), daemon=True),
        threading.Thread(target=stream, args=(frontend_proc, "FRONTEND", MAGENTA), daemon=True),
    ]
    for t in threads:
        t.start()

    stop_event = threading.Event()

    def shutdown(signum=None, frame=None) -> None:
        if stop_event.is_set():
            return
        stop_event.set()
        print(f"\n{BOLD}Shutting down…{RESET}")
        for proc in procs:
            kill_tree(proc)
        for proc in procs:
            proc.wait()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Block the main thread; call shutdown if either process exits unexpectedly.
    while not stop_event.is_set():
        for proc in procs:
            if proc.poll() is not None:
                shutdown()
                return
        stop_event.wait(0.5)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Start the Assembly web development stack as one managed command.

Starts FastAPI and the static-export Next.js frontend as child processes,
waits for both readiness endpoints, and tears both down together on Ctrl+C.
No provider API keys are required to start; configure them in the browser.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 3000


def _free_port(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _wait_http(url: str, process: subprocess.Popen[bytes], timeout: float, name: str) -> None:
    deadline = time.monotonic() + timeout
    last_error = "not ready yet"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{name} exited early with code {process.returncode}.")
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if 200 <= response.status < 400:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.35)
    raise TimeoutError(f"{name} did not become ready within {timeout:g}s ({last_error}).")


def _terminate(process: subprocess.Popen[bytes] | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    print(f"Stopping {name}…", flush=True)
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)


def _command(args: Sequence[str]) -> list[str]:
    return [str(item) for item in args]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-host", default=DEFAULT_HOST, help="Backend bind host (default: 127.0.0.1)")
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--frontend-host", default=DEFAULT_HOST, help="Frontend bind host (default: 127.0.0.1)")
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--ready-timeout", type=float, default=90.0)
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser automatically")
    args = parser.parse_args()

    for label, port in (("backend", args.backend_port), ("frontend", args.frontend_port)):
        if not 1 <= port <= 65535:
            parser.error(f"{label} port must be between 1 and 65535")
    if args.ready_timeout <= 0:
        parser.error("--ready-timeout must be greater than zero")

    if not _free_port(args.backend_host, args.backend_port):
        print(f"ERROR: backend address {args.backend_host}:{args.backend_port} is already in use.", file=sys.stderr)
        return 2
    if not _free_port(args.frontend_host, args.frontend_port):
        print(f"ERROR: frontend address {args.frontend_host}:{args.frontend_port} is already in use.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.setdefault("APP_ENV", "development")
    env["APP_MODE"] = "dev"
    env["HOST"] = args.backend_host
    env["PORT"] = str(args.backend_port)
    env.setdefault("FRONTEND_URL", f"http://{args.frontend_host}:{args.frontend_port}")
    existing_cors = [item.strip() for item in env.get("CORS_ALLOW_LIST", "").split(",") if item.strip()]
    for origin in (f"http://localhost:{args.frontend_port}", f"http://127.0.0.1:{args.frontend_port}"):
        if origin not in existing_cors:
            existing_cors.append(origin)
    env["CORS_ALLOW_LIST"] = ",".join(existing_cors)
    env["NEXT_PUBLIC_API_URL"] = f"http://{args.backend_host}:{args.backend_port}"

    backend: subprocess.Popen[bytes] | None = None
    frontend: subprocess.Popen[bytes] | None = None
    frontend_url = f"http://{args.frontend_host}:{args.frontend_port}"
    backend_url = f"http://{args.backend_host}:{args.backend_port}"
    try:
        backend = subprocess.Popen(
            _command([sys.executable, "-m", "uvicorn", "src.main:app", "--host", args.backend_host, "--port", args.backend_port, "--reload"]),
            cwd=ROOT,
            env=env,
        )
        frontend = subprocess.Popen(
            _command(["npm", "run", "dev", "--", "--hostname", args.frontend_host, "--port", args.frontend_port]),
            cwd=FRONTEND,
            env=env,
        )
        print(f"Starting backend:  {backend_url}", flush=True)
        print(f"Starting frontend: {frontend_url}", flush=True)
        _wait_http(f"{backend_url}/health", backend, args.ready_timeout, "FastAPI backend")
        _wait_http(frontend_url, frontend, args.ready_timeout, "Next.js frontend")
        print("\nAssembly web stack is ready.", flush=True)
        print(f"Frontend: {frontend_url}", flush=True)
        print(f"Backend:  {backend_url}", flush=True)
        print("Press Ctrl+C to stop both processes.", flush=True)
        if not args.no_browser:
            try:
                import webbrowser
                webbrowser.open(frontend_url)
            except Exception:
                print("Browser could not be opened automatically; use the frontend URL above.", flush=True)
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.4)
        if backend.poll() is not None:
            print(f"Backend exited with code {backend.returncode}.", file=sys.stderr, flush=True)
            return int(backend.returncode or 1)
        print(f"Frontend exited with code {frontend.returncode}.", file=sys.stderr, flush=True)
        return int(frontend.returncode or 1)
    except KeyboardInterrupt:
        print("\nShutdown requested.", flush=True)
        return 0
    except (OSError, RuntimeError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        _terminate(frontend, "frontend")
        _terminate(backend, "backend")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install always-on LAN backend service via launchd (macOS).")
    parser.add_argument("--label", default="com.nextgen.health.lan", help="launchd service label.")
    parser.add_argument("--host", default="0.0.0.0", help="Host bind value.")
    parser.add_argument("--port", type=int, default=8000, help="Port bind value.")
    parser.add_argument("--load", action="store_true", help="Load/reload service immediately.")
    return parser.parse_args()


def detect_lan_ip() -> str:
    for interface in ("en0", "en1"):
        result = subprocess.run(["ipconfig", "getifaddr", interface], check=False, capture_output=True, text=True)
        lan_ip = result.stdout.strip()
        if lan_ip:
            return lan_ip
    return ""


def main() -> int:
    args = parse_args()

    venv_bin = PROJECT_ROOT / ".venv" / "bin"
    uvicorn_path = venv_bin / "uvicorn"
    python_path = venv_bin / "python"
    if not python_path.exists():
        print("ERROR: virtual environment not found. Create first:")
        print(f"  python3 -m venv {PROJECT_ROOT / '.venv'}")
        return 1
    if not uvicorn_path.exists():
        print("ERROR: uvicorn not found in virtualenv. Install dependencies:")
        print("  source .venv/bin/activate && pip install -r requirements.txt")
        return 1

    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents_dir / f"{args.label}.plist"

    environment_path = f"{venv_bin}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    payload = {
        "Label": args.label,
        "ProgramArguments": [
            str(uvicorn_path),
            "app.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {
            "PATH": environment_path,
            "PYTHONPATH": str(PROJECT_ROOT),
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(logs_dir / "backend.lan.launchd.out.log"),
        "StandardErrorPath": str(logs_dir / "backend.lan.launchd.err.log"),
    }

    plist_path.write_bytes(plistlib.dumps(payload))
    print(f"Wrote: {plist_path}")

    if args.load:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print("launchctl loaded successfully")
    else:
        print("Not loaded yet. To load manually:")
        print(f"  launchctl load {plist_path}")

    lan_ip = detect_lan_ip()
    if lan_ip:
        print(f"LAN URL: http://{lan_ip}:{args.port}")
    else:
        print(f"LAN URL: http://<YOUR_LAN_IP>:{args.port}")

    print("Status check:")
    print(f"  launchctl list | grep {args.label}")
    print("Logs:")
    print(f"  tail -f {logs_dir / 'backend.lan.launchd.err.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

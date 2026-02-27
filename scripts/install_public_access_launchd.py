#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install always-on launchd services for backend + Cloudflare named tunnel (macOS)."
    )
    parser.add_argument("--label-prefix", default="com.nextgen.health", help="launchd label prefix.")
    parser.add_argument("--tunnel-name", default="nextgen-health", help="Cloudflare named tunnel.")
    parser.add_argument("--host", default="0.0.0.0", help="Backend bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Backend bind port.")
    parser.add_argument(
        "--config",
        default=str(Path.home() / ".cloudflared" / "config.yml"),
        help="Path to cloudflared config.yml.",
    )
    parser.add_argument("--load", action="store_true", help="Load/reload launch agents immediately.")
    return parser.parse_args()


def write_plist(path: Path, payload: dict) -> None:
    path.write_bytes(plistlib.dumps(payload))
    print(f"Wrote: {path}")


def load_plist(path: Path) -> None:
    subprocess.run(["launchctl", "unload", str(path)], check=False)
    subprocess.run(["launchctl", "load", str(path)], check=True)


def main() -> int:
    args = parse_args()

    venv_bin = PROJECT_ROOT / ".venv" / "bin"
    uvicorn_path = venv_bin / "uvicorn"
    python_path = venv_bin / "python"

    if not python_path.exists():
        print("ERROR: Virtualenv Python not found. Create venv first:")
        print(f"  python3 -m venv {PROJECT_ROOT / '.venv'}")
        return 1

    if not uvicorn_path.exists():
        print("ERROR: uvicorn not found in virtualenv. Install requirements first:")
        print("  source .venv/bin/activate && pip install -r requirements.txt")
        return 1

    cloudflared_path = shutil.which("cloudflared")
    if not cloudflared_path:
        print("ERROR: cloudflared binary not found in PATH.")
        return 1

    config_path = Path(args.config).expanduser()
    if not config_path.exists():
        print(f"ERROR: cloudflared config not found: {config_path}")
        print("Create one named tunnel first:")
        print("  cloudflared tunnel login")
        print(f"  cloudflared tunnel create {args.tunnel_name}")
        print(f"  cloudflared tunnel route dns {args.tunnel_name} app.YOURDOMAIN.com")
        return 1

    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    backend_label = f"{args.label_prefix}.backend"
    tunnel_label = f"{args.label_prefix}.tunnel"

    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)

    backend_plist_path = launch_agents_dir / f"{backend_label}.plist"
    tunnel_plist_path = launch_agents_dir / f"{tunnel_label}.plist"

    environment_path = f"{venv_bin}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    backend_payload = {
        "Label": backend_label,
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
        "StandardOutPath": str(logs_dir / "backend.launchd.out.log"),
        "StandardErrorPath": str(logs_dir / "backend.launchd.err.log"),
    }

    tunnel_payload = {
        "Label": tunnel_label,
        "ProgramArguments": [
            cloudflared_path,
            "tunnel",
            "--config",
            str(config_path),
            "run",
            args.tunnel_name,
        ],
        "WorkingDirectory": str(PROJECT_ROOT),
        "EnvironmentVariables": {"PATH": environment_path},
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(logs_dir / "tunnel.launchd.out.log"),
        "StandardErrorPath": str(logs_dir / "tunnel.launchd.err.log"),
    }

    write_plist(backend_plist_path, backend_payload)
    write_plist(tunnel_plist_path, tunnel_payload)

    if args.load:
        load_plist(backend_plist_path)
        load_plist(tunnel_plist_path)
        print("launchctl loaded both services successfully.")
    else:
        print("Plists written but not loaded.")
        print("Load manually with:")
        print(f"  launchctl load {backend_plist_path}")
        print(f"  launchctl load {tunnel_plist_path}")

    print("\nStatus checks:")
    print(f"  launchctl list | grep '{args.label_prefix}'")
    print("Logs:")
    print(f"  tail -f {logs_dir / 'backend.launchd.out.log'}")
    print(f"  tail -f {logs_dir / 'backend.launchd.err.log'}")
    print(f"  tail -f {logs_dir / 'tunnel.launchd.out.log'}")
    print(f"  tail -f {logs_dir / 'tunnel.launchd.err.log'}")
    print(
        "\nImportant: keep this Mac awake and connected to internet. "
        "If the machine sleeps or shuts down, public access will pause."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import plistlib
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install monthly ICD refresh schedule via launchd (macOS).")
    parser.add_argument("--label", default="com.nextgen.icd-refresh", help="launchd job label.")
    parser.add_argument("--day", type=int, default=1, help="Day of month to run (1-28 recommended).")
    parser.add_argument(
        "--weekday",
        type=int,
        default=None,
        help="Weekday schedule (0 or 7=Sunday, 1=Monday ... 6=Saturday). If set, weekly schedule is used.",
    )
    parser.add_argument("--hour", type=int, default=3, help="Hour (0-23).")
    parser.add_argument("--minute", type=int, default=30, help="Minute (0-59).")
    parser.add_argument("--release", default="auto", help="Release version or auto.")
    parser.add_argument("--load", action="store_true", help="Also load job with launchctl.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    python_path = PROJECT_ROOT / ".venv" / "bin" / "python"
    refresh_script = PROJECT_ROOT / "scripts" / "refresh_icd_monthly.py"
    output_path = PROJECT_ROOT / "app" / "data" / "disease_knowledge.json"
    template_path = PROJECT_ROOT / "app" / "data" / "icd_category_templates.json"
    work_dir = PROJECT_ROOT / "app" / "data" / "icd_raw"
    stdout_log = PROJECT_ROOT / "app" / "data" / "icd_refresh_launchd.log"
    stderr_log = PROJECT_ROOT / "app" / "data" / "icd_refresh_launchd.err.log"

    if args.weekday is not None:
        schedule = {
            "Weekday": args.weekday,
            "Hour": args.hour,
            "Minute": args.minute,
        }
    else:
        schedule = {
            "Day": args.day,
            "Hour": args.hour,
            "Minute": args.minute,
        }

    plist_payload = {
        "Label": args.label,
        "ProgramArguments": [
            str(python_path),
            str(refresh_script),
            "--release",
            args.release,
            "--output",
            str(output_path),
            "--template",
            str(template_path),
            "--work-dir",
            str(work_dir),
            "--source-label",
            "WHO ICD-11",
            "--min-icd-rows",
            "5000",
        ],
        "StartCalendarInterval": schedule,
        "StandardOutPath": str(stdout_log),
        "StandardErrorPath": str(stderr_log),
        "RunAtLoad": False,
        "WorkingDirectory": str(PROJECT_ROOT),
    }

    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    launch_agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = launch_agents_dir / f"{args.label}.plist"

    plist_path.write_bytes(plistlib.dumps(plist_payload))
    print(f"Wrote: {plist_path}")

    if args.load:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
        print("launchctl loaded successfully")
    else:
        print("Not loaded yet. To enable now, run:")
        print(f"  launchctl load {plist_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

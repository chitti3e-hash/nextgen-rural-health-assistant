#!/usr/bin/env python3

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, UTC
import fnmatch
import hashlib
import io
from pathlib import Path
import tarfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "nextgen_recovery_all_in_one.py"

DEFAULT_INCLUDE = [
    "app",
    "frontend",
    "scripts",
    "tests",
    "certs",
    "README.md",
    "requirements.txt",
    "run.sh",
    "start-public.sh",
    "start-lan.sh",
    ".gitignore",
]

EXCLUDE_PATTERNS = [
    ".venv/*",
    ".pytest_cache/*",
    "__pycache__/*",
    "*.pyc",
    "*.pyo",
    "*.log",
    ".DS_Store",
    "nextgen-source-*.zip",
    "nextgen-source-*.tar.gz",
    "nextgen-source-*.sha256",
    "nextgen_recovery_all_in_one.py",
]


@dataclass
class BundleMeta:
    created_at: str
    file_count: int
    payload_sha256: str


def _is_excluded(rel_posix: str) -> bool:
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in EXCLUDE_PATTERNS)


def _collect_paths() -> list[Path]:
    collected: list[Path] = []
    for entry in DEFAULT_INCLUDE:
        source = PROJECT_ROOT / entry
        if not source.exists():
            continue
        if source.is_file():
            rel = source.relative_to(PROJECT_ROOT).as_posix()
            if not _is_excluded(rel):
                collected.append(source)
            continue
        for child in sorted(source.rglob("*")):
            if not child.is_file():
                continue
            rel = child.relative_to(PROJECT_ROOT).as_posix()
            if _is_excluded(rel):
                continue
            collected.append(child)
    unique: dict[str, Path] = {}
    for item in collected:
        unique[item.relative_to(PROJECT_ROOT).as_posix()] = item
    return [unique[key] for key in sorted(unique.keys())]


def _build_tar_gz(files: list[Path]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for file_path in files:
            rel = file_path.relative_to(PROJECT_ROOT).as_posix()
            archive.add(file_path, arcname=rel, recursive=False)
    return buffer.getvalue()


def _chunk_text(text: str, width: int = 120) -> str:
    return "\n".join(text[index : index + width] for index in range(0, len(text), width))


def _render_recovery_script(payload_b64: str, meta: BundleMeta) -> str:
    return f'''#!/usr/bin/env python3
"""
NextGen full project one-file recovery bundle.

Created at: {meta.created_at}
Included files: {meta.file_count}
Payload SHA256: {meta.payload_sha256}

Usage:
  python nextgen_recovery_all_in_one.py --list
  python nextgen_recovery_all_in_one.py --extract ./restore_here
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
from pathlib import Path
import tarfile

PAYLOAD_B64 = """{payload_b64}"""
EXPECTED_SHA256 = "{meta.payload_sha256}"
FILE_COUNT = {meta.file_count}
CREATED_AT = "{meta.created_at}"


def payload_bytes() -> bytes:
    return base64.b64decode(PAYLOAD_B64.encode("ascii"))


def verify_payload() -> bool:
    digest = hashlib.sha256(payload_bytes()).hexdigest()
    return digest == EXPECTED_SHA256


def _safe_members(archive: tarfile.TarFile, destination: Path) -> list[tarfile.TarInfo]:
    safe: list[tarfile.TarInfo] = []
    base = destination.resolve()
    for member in archive.getmembers():
        target = (destination / member.name).resolve()
        if base == target or base in target.parents:
            safe.append(member)
    return safe


def list_bundle() -> None:
    data = payload_bytes()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        names = sorted(member.name for member in archive.getmembers() if member.isfile())
    print(f"Bundle created: {{CREATED_AT}}")
    print(f"File count: {{len(names)}}")
    for name in names:
        print(name)


def extract_bundle(target_dir: Path, overwrite: bool) -> None:
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    data = payload_bytes()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = _safe_members(archive, target_dir)
        if not overwrite:
            for member in members:
                candidate = target_dir / member.name
                if candidate.exists():
                    raise FileExistsError(
                        f"Refusing to overwrite existing file: {{candidate}}. "
                        "Use --overwrite to replace existing files."
                    )
        archive.extractall(path=target_dir, members=members)

    print(f"Recovered {{len(members)}} files into: {{target_dir}}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract or inspect NextGen one-file recovery bundle.")
    parser.add_argument("--extract", default=None, help="Target directory to extract bundle.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing files.")
    parser.add_argument("--list", action="store_true", help="List bundled files.")
    parser.add_argument("--verify", action="store_true", help="Verify payload integrity hash.")
    args = parser.parse_args()

    if args.verify:
        ok = verify_payload()
        print("OK" if ok else "FAILED")
        return 0 if ok else 1

    if args.list:
        list_bundle()
        return 0

    if args.extract:
        extract_bundle(Path(args.extract), overwrite=args.overwrite)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def main() -> int:
    files = _collect_paths()
    payload = _build_tar_gz(files)
    payload_b64 = _chunk_text(base64.b64encode(payload).decode("ascii"))
    sha256 = hashlib.sha256(payload).hexdigest()
    meta = BundleMeta(
        created_at=datetime.now(UTC).isoformat(),
        file_count=len(files),
        payload_sha256=sha256,
    )

    content = _render_recovery_script(payload_b64=payload_b64, meta=meta)
    OUTPUT_FILE.write_text(content, encoding="utf-8")

    print(f"Wrote: {OUTPUT_FILE}")
    print(f"Included files: {meta.file_count}")
    print(f"Payload SHA256: {meta.payload_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

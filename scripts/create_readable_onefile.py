#!/usr/bin/env python3

from __future__ import annotations

import base64
from datetime import datetime, UTC
import fnmatch
import hashlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = PROJECT_ROOT / "nextgen_recovery_readable.py"

INCLUDE_PATHS = [
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
    "nextgen_recovery_readable.py",
]


def _is_excluded(rel_posix: str) -> bool:
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in EXCLUDE_PATTERNS)


def _collect_files() -> list[Path]:
    paths: dict[str, Path] = {}
    for entry in INCLUDE_PATHS:
        source = PROJECT_ROOT / entry
        if not source.exists():
            continue
        if source.is_file():
            rel = source.relative_to(PROJECT_ROOT).as_posix()
            if not _is_excluded(rel):
                paths[rel] = source
            continue

        for file_path in sorted(source.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(PROJECT_ROOT).as_posix()
            if _is_excluded(rel):
                continue
            paths[rel] = file_path

    return [paths[key] for key in sorted(paths.keys())]


def _safe_for_raw_triple_single(content: str) -> bool:
    if "'''" in content:
        return False
    if content.endswith("\\"):
        return False
    return True


def _make_entry(path: str, content: str) -> str:
    return f"    {path!r}: r'''{content}''',\n"


def _render_py(text_files: dict[str, str], encoded_files: dict[str, str], created_at: str, sha256: str) -> str:
    lines: list[str] = []
    lines.append("#!/usr/bin/env python3\n")
    lines.append('"""\n')
    lines.append("Readable one-file project recovery bundle.\n\n")
    lines.append(f"Created at: {created_at}\n")
    lines.append(f"Bundle SHA256: {sha256}\n\n")
    lines.append("Usage:\n")
    lines.append("  python nextgen_recovery_readable.py --list\n")
    lines.append("  python nextgen_recovery_readable.py --extract ./restore_dir\n")
    lines.append('"""\n\n')
    lines.append("from __future__ import annotations\n\n")
    lines.append("import argparse\n")
    lines.append("import base64\n")
    lines.append("from pathlib import Path\n\n")
    lines.append("TEXT_FILES = {\n")
    for path, content in text_files.items():
        lines.append(_make_entry(path, content))
    lines.append("}\n\n")
    lines.append("ENCODED_FILES = {\n")
    for path, payload in encoded_files.items():
        lines.append(f"    {path!r}: {payload!r},\n")
    lines.append("}\n\n")
    lines.append(
        """def list_files() -> None:
    names = sorted(list(TEXT_FILES.keys()) + list(ENCODED_FILES.keys()))
    for name in names:
        print(name)


def extract_bundle(target_dir: Path, overwrite: bool = False) -> None:
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for rel_path, content in TEXT_FILES.items():
        destination = target_dir / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
        destination.write_text(content, encoding="utf-8")
        count += 1

    for rel_path, payload in ENCODED_FILES.items():
        destination = target_dir / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
        destination.write_bytes(base64.b64decode(payload.encode("ascii")))
        count += 1

    print(f"Recovered {count} files into: {target_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Readable one-file recovery bundle extractor.")
    parser.add_argument("--list", action="store_true", help="List bundled files.")
    parser.add_argument("--extract", default=None, help="Target directory to extract files.")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting existing files.")
    args = parser.parse_args()

    if args.list:
        list_files()
        return 0

    if args.extract:
        extract_bundle(Path(args.extract), overwrite=args.overwrite)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""
    )
    return "".join(lines)


def main() -> int:
    files = _collect_files()
    text_files: dict[str, str] = {}
    encoded_files: dict[str, str] = {}
    hash_builder = hashlib.sha256()

    for file_path in files:
        rel = file_path.relative_to(PROJECT_ROOT).as_posix()
        raw = file_path.read_bytes()
        hash_builder.update(rel.encode("utf-8") + b"\x00" + raw + b"\x00")

        try:
            content = raw.decode("utf-8")
            if _safe_for_raw_triple_single(content):
                text_files[rel] = content
            else:
                encoded_files[rel] = base64.b64encode(raw).decode("ascii")
        except UnicodeDecodeError:
            encoded_files[rel] = base64.b64encode(raw).decode("ascii")

    created_at = datetime.now(UTC).isoformat()
    sha256 = hash_builder.hexdigest()
    output = _render_py(text_files=text_files, encoded_files=encoded_files, created_at=created_at, sha256=sha256)
    OUTPUT_PATH.write_text(output, encoding="utf-8")

    print(f"Wrote: {OUTPUT_PATH}")
    print(f"Text files: {len(text_files)}")
    print(f"Encoded files: {len(encoded_files)}")
    print(f"Bundle SHA256: {sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
import argparse
import json
import re
import shutil
import sys
import zipfile

import httpx


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.icd_importer import import_icd_dataset
from app.services.icd_refresh import (
    build_import_ready_csv,
    load_json_list,
    merge_custom_with_icd,
    validate_disease_records,
    write_refresh_state,
)


RELEASES_PAGE = "https://icd.who.int/browse/releases/mms/en"


def resolve_release(version: str) -> str:
    if version and version.lower() != "auto":
        return version

    response = httpx.get(RELEASES_PAGE, timeout=30.0)
    response.raise_for_status()
    matches = re.findall(r"/browse/(\d{4}-\d{2})/mms/en", response.text)
    if not matches:
        raise RuntimeError("Unable to auto-detect ICD release version from WHO releases page.")
    return sorted(set(matches))[-1]


def download_release_zip(release: str, output_path: Path, timeout: int) -> str:
    url = f"https://icdcdn.who.int/static/releasefiles/{release}/SimpleTabulation-ICD-11-MMS-en.zip"
    with httpx.stream("GET", url, timeout=timeout) as response:
        response.raise_for_status()
        with output_path.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    return url


def extract_tabulation_txt(zip_path: Path, work_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(path=work_dir)
    txt_path = work_dir / "SimpleTabulation-ICD-11-MMS-en.txt"
    if not txt_path.exists():
        raise RuntimeError("ICD tabulation text file not found inside downloaded ZIP.")
    return txt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monthly ICD refresh: download, transform, import, validate, and merge.")
    parser.add_argument("--release", default="auto", help="Release version like 2026-01, or 'auto' to detect latest.")
    parser.add_argument("--output", default="app/data/disease_knowledge.json", help="Target disease JSON file.")
    parser.add_argument("--template", default="app/data/icd_category_templates.json", help="ICD mapping templates JSON.")
    parser.add_argument("--work-dir", default="app/data/icd_raw", help="Working directory for downloaded/extracted files.")
    parser.add_argument("--source-label", default="WHO ICD-11", help="Source label prefix saved into records.")
    parser.add_argument("--min-icd-rows", type=int, default=5000, help="Minimum ICD row sanity threshold.")
    parser.add_argument("--timeout", type=int, default=180, help="Download timeout in seconds.")
    parser.add_argument("--keep-raw", action="store_true", help="Keep raw zip/txt/csv artifacts after refresh.")
    parser.add_argument("--no-backup", action="store_true", help="Skip backup of previous output JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    template_path = Path(args.template)

    release = resolve_release(args.release)
    release_label = f"{args.source_label} {release}"

    zip_path = work_dir / f"icd11_{release}_en.zip"
    txt_path = work_dir / "SimpleTabulation-ICD-11-MMS-en.txt"
    csv_path = work_dir / f"icd11_{release}_import_ready.csv"
    icd_only_path = work_dir / f"icd11_{release}_generated.json"

    download_url = download_release_zip(release, zip_path, timeout=args.timeout)
    txt_path = extract_tabulation_txt(zip_path, work_dir)
    prep_stats = build_import_ready_csv(txt_path, csv_path)

    import_icd_dataset(
        input_path=csv_path,
        output_path=icd_only_path,
        template_path=template_path,
        merge_existing=False,
        limit=None,
        source_label=release_label,
        code_column="code",
        title_column="title",
        description_column="description",
        chapter_column="chapter",
        aliases_column="aliases",
    )

    existing_records = load_json_list(output_path)
    icd_records = load_json_list(icd_only_path)
    merged_records = merge_custom_with_icd(existing_records, icd_records)
    summary = validate_disease_records(merged_records, min_icd_rows=args.min_icd_rows)

    if output_path.exists() and not args.no_backup:
        backup_dir = output_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = backup_dir / f"{output_path.stem}.{timestamp}{output_path.suffix}"
        shutil.copy2(output_path, backup_path)

    output_path.write_text(json.dumps(merged_records, ensure_ascii=False, indent=2), encoding="utf-8")
    state_path = output_path.parent / "icd_refresh_state.json"
    write_refresh_state(state_path, release=release, total_rows=summary["total_rows"], icd_rows=summary["icd_rows"])

    if not args.keep_raw:
        for path in [txt_path, csv_path, icd_only_path]:
            if path.exists():
                path.unlink()

    print("ICD monthly refresh complete")
    print(f"- Release: {release}")
    print(f"- Download URL: {download_url}")
    print(f"- Prepared ICD rows: {prep_stats['prepared_rows']}")
    print(f"- Total rows written: {summary['total_rows']}")
    print(f"- ICD rows written: {summary['icd_rows']}")
    print(f"- Output file: {output_path}")
    print(f"- State file: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


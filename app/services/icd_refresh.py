from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path
import csv
import json
import re


EXCLUDED_CHAPTERS = {
    "Extension Codes",
    "Supplementary section for functioning assessment",
    "Codes for special purposes",
}


def _clean_title(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = re.sub(r"^(?:-\s*)+", "", cleaned)
    return cleaned.strip()


def build_import_ready_csv(source_txt_path: Path, output_csv_path: Path) -> dict:
    chapter_titles: dict[str, str] = {}
    rows: list[dict] = []
    skipped_by_chapter = 0

    with source_txt_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            class_kind = (row.get("ClassKind") or "").strip().lower()
            chapter_no = (row.get("ChapterNo") or "").strip()
            title = _clean_title(row.get("Title"))
            code = (row.get("Code") or "").strip()

            if class_kind == "chapter" and chapter_no and title:
                chapter_titles[chapter_no] = title
                continue

            if class_kind != "category" or not code or not title:
                continue

            chapter = chapter_titles.get(chapter_no, f"Chapter {chapter_no}" if chapter_no else "ICD chapter")
            if chapter in EXCLUDED_CHAPTERS:
                skipped_by_chapter += 1
                continue

            coding_note = (row.get("CodingNote") or "").strip()
            description = coding_note if coding_note else f"ICD-11 category under {chapter}."

            rows.append(
                {
                    "code": code,
                    "title": title,
                    "description": description,
                    "chapter": chapter,
                    "aliases": "",
                    "is_residual": "true" if (row.get("IsResidual") or "").strip().lower() == "true" else "false",
                    "is_leaf": "true" if (row.get("isLeaf") or "").strip().lower() == "true" else "false",
                }
            )

    with output_csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["code", "title", "description", "chapter", "aliases", "is_residual", "is_leaf"],
        )
        writer.writeheader()
        writer.writerows(rows)

    return {
        "prepared_rows": len(rows),
        "skipped_by_chapter": skipped_by_chapter,
        "output_csv": str(output_csv_path),
    }


def load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list JSON in {path}")
    return [item for item in payload if isinstance(item, dict)]


def merge_custom_with_icd(existing_records: list[dict], icd_records: list[dict]) -> list[dict]:
    custom_records = [item for item in existing_records if not str(item.get("id", "")).startswith("icd-")]

    by_id: dict[str, dict] = {}
    for item in icd_records:
        item_id = str(item.get("id", "")).strip()
        if item_id:
            by_id[item_id] = item

    combined = custom_records + list(by_id.values())
    combined.sort(key=lambda item: str(item.get("id", "")))
    return combined


def validate_disease_records(records: list[dict], min_icd_rows: int = 5000) -> dict:
    required_fields = {
        "id",
        "name",
        "aliases",
        "category",
        "overview",
        "treatment_summary",
        "medicine_guidance",
        "home_care",
        "red_flags",
        "source",
    }

    icd_count = 0
    for index, item in enumerate(records):
        missing = [field for field in required_fields if field not in item]
        if missing:
            raise ValueError(f"Record {index} missing required fields: {missing}")

        if str(item.get("id", "")).startswith("icd-"):
            icd_count += 1

    if icd_count < min_icd_rows:
        raise ValueError(f"ICD rows too low: {icd_count} < {min_icd_rows}")

    return {"total_rows": len(records), "icd_rows": icd_count}


def write_refresh_state(state_path: Path, *, release: str, total_rows: int, icd_rows: int) -> None:
    payload = {
        "release": release,
        "total_rows": total_rows,
        "icd_rows": icd_rows,
        "refreshed_at": datetime.now(UTC).isoformat(),
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import json
import re


@dataclass
class ICDSourceRecord:
    code: str
    title: str
    description: str
    chapter: str
    aliases: list[str]


class ICDImportError(RuntimeError):
    pass


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip())


def _clean_title(value: str | None) -> str:
    cleaned = _normalize(value)
    cleaned = re.sub(r"^(?:-\s*)+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _slugify_code(code: str) -> str:
    base = code.lower().strip()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    return base.strip("-") or "unknown"


def _split_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = re.split(r"[|;,]", raw)
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _normalize(value)
        key = cleaned.lower()
        if cleaned and key not in seen:
            deduped.append(cleaned)
            seen.add(key)
    return deduped


def load_icd_rows(
    input_path: Path,
    code_column: str,
    title_column: str,
    description_column: str,
    chapter_column: str,
    aliases_column: str | None,
) -> list[ICDSourceRecord]:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        return _load_csv_rows(
            input_path=input_path,
            code_column=code_column,
            title_column=title_column,
            description_column=description_column,
            chapter_column=chapter_column,
            aliases_column=aliases_column,
        )
    if suffix == ".json":
        return _load_json_rows(
            input_path=input_path,
            code_column=code_column,
            title_column=title_column,
            description_column=description_column,
            chapter_column=chapter_column,
            aliases_column=aliases_column,
        )
    raise ICDImportError("Unsupported input format. Use .csv or .json")


def _load_csv_rows(
    input_path: Path,
    code_column: str,
    title_column: str,
    description_column: str,
    chapter_column: str,
    aliases_column: str | None,
) -> list[ICDSourceRecord]:
    rows: list[ICDSourceRecord] = []
    with input_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            code = _normalize(raw_row.get(code_column))
            title = _clean_title(raw_row.get(title_column))
            if not code or not title:
                continue

            rows.append(
                ICDSourceRecord(
                    code=code,
                    title=title,
                    description=_normalize(raw_row.get(description_column)),
                    chapter=_normalize(raw_row.get(chapter_column)),
                    aliases=_split_aliases(raw_row.get(aliases_column)) if aliases_column else [],
                )
            )
    return rows


def _load_json_rows(
    input_path: Path,
    code_column: str,
    title_column: str,
    description_column: str,
    chapter_column: str,
    aliases_column: str | None,
) -> list[ICDSourceRecord]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ICDImportError("JSON input must be a list of row objects.")

    rows: list[ICDSourceRecord] = []
    for raw_row in payload:
        if not isinstance(raw_row, dict):
            continue

        code = _normalize(raw_row.get(code_column))
        title = _clean_title(raw_row.get(title_column))
        if not code or not title:
            continue

        rows.append(
            ICDSourceRecord(
                code=code,
                title=title,
                description=_normalize(raw_row.get(description_column)),
                chapter=_normalize(raw_row.get(chapter_column)),
                aliases=_split_aliases(raw_row.get(aliases_column)) if aliases_column else [],
            )
        )
    return rows


def load_templates(template_path: Path) -> dict:
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    if "rules" not in payload or "default" not in payload:
        raise ICDImportError("Template file must include 'rules' and 'default'.")
    return payload


def _pick_template(record: ICDSourceRecord, template_payload: dict) -> dict:
    search_blob = " ".join([record.title, record.description, record.chapter]).lower()
    for rule in template_payload.get("rules", []):
        keywords = [word.lower() for word in rule.get("keywords", [])]
        if any(keyword in search_blob for keyword in keywords):
            return rule
    return template_payload["default"]


def _build_entry(record: ICDSourceRecord, template: dict, source_label: str) -> dict:
    overview = record.description or f"{record.title} is a recognized condition listed in ICD classification systems."
    source = f"{source_label} ({record.code})"

    aliases = []
    seen = set()
    for alias in record.aliases:
        key = alias.lower()
        if key != record.title.lower() and key not in seen:
            aliases.append(alias)
            seen.add(key)

    return {
        "id": f"icd-{_slugify_code(record.code)}",
        "name": record.title,
        "aliases": aliases,
        "category": template["category"],
        "overview": overview,
        "treatment_summary": template["treatment_summary"],
        "medicine_guidance": template["medicine_guidance"],
        "home_care": template["home_care"],
        "red_flags": template["red_flags"],
        "source": source,
    }


def import_icd_dataset(
    input_path: Path,
    output_path: Path,
    template_path: Path,
    merge_existing: bool,
    limit: int | None,
    source_label: str,
    code_column: str,
    title_column: str,
    description_column: str,
    chapter_column: str,
    aliases_column: str | None,
) -> dict:
    rows = load_icd_rows(
        input_path=input_path,
        code_column=code_column,
        title_column=title_column,
        description_column=description_column,
        chapter_column=chapter_column,
        aliases_column=aliases_column,
    )

    if limit:
        rows = rows[:limit]

    templates = load_templates(template_path)
    generated = [_build_entry(row, _pick_template(row, templates), source_label=source_label) for row in rows]

    if merge_existing and output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(existing, list):
            raise ICDImportError("Existing output file must be a list.")
        by_id = {item["id"]: item for item in existing if isinstance(item, dict) and "id" in item}
        for item in generated:
            by_id[item["id"]] = item
        final_data = list(by_id.values())
    else:
        final_data = generated

    final_data.sort(key=lambda item: item.get("id", ""))
    output_path.write_text(json.dumps(final_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "input_rows": len(rows),
        "written_rows": len(final_data),
        "output_path": str(output_path),
    }

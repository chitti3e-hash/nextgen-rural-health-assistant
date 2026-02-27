#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.icd_importer import ICDImportError, import_icd_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bulk import ICD-10/ICD-11 rows into disease knowledge JSON format."
    )
    parser.add_argument("--input", required=True, help="Input ICD dataset file (.csv or .json).")
    parser.add_argument(
        "--output",
        default="app/data/disease_knowledge.json",
        help="Output disease knowledge JSON path.",
    )
    parser.add_argument(
        "--template",
        default="app/data/icd_category_templates.json",
        help="Template mapping file for category/treatment defaults.",
    )
    parser.add_argument("--source-label", default="ICD Bulk Import", help="Source label to write into records.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of rows to import.")
    parser.add_argument(
        "--merge-existing",
        action="store_true",
        help="Merge imported records into existing output file by id.",
    )

    parser.add_argument("--code-column", default="code", help="Column name for ICD code.")
    parser.add_argument("--title-column", default="title", help="Column name for disease title.")
    parser.add_argument("--description-column", default="description", help="Column name for description text.")
    parser.add_argument("--chapter-column", default="chapter", help="Column name for ICD chapter text.")
    parser.add_argument("--aliases-column", default="aliases", help="Column name for aliases (optional).")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = import_icd_dataset(
            input_path=Path(args.input),
            output_path=Path(args.output),
            template_path=Path(args.template),
            merge_existing=args.merge_existing,
            limit=args.limit,
            source_label=args.source_label,
            code_column=args.code_column,
            title_column=args.title_column,
            description_column=args.description_column,
            chapter_column=args.chapter_column,
            aliases_column=args.aliases_column,
        )
    except ICDImportError as exc:
        print(f"ICD import failed: {exc}")
        return 1
    except FileNotFoundError as exc:
        print(f"File not found: {exc}")
        return 1

    print("ICD import complete")
    print(f"- Input rows processed: {result['input_rows']}")
    print(f"- Rows written: {result['written_rows']}")
    print(f"- Output: {result['output_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


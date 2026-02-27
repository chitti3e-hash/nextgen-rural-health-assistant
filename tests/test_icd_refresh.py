from pathlib import Path
import csv

from app.services.icd_refresh import build_import_ready_csv, merge_custom_with_icd, validate_disease_records


def test_build_import_ready_csv_filters_extension_chapter(tmp_path: Path) -> None:
    source_path = tmp_path / "tab.txt"
    output_path = tmp_path / "out.csv"

    source_path.write_text(
        "Foundation URI\tLinearization URI\tCode\tBlockId\tTitle\tClassKind\tDepthInKind\tIsResidual\tChapterNo\tBrowserLink\tisLeaf\tPrimary tabulation\tGrouping1\tGrouping2\tGrouping3\tGrouping4\tGrouping5\tCodingNote\tParent\n"
        "u1\tl1\t\t\tCertain infectious diseases\tchapter\t1\tFalse\t01\t\tFalse\t\t\t\t\t\t\t\t\n"
        "u2\tl2\t\t\tExtension Codes\tchapter\t1\tFalse\tXX\t\tFalse\t\t\t\t\t\t\t\t\n"
        "u3\tl3\t1A00\t\t- Dengue\tcategory\t1\tFalse\t01\t\tTrue\t\t\t\t\t\t\t\t\n"
        "u4\tl4\tXE266\t\t- Home\tcategory\t1\tFalse\tXX\t\tTrue\t\t\t\t\t\t\t\t\n",
        encoding="utf-8",
    )

    stats = build_import_ready_csv(source_path, output_path)
    assert stats["prepared_rows"] == 1

    with output_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["code"] == "1A00"
    assert rows[0]["title"] == "Dengue"


def test_merge_and_validate_records() -> None:
    existing = [
        {
            "id": "dis-001",
            "name": "Custom Dengue",
            "aliases": [],
            "category": "infectious",
            "overview": "x",
            "treatment_summary": "x",
            "medicine_guidance": ["x"],
            "home_care": ["x"],
            "red_flags": ["x"],
            "source": "custom",
        },
        {
            "id": "icd-a90",
            "name": "Old ICD Dengue",
            "aliases": [],
            "category": "infectious",
            "overview": "x",
            "treatment_summary": "x",
            "medicine_guidance": ["x"],
            "home_care": ["x"],
            "red_flags": ["x"],
            "source": "old",
        },
    ]
    imported = [
        {
            "id": "icd-a90",
            "name": "ICD Dengue",
            "aliases": [],
            "category": "infectious",
            "overview": "x",
            "treatment_summary": "x",
            "medicine_guidance": ["x"],
            "home_care": ["x"],
            "red_flags": ["x"],
            "source": "new",
        }
    ]

    merged = merge_custom_with_icd(existing, imported)
    assert len(merged) == 2
    assert any(item["id"] == "dis-001" for item in merged)

    summary = validate_disease_records(merged, min_icd_rows=1)
    assert summary["icd_rows"] == 1


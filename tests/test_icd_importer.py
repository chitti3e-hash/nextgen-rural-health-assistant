from pathlib import Path
import json

from app.services.icd_importer import import_icd_dataset, load_icd_rows


def _write_template(path: Path) -> None:
    payload = {
        "rules": [
            {
                "keywords": ["infectious", "virus"],
                "category": "infectious",
                "treatment_summary": "Rule-based treatment summary.",
                "medicine_guidance": ["Rule medicine 1", "Rule medicine 2"],
                "home_care": ["Rule care 1", "Rule care 2"],
                "red_flags": ["Rule red flag"],
            }
        ],
        "default": {
            "category": "general",
            "treatment_summary": "Default treatment summary.",
            "medicine_guidance": ["Default medicine"],
            "home_care": ["Default care"],
            "red_flags": ["Default red flag"],
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_icd_rows_csv_parses_aliases(tmp_path: Path) -> None:
    csv_path = tmp_path / "icd.csv"
    csv_path.write_text(
        "code,title,description,chapter,aliases\n"
        "A90,Dengue fever,Acute viral disease,Infectious diseases,dengue|breakbone fever\n",
        encoding="utf-8",
    )

    rows = load_icd_rows(
        input_path=csv_path,
        code_column="code",
        title_column="title",
        description_column="description",
        chapter_column="chapter",
        aliases_column="aliases",
    )

    assert len(rows) == 1
    assert rows[0].code == "A90"
    assert rows[0].title == "Dengue fever"
    assert rows[0].aliases == ["dengue", "breakbone fever"]


def test_import_icd_dataset_merges_existing(tmp_path: Path) -> None:
    template_path = tmp_path / "template.json"
    _write_template(template_path)

    csv_path = tmp_path / "icd.csv"
    csv_path.write_text(
        "code,title,description,chapter,aliases\n"
        "A90,Dengue fever,Acute viral disease,Infectious diseases,dengue\n"
        "I10,Essential hypertension,Chronic blood pressure disease,Circulatory diseases,high bp\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "diseases.json"
    output_path.write_text(
        json.dumps(
            [
                {
                    "id": "existing-1",
                    "name": "Existing Disease",
                    "aliases": [],
                    "category": "general",
                    "overview": "existing",
                    "treatment_summary": "existing",
                    "medicine_guidance": [],
                    "home_care": [],
                    "red_flags": [],
                    "source": "existing",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = import_icd_dataset(
        input_path=csv_path,
        output_path=output_path,
        template_path=template_path,
        merge_existing=True,
        limit=None,
        source_label="ICD Test",
        code_column="code",
        title_column="title",
        description_column="description",
        chapter_column="chapter",
        aliases_column="aliases",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    ids = {item["id"] for item in payload}
    assert result["input_rows"] == 2
    assert "existing-1" in ids
    assert "icd-a90" in ids
    assert "icd-i10" in ids

    dengue_record = next(item for item in payload if item["id"] == "icd-a90")
    assert dengue_record["category"] == "infectious"
    assert dengue_record["source"] == "ICD Test (A90)"


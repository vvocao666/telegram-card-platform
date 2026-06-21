import json

from services.ocr.ocr_report import build_ocr_report, write_ocr_report


def test_ocr_report_writes_required_metrics(tmp_path):
    report = build_ocr_report(
        total_images=1,
        total_cards=6,
        correct_count=6,
        predicted_count=6,
        fixed_count=2,
        false_negative_count=1,
        character_confusion_count=1,
        font_profile_hits=1,
        font_profile_misses=0,
        error_pairs={"2>Z": 2},
    )
    output_path = tmp_path / "ocr_report.json"

    write_ocr_report(report, output_path)
    data = json.loads(output_path.read_text(encoding="utf-8"))

    assert data["total_images"] == 1
    assert data["total_cards"] == 6
    assert data["fixed_count"] == 2
    assert data["precision"] == 1.0
    assert data["recall"] == 1.0
    assert data["f1"] == 1.0
    assert data["top_error_pairs"] == [["2>Z", 2]]

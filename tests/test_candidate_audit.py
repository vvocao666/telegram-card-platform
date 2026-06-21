import json

from services.ocr.candidate_audit import append_candidate_audit, build_candidate_audit


def test_candidate_audit_records_required_fields(tmp_path):
    record = build_candidate_audit("S07304-GM7D-\nJQ93-9NHLV", card_type="PUBG")

    assert record.ocr_raw == "S07304-GM7D-\nJQ93-9NHLV"
    assert any(item["value"] == "S07304-GM7D-JQ93-9NHLV" for item in record.candidate_list)
    assert record.best_candidate == "S07304-GM7D-JQ93-9NHLV"
    assert record.best_score is not None


def test_candidate_audit_writes_outputs_json(tmp_path):
    output_path = tmp_path / "outputs" / "ocr_candidates.json"

    append_candidate_audit("T07304-GM7D-JQ93-9NHLV", card_type="PUBG", output_path=output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))

    assert data[0]["ocr_raw"] == "T07304-GM7D-JQ93-9NHLV"
    assert "T07304-GM7D-JQ93-9NHLV" in data[0]["validator_reject_reason"]
    assert data[0]["validator_reject_reason"]["T07304-GM7D-JQ93-9NHLV"] == "pubg_prefix_not_s07"

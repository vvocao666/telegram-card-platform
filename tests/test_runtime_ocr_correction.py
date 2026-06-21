import json

import services.runtime as runtime
from services.ocr.font_repository import FontRepository


REAL_PUBG_SAMPLE = """
S07304-WJB9-VPEZ-MUFWK
S07304-RC96-2437-QTWC9
S07304-9M8Q-Y7UW-7822U
S07304-GM7D-
JQ93-9NHLV
S07304-XFBX-EHKX-RB34D
S07304-8MP5-4TY9-VDVR6
"""


EXPECTED_PUBG_CARDS = [
    "S07304-WJB9-VPEZ-MUFWK",
    "S07304-RC96-2437-QTWC9",
    "S07304-9M8Q-Y7UW-78Z2U",
    "S07304-GM7D-JQ93-9NHLV",
    "S07304-XFBX-EHKX-RB34D",
    "S07304-8MP5-4TY9-VDVR6",
]


def test_runtime_ocrspace_enhancement_recovers_real_sample(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime, "OCR_CANDIDATES_PATH", tmp_path / "ocr_candidates.json")
    monkeypatch.setattr(runtime, "font_repository", FontRepository(tmp_path / "ocr_font_profiles.json"))

    legacy_cards = runtime.extract_cards(REAL_PUBG_SAMPLE)
    enhanced_cards, stats = runtime.enhanced_ocrspace_pubg_cards(REAL_PUBG_SAMPLE, legacy_cards)
    settled_cards, _ = runtime.settle_image_cards(enhanced_cards + legacy_cards)

    assert settled_cards == EXPECTED_PUBG_CARDS
    assert len(settled_cards) / len(EXPECTED_PUBG_CARDS) == 1.0
    assert stats["ocr_fixed_count"] >= 1
    assert stats["ocr_missing_count"] >= 0
    assert stats["ocr_false_negative"] >= 0
    assert stats["ocr_character_confusion"] >= 1


def test_runtime_ocrspace_enhancement_writes_candidate_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / "ocr_candidates.json"
    monkeypatch.setattr(runtime, "OCR_CANDIDATES_PATH", audit_path)
    monkeypatch.setattr(runtime, "font_repository", FontRepository(tmp_path / "ocr_font_profiles.json"))

    runtime.enhanced_ocrspace_pubg_cards(REAL_PUBG_SAMPLE, runtime.extract_cards(REAL_PUBG_SAMPLE))
    data = json.loads(audit_path.read_text(encoding="utf-8"))

    assert data[0]["ocr_raw"] == REAL_PUBG_SAMPLE
    assert data[0]["best_candidate"] is not None
    assert data[0]["best_score"] is not None
    assert "candidate_list" in data[0]
    assert "validator_reject_reason" in data[0]

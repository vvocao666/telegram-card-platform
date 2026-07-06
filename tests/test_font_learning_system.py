from services.ocr.candidate_generator import generate_replacement_candidates
from services.ocr.correction_rules import replacement_map
from services.ocr.font_learning import diff_font_corrections, learn_font_correction
from services.ocr.font_repository import FontRepository
from services.ocr.font_scoring import score_with_font_profile
from services.ocr.validator import validate_candidate


GROUND_TRUTH = [
    "S07304-WJB9-VPEZ-MUFWK",
    "S07304-RC96-2437-QTWC9",
    "S07304-9M8Q-Y7UW-78Z2U",
    "S07304-GM7D-JQ93-9NHLV",
    "S07304-XFBX-EHKX-RB34D",
    "S07304-8MP5-4TY9-VDVR6",
]

OLD_RESULT_TEXT = """
S07304-WJB9-VPEZ-MUFWK
S07304-RC96-2437-QTWC9
S07304-9M8Q-Y7UW-7822U
S07304-GM7D-
JQ93-9NHLV
S07304-XFBX-EHKX-RB34D
S07304-8MP5-4TY9-VDVR6
"""


def test_font_learning_records_2_to_z_position_rule(tmp_path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    events = learn_font_correction(
        "S07304-9M8Q-Y7UW-7822U",
        "S07304-9M8Q-Y7UW-78Z2U",
        "PUBG",
        "pubg_font_a_supplier",
        repository,
    )
    profile = repository.get_profile("pubg_font_a_supplier")

    assert events[0].wrong == "2"
    assert events[0].correct == "Z"
    assert events[0].position == 19
    assert profile is not None
    assert profile.error_pairs["2>Z"] == 1
    assert profile.position_rules["19:2>Z"] == 1


def test_font_learning_does_not_auto_generate_ambiguous_2_to_z_candidate(tmp_path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    font_hash = "pubg_font_a_supplier"
    learn_font_correction(
        "S07304-9M8Q-Y7UW-7822U",
        "S07304-9M8Q-Y7UW-78Z2U",
        "PUBG",
        font_hash,
        repository,
    )
    profile = repository.get_profile(font_hash)
    candidates = generate_replacement_candidates(OLD_RESULT_TEXT, replacement_map("PUBG"), card_type="PUBG")
    candidate_values = {candidate.corrected_text for candidate in candidates}

    assert profile is not None
    assert "S07304-9M8Q-Y7UW-7822U" in candidate_values
    assert "S07304-9M8Q-Y7UW-78Z2U" not in candidate_values


def test_real_sample_keeps_non_ambiguous_candidates_valid(tmp_path):
    repository = FontRepository(tmp_path / "font_profiles.json")
    font_hash = "pubg_font_a_supplier"
    learn_font_correction(
        "S07304-WJB9-VPEZ-MUFWK",
        "S07304-WJBS-VPEZ-MUFWK",
        "PUBG",
        font_hash,
        repository,
    )
    profile = repository.get_profile(font_hash)
    candidates = generate_replacement_candidates(OLD_RESULT_TEXT, replacement_map("PUBG"), card_type="PUBG")
    matches = [candidate for candidate in candidates if candidate.corrected_text == "S07304-WJB9-VPEZ-MUFWK"]

    assert matches
    best = max(matches, key=lambda item: score_with_font_profile(item, profile, font_hash=font_hash).score)
    assert validate_candidate(best.corrected_text, "PUBG")


def test_diff_ignores_length_mismatch():
    assert diff_font_corrections("ABC", "ABCD", "PUBG", "font") == []

from services.ocr.candidate_generator import Candidate
from services.ocr.font_learning import learn_font_correction
from services.ocr.font_repository import FontRepository
from services.ocr.font_scoring import score_with_font_profile


def test_font_specific_rule_scores_highest_for_2_to_z(tmp_path):
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
    candidate = Candidate(
        "raw",
        "S07304-9M8Q-Y7UW-78Z2U",
        "PUBG",
        changes=("2->Z@19",),
    )

    score = score_with_font_profile(candidate, profile, font_hash=font_hash)

    assert score.score >= 120
    assert "font_match" in score.reasons
    assert "learned_rule" in score.reasons
    assert "position_match" in score.reasons


def test_font_mismatch_does_not_apply_font_weight(tmp_path):
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
    candidate = Candidate(
        "raw",
        "S07304-9M8Q-Y7UW-78Z2U",
        "PUBG",
        changes=("2->Z@19",),
    )

    score = score_with_font_profile(candidate, profile, font_hash="pubg_font_a_other")

    assert "font_match" not in score.reasons
    assert score.score < 120


def test_invalid_candidate_gets_negative_score():
    candidate = Candidate("raw", "T07304-9M8Q-Y7UW-78Z2U", "PUBG", changes=("T->S@0",))

    score = score_with_font_profile(candidate)

    assert score.score == -100
    assert score.reasons == ("invalid_format",)

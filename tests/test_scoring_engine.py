from services.ocr.candidate_generator import Candidate
from services.ocr.scoring_engine import choose_best_candidate, score_candidate


def test_valid_candidate_scores_higher_than_invalid_candidate():
    valid = Candidate("raw", "S07304-KVTE-JZGW-JVB4U", "PUBG")
    invalid = Candidate("raw", "S07304-KVTE-JZGW-JVB4", "PUBG")

    assert score_candidate(valid).score > score_candidate(invalid).score


def test_learned_candidate_gets_priority_after_three_hits():
    candidate = Candidate("raw", "S07304-KVTE-JZGW-JVB4U", "PUBG", changes=("O->0@4",))

    scored = score_candidate(candidate, learned_count=3)

    assert "learned_priority" in scored.reasons


def test_choose_best_candidate_returns_valid_candidate():
    candidates = [
        Candidate("raw", "S07304-KVTE-JZGW-JVB4", "PUBG"),
        Candidate("raw", "S07304-KVTE-JZGW-JVB4U", "PUBG"),
    ]

    best = choose_best_candidate(candidates)

    assert best is not None
    assert best.candidate.corrected_text == "S07304-KVTE-JZGW-JVB4U"

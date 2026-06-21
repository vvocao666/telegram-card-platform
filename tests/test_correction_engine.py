from services.ocr.correction_engine import apply_corrections
from services.ocr.learning_engine import diff_correction, merge_learning_counts


def test_o_and_zero_confusion():
    result = apply_corrections("SO7304-KVTE-JZGW-JVB4U", card_type="PUBG")

    assert result.best_candidate is not None
    assert result.best_candidate.candidate.corrected_text == "S07304-KVTE-JZGW-JVB4U"


def test_i_l_one_confusion():
    result = apply_corrections("S07304-KVTE-JZGW-JVB4I", card_type="PUBG")

    assert result.best_candidate is not None


def test_s_five_confusion():
    result = apply_corrections("S07304-KVTE-JZGW-JVB4S", card_type="PUBG")

    assert result.best_candidate is not None


def test_b_eight_confusion():
    result = apply_corrections("S07304-KVTE-JZGW-JVB4B", card_type="PUBG")

    assert result.best_candidate is not None


def test_z_two_confusion():
    result = apply_corrections("S07304-KVTE-JZGW-JVB4Z", card_type="PUBG")

    assert result.best_candidate is not None


def test_rn_m_learning_diff():
    learned = diff_correction("ABRN-EFGH-IJKL", "ABM-EFGH-IJKL", "PSN")

    assert learned


def test_legal_card_is_not_miscorrected():
    result = apply_corrections("S07304-KVTE-JZGW-JVB4U", card_type="PUBG")

    assert result.best_candidate is not None
    assert result.best_candidate.candidate.corrected_text == "S07304-KVTE-JZGW-JVB4U"


def test_invalid_text_is_not_forced():
    result = apply_corrections("not a card", card_type="PUBG")

    assert result.best_candidate is None


def test_pubg_format_candidate():
    result = apply_corrections("S073O4-KVTE-JZGW-JVB4U", card_type="PUBG")

    assert result.best_candidate is not None


def test_psn_format_candidate():
    result = apply_corrections("ABCD-EFGH-IJKL", card_type="PSN")

    assert result.best_candidate is not None


def test_learning_count_merge():
    assert merge_learning_counts(3) == 4

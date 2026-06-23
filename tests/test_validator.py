from services.ocr.validator import detect_card_type, filter_valid_candidates, validate_candidate


def test_pubg_candidate_validation():
    assert validate_candidate("S07304-KVTE-JZGW-JVB4U", card_type="PUBG")


def test_pubg_documented_format_is_valid():
    assert validate_candidate("S07304-F2V7-SGH8-NL72X", card_type="PUBG")


def test_pubg_observed_correction_format_is_valid():
    assert validate_candidate("S07304-9M8Q-Y7UW-78Z2U", card_type="PUBG")


def test_pubg_four_char_tail_format_is_invalid():
    assert not validate_candidate("S07304-DTUM-QWGA-CEGV", card_type="PUBG")


def test_psn_candidate_validation():
    assert validate_candidate("ABCD-EFGH-IJKL", card_type="PSN")


def test_psn_documented_format_is_valid():
    assert validate_candidate("PFP7-FP8X-26PH", card_type="PSN")


def test_non_s07_pubg_prefix_is_invalid():
    assert not validate_candidate("T07304-F2V7-SGH8-NL72X", card_type="PUBG")
    assert not validate_candidate("507304-F2V7-SGH8-NL72X", card_type="PUBG")


def test_psn_wrong_length_is_invalid():
    assert not validate_candidate("PFP7-FP8X-26P", card_type="PSN")
    assert not validate_candidate("PFP7-FP8X-26PH-Z", card_type="PSN")


def test_legal_card_is_not_rejected_without_card_type():
    assert detect_card_type("S07304-KVTE-JZGW-JVB4U") == "PUBG"
    assert detect_card_type("ABCD-EFGH-IJKL") == "PSN"


def test_invalid_text_is_not_forced_into_candidate():
    assert not validate_candidate("HELLO-WORLD", card_type=None)


def test_filter_valid_candidates_deduplicates():
    candidates = filter_valid_candidates(
        ["S07304-KVTE-JZGW-JVB4U", "S07304-KVTE-JZGW-JVB4U", "HELLO-WORLD"],
        card_type="PUBG",
    )

    assert candidates == ["S07304-KVTE-JZGW-JVB4U"]

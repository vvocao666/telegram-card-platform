from services.ocr.candidate_generator import extract_raw_candidates, generate_replacement_candidates


def test_extract_raw_candidates_keeps_separated_card_text():
    candidates = extract_raw_candidates("code S073O4-KVTE-JZGW-JVB4U", card_type="PUBG")

    assert candidates[0].corrected_text == "S073O4-KVTE-JZGW-JVB4U"


def test_generate_replacement_candidates_for_o_zero_confusion():
    candidates = generate_replacement_candidates(
        "S073O4-KVTE-JZGW-JVB4U",
        {"O": ("0",)},
        card_type="PUBG",
    )

    assert any(candidate.corrected_text == "S07304-KVTE-JZGW-JVB4U" for candidate in candidates)


def test_generate_pubg_prefix_candidate_from_507():
    candidates = generate_replacement_candidates(
        "507304-F2V7-SGH8-NL72X",
        {},
        card_type="PUBG",
    )

    assert any(candidate.corrected_text == "S07304-F2V7-SGH8-NL72X" for candidate in candidates)


def test_generate_pubg_prefix_candidate_from_so7():
    candidates = generate_replacement_candidates(
        "SO7304-F2V7-SGH8-NL72X",
        {},
        card_type="PUBG",
    )

    assert any(candidate.corrected_text == "S07304-F2V7-SGH8-NL72X" for candidate in candidates)


def test_generate_pubg_prefix_candidate_from_s0t():
    candidates = generate_replacement_candidates(
        "S0T304-F2V7-SGH8-NL72X",
        {},
        card_type="PUBG",
    )

    assert any(candidate.corrected_text == "S07304-F2V7-SGH8-NL72X" for candidate in candidates)


def test_generate_replacement_candidates_does_not_force_invalid_text():
    candidates = generate_replacement_candidates("hello world", {"O": ("0",)}, card_type="PUBG")

    assert candidates == []


def test_extract_raw_candidates_recovers_broken_pubg_lines():
    candidates = extract_raw_candidates(
        """
        S07304-WJB9-VPEZ-MUFWK
        S07304-RC96-2437-QTWC9
        S07304-9M8Q-Y7UW-78Z2U
        S07304-GM7D-
        JQ93-9NHLV
        S07304-XFBX-EHKX-RB34D
        S07304-8MP5-4TY9-VDVR6
        """,
        card_type="PUBG",
    )

    values = [candidate.corrected_text for candidate in candidates]

    assert len(values) == 6
    assert "S07304-GM7D-JQ93-9NHLV" in values


def test_pubg_sample_candidate_recall_is_above_95_percent():
    expected = {
        "S07304-WJB9-VPEZ-MUFWK",
        "S07304-RC96-2437-QTWC9",
        "S07304-9M8Q-Y7UW-78Z2U",
        "S07304-GM7D-JQ93-9NHLV",
        "S07304-XFBX-EHKX-RB34D",
        "S07304-8MP5-4TY9-VDVR6",
    }
    candidates = extract_raw_candidates(
        "S07304-WJB9-VPEZ-MUFWK\n"
        "S07304-RC96-2437-QTWC9\n"
        "S07304-9M8Q-Y7UW-78Z2U\n"
        "S07304-GM7D-\nJQ93-9NHLV\n"
        "S07304-XFBX-EHKX-RB34D\n"
        "S07304-8MP5-4TY9-VDVR6",
        card_type="PUBG",
    )
    actual = {candidate.corrected_text for candidate in candidates}

    assert len(actual & expected) / len(expected) >= 0.95

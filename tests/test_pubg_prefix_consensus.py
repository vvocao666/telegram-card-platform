from services.ocr.pubg_prefix_consensus import recover_single_prefix_digit_error


def test_recovers_one_prefix_digit_from_same_image_majority_in_original_order() -> None:
    existing = [
        "S07336-ZEBT-JFGP-KR4YE",
        "S07336-BHSN-T4TA-CH39R",
    ]
    lines = [
        "卡号：S07336-ZEBT-JFGP-KR4YE",
        "卡号：S01336-3SRE-ETDS-QEXR7",
        "卡号：S07336-BHSN-T4TA-CH39R",
    ]

    assert recover_single_prefix_digit_error(lines, existing) == [
        (1, "S07336-3SRE-ETDS-QEXR7")
    ]


def test_does_not_recover_without_two_matching_valid_prefixes() -> None:
    assert recover_single_prefix_digit_error(
        ["S01336-3SRE-ETDS-QEXR7"],
        ["S07336-ZEBT-JFGP-KR4YE"],
    ) == []


def test_does_not_change_pubg_body_characters() -> None:
    existing = [
        "S07336-AAAA-BBBB-CCCCC",
        "S07336-DDDD-EEEE-FFFFF",
    ]
    assert recover_single_prefix_digit_error(
        ["S01336-3SRE-ETDS-QEXR7"],
        existing,
    ) == [(0, "S07336-3SRE-ETDS-QEXR7")]

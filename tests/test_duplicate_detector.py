from services.ocr.duplicate_detector import canonical_card, similar_duplicate_warnings


def test_canonical_card_requires_validator():
    assert canonical_card("s07304-f2v7-sgh8-nl72x") == "S07304-F2V7-SGH8-NL72X"
    assert canonical_card("T07304-F2V7-SGH8-NL72X") is None


def test_similar_card_triggers_owner_warning_without_deleting():
    warnings = similar_duplicate_warnings(
        ["S07304-F2V7-SGH8-NL72Y"],
        source="supplier-a",
        existing_cards=[("S07304-F2V7-SGH8-NL72X", "supplier-a")],
    )

    assert len(warnings) == 1
    assert warnings[0].similarity >= 95
    assert warnings[0].card == "S07304-F2V7-SGH8-NL72Y"

from services.ocr.remote_variant_policy import remote_variants_conflict


def variant(*cards: str) -> dict:
    return {"cards": [{"text": card, "score": 0.99} for card in cards]}


def test_conflicting_original_and_enhanced_cards_require_review() -> None:
    payload = {
        "ocr_original": variant("S07336-MMVV-KBPX-LR72P"),
        "ocr_enhanced": variant("S07336-MMVV-KBPX-LR72F"),
    }
    assert remote_variants_conflict(payload) is True


def test_matching_variants_do_not_require_review() -> None:
    card = "S07336-C7P3-RMHQ-78288"
    assert remote_variants_conflict(
        {"ocr_original": variant(card), "ocr_enhanced": variant(card)}
    ) is False


def test_missing_variant_does_not_create_false_conflict() -> None:
    assert remote_variants_conflict(
        {"ocr_original": variant("S07336-C7P3-RMHQ-78288")}
    ) is False

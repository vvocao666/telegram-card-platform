import re
from types import SimpleNamespace

from services.ocr.remote_variant_policy import (
    cloud_resolves_remote_variant_conflict,
    remote_variant_evidence,
    remote_variants_conflict,
)


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


def test_mild_original_review_can_resolve_variant_conflict() -> None:
    original = "S07336-VLHL-MDZH-6S8ML"
    enhanced = "S07336-VLHL-MDZH-6S6ML"
    payload = {
        "ocr_original": variant(original),
        "ocr_enhanced": variant(enhanced),
        "variant_review": {
            "resolved": True,
            "selected_card": original,
            "review_card": original,
        },
    }

    assert remote_variants_conflict(payload) is False


def test_missing_variant_does_not_create_false_conflict() -> None:
    assert remote_variants_conflict(
        {"ocr_original": variant("S07336-C7P3-RMHQ-78288")}
    ) is False


def test_cloud_resolves_single_slot_higher_confidence_enhanced_conflict() -> None:
    original = "S07336-9L9E-W6T6-FKECC"
    enhanced = "S07336-9L9E-W6T6-FKECQ"
    payload = {
        "ocr_original": {"cards": [{"text": original, "score": 0.9963}]},
        "ocr_enhanced": {"cards": [{"text": enhanced, "score": 0.9998}]},
    }
    original_scores, enhanced_scores = remote_variant_evidence(payload)
    remote = SimpleNamespace(
        remote_variant_conflict=True,
        remote_original_card_scores=original_scores,
        remote_enhanced_card_scores=enhanced_scores,
        psn_cards=(),
    )
    cloud = SimpleNamespace(cards=(enhanced,), psn_cards=(), uncertain_count=0)

    assert cloud_resolves_remote_variant_conflict(
        remote,
        cloud,
        valid_card=lambda card: bool(re.fullmatch(r"S07\d{3}(?:-[A-Z0-9]{4}){2}-[A-Z0-9]{5}", card)),
    ) is True


def test_cloud_does_not_resolve_when_it_supports_lower_confidence_original() -> None:
    original = "S07336-9L9E-W6T6-FKECC"
    enhanced = "S07336-9L9E-W6T6-FKECQ"
    remote = SimpleNamespace(
        remote_variant_conflict=True,
        remote_original_card_scores=((original, 0.9963),),
        remote_enhanced_card_scores=((enhanced, 0.9998),),
        psn_cards=(),
    )
    cloud = SimpleNamespace(cards=(original,), psn_cards=(), uncertain_count=0)

    assert cloud_resolves_remote_variant_conflict(
        remote, cloud, valid_card=lambda _card: True
    ) is False


def test_cloud_does_not_resolve_multi_character_or_multi_card_conflict() -> None:
    remote = SimpleNamespace(
        remote_variant_conflict=True,
        remote_original_card_scores=(("S07336-9L9E-W6T6-FKECC", 0.99),),
        remote_enhanced_card_scores=(("S07336-9L9E-W6T6-FK9QQ", 1.0),),
        psn_cards=(),
    )
    cloud = SimpleNamespace(
        cards=("S07336-9L9E-W6T6-FK9QQ", "S07336-AAAA-BBBB-CCCCC"),
        psn_cards=(),
        uncertain_count=0,
    )

    assert cloud_resolves_remote_variant_conflict(
        remote, cloud, valid_card=lambda _card: True
    ) is False

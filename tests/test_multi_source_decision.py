from services.ocr.multi_source_decision import (
    apply_cpu_cloud_confirmations,
    cpu_cloud_confirmed_cards,
    cpu_payload_requires_review,
    cpu_pubg_candidates,
)


def test_cpu_conflict_only_triggers_review_in_strict_enabled_mode():
    assert not cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "shadow_only": True, "conflicts": [1]}})
    assert not cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "can_affect_result": True, "confirmation_mode": "strict", "review_required": False}})
    assert cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "can_affect_result": True, "confirmation_mode": "strict", "review_required": True}})
    assert not cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "can_affect_result": True, "confirmation_mode": "strict", "review_required": True, "roi_conflicts_resolved": True}})


def test_cpu_candidates_require_active_strict_review():
    card = "S07324-Z4ZH-S4Y7-NBRSB"
    active = {"cpu_ocr": {"enabled": True, "shadow_only": False, "can_affect_result": True,
                          "confirmation_mode": "strict", "review_required": True,
                          "lines": [{"raw_text": card, "score": 0.88}]}}
    shadow = {"cpu_ocr": {**active["cpu_ocr"], "shadow_only": True}}

    assert cpu_pubg_candidates(active) == (card,)
    assert cpu_pubg_candidates(shadow) == tuple()


def test_cpu_never_wins_without_exact_ocrspace_agreement():
    cpu = ("S07324-Z4ZH-S4Y7-NBRSB",)
    cloud = ("S07324-Z4ZH-54Y7-NBRSB",)

    assert cpu_cloud_confirmed_cards(cpu, cloud) == tuple()


def test_exact_cpu_and_ocrspace_confirmation_replaces_unique_gpu_slot():
    wrong = "S07324-Z4ZH-54Y7-NBRSB"
    correct = "S07324-Z4ZH-S4Y7-NBRSB"
    confirmed = cpu_cloud_confirmed_cards((correct,), (correct,))

    result, resolved = apply_cpu_cloud_confirmations(
        (wrong,),
        confirmed,
        likely_same_card=lambda left, right: sum(a != b for a, b in zip(left, right)) <= 1,
    )

    assert result == (correct,)
    assert resolved == 1

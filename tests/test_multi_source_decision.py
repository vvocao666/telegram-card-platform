from services.ocr.multi_source_decision import cpu_payload_requires_review


def test_cpu_conflict_only_triggers_review_in_strict_enabled_mode():
    assert not cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "shadow_only": True, "conflicts": [1]}})
    assert not cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "can_affect_result": True, "confirmation_mode": "strict", "conflicts": []}})
    assert cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "can_affect_result": True, "confirmation_mode": "strict", "conflicts": [1]}})
    assert not cpu_payload_requires_review({"cpu_ocr": {"enabled": True, "can_affect_result": True, "confirmation_mode": "strict", "conflicts": [1], "roi_conflicts_resolved": True}})

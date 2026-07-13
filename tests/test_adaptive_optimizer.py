import json

from services.ocr.adaptive_optimizer import (
    AdaptiveAuditCase,
    build_adaptive_policy_candidates,
    evaluate_policy_promotion,
    load_adaptive_audit_cases,
)
from services.ocr.image_benchmark import ImageBenchmarkSummary


def _summary(**overrides) -> ImageBenchmarkSummary:
    values = {
        "cases": 20,
        "expected_cards": 40,
        "correct_cards": 36,
        "missing_cards": 4,
        "false_positive_cards": 0,
        "type_mix_cases": 0,
        "order_mismatch_cases": 1,
        "exact_image_matches": 16,
        "precision": 1.0,
        "recall": 0.9,
        "p50_ms": 500.0,
        "p95_ms": 900.0,
    }
    values.update(overrides)
    return ImageBenchmarkSummary(**values)


def test_audit_loader_deduplicates_case_ids_and_downgrades_unknown_status(tmp_path):
    path = tmp_path / "2026-07-13-audit.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {"case_id": "one", "profile": "thin", "status": "confirmed_error", "error_types": ["missing"]},
                    {"case_id": "one", "profile": "thin", "status": "confirmed_match"},
                    {"case_id": "two", "profile": "thin", "status": "unknown"},
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_adaptive_audit_cases([path])

    assert [case.case_id for case in cases] == ["one", "two"]
    assert cases[1].status == "needs_review"


def test_policy_requires_enough_confirmed_non_ambiguous_errors():
    cases = [
        AdaptiveAuditCase(
            case_id=f"case-{index}",
            profile="thin|clear|pubg",
            status="confirmed_error" if index < 3 else "confirmed_match",
            error_types=("missing",) if index < 3 else tuple(),
        )
        for index in range(20)
    ]

    candidate = build_adaptive_policy_candidates(cases)[0]

    assert candidate.eligible is True
    assert candidate.action == "secondary_verification"
    assert candidate.error_cases == 3


def test_policy_does_not_learn_from_ambiguous_images():
    cases = [
        AdaptiveAuditCase(f"confirmed-{index}", "blurred", "confirmed_match")
        for index in range(20)
    ] + [
        AdaptiveAuditCase(f"review-{index}", "blurred", "needs_review")
        for index in range(10)
    ]

    candidate = build_adaptive_policy_candidates(cases)[0]

    assert candidate.eligible is False
    assert "too_many_ambiguous_samples" in candidate.reasons
    assert "insufficient_confirmed_errors" in candidate.reasons


def test_promotion_requires_improvement_without_accuracy_regression():
    baseline = _summary()
    improved = _summary(
        correct_cards=38,
        missing_cards=2,
        exact_image_matches=18,
        order_mismatch_cases=0,
        p95_ms=1100.0,
    )
    regressed = _summary(
        correct_cards=38,
        missing_cards=2,
        false_positive_cards=1,
        exact_image_matches=18,
    )

    assert evaluate_policy_promotion(baseline, improved).approved is True
    decision = evaluate_policy_promotion(baseline, regressed)
    assert decision.approved is False
    assert "false_positives_increased" in decision.reasons

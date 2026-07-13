from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

from services.ocr.image_benchmark import ImageBenchmarkSummary


CONFIRMED_STATUSES = {"confirmed_match", "confirmed_error"}
SAFE_REVIEW_ACTION = "secondary_verification"


@dataclass(frozen=True)
class AdaptiveAuditCase:
    case_id: str
    profile: str
    status: str
    error_types: tuple[str, ...] = tuple()


@dataclass(frozen=True)
class AdaptivePolicyCandidate:
    profile: str
    action: str
    confirmed_cases: int
    error_cases: int
    review_cases: int
    error_rate: float
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PromotionDecision:
    approved: bool
    reasons: tuple[str, ...]


def load_adaptive_audit_cases(paths: Iterable[Path]) -> list[AdaptiveAuditCase]:
    cases: list[AdaptiveAuditCase] = []
    seen: set[str] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("cases", []):
            case_id = str(item.get("case_id", "")).strip()
            profile = str(item.get("profile", "unspecified")).strip() or "unspecified"
            status = str(item.get("status", "needs_review")).strip()
            if not case_id or case_id in seen:
                continue
            if status not in CONFIRMED_STATUSES | {"needs_review"}:
                status = "needs_review"
            error_types = tuple(
                sorted({str(value).strip() for value in item.get("error_types", []) if str(value).strip()})
            )
            cases.append(
                AdaptiveAuditCase(
                    case_id=case_id,
                    profile=profile,
                    status=status,
                    error_types=error_types,
                )
            )
            seen.add(case_id)
    return cases


def build_adaptive_policy_candidates(
    cases: Iterable[AdaptiveAuditCase],
    *,
    minimum_confirmed_cases: int = 20,
    minimum_error_cases: int = 3,
    maximum_review_rate: float = 0.25,
) -> list[AdaptivePolicyCandidate]:
    grouped: dict[str, list[AdaptiveAuditCase]] = {}
    for case in cases:
        grouped.setdefault(case.profile, []).append(case)

    candidates: list[AdaptivePolicyCandidate] = []
    for profile, rows in sorted(grouped.items()):
        confirmed = [row for row in rows if row.status in CONFIRMED_STATUSES]
        errors = [row for row in confirmed if row.status == "confirmed_error"]
        reviews = [row for row in rows if row.status == "needs_review"]
        reasons: list[str] = []
        if len(confirmed) < minimum_confirmed_cases:
            reasons.append("insufficient_confirmed_samples")
        if len(errors) < minimum_error_cases:
            reasons.append("insufficient_confirmed_errors")
        review_rate = len(reviews) / len(rows) if rows else 1.0
        if review_rate > maximum_review_rate:
            reasons.append("too_many_ambiguous_samples")
        candidates.append(
            AdaptivePolicyCandidate(
                profile=profile,
                action=SAFE_REVIEW_ACTION,
                confirmed_cases=len(confirmed),
                error_cases=len(errors),
                review_cases=len(reviews),
                error_rate=round(len(errors) / len(confirmed), 6) if confirmed else 0.0,
                eligible=not reasons,
                reasons=tuple(reasons),
            )
        )
    return candidates


def evaluate_policy_promotion(
    baseline: ImageBenchmarkSummary,
    candidate: ImageBenchmarkSummary,
    *,
    maximum_p95_multiplier: float = 1.5,
) -> PromotionDecision:
    reasons: list[str] = []
    if candidate.cases != baseline.cases or candidate.expected_cards != baseline.expected_cards:
        reasons.append("benchmark_scope_changed")
    if candidate.false_positive_cards > baseline.false_positive_cards:
        reasons.append("false_positives_increased")
    if candidate.missing_cards > baseline.missing_cards:
        reasons.append("missing_cards_increased")
    if candidate.type_mix_cases > baseline.type_mix_cases:
        reasons.append("type_mix_increased")
    if candidate.order_mismatch_cases > baseline.order_mismatch_cases:
        reasons.append("order_regressed")
    if candidate.exact_image_matches <= baseline.exact_image_matches:
        reasons.append("no_exact_match_improvement")
    if candidate.p95_ms > max(baseline.p95_ms * maximum_p95_multiplier, baseline.p95_ms + 500):
        reasons.append("p95_latency_regressed")
    return PromotionDecision(approved=not reasons, reasons=tuple(reasons))


def write_adaptive_policy_candidates(
    output_path: Path,
    candidates: Iterable[AdaptivePolicyCandidate],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "mode": "shadow",
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    temporary = output_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output_path)

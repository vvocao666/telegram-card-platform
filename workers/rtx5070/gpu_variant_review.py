from __future__ import annotations

import os
import re
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import replace
from typing import Any, Callable

from cpu_preprocess import write_roi_crop

try:
    import cv2
except Exception:  # Cloud Deploy test environments do not install Worker-only OpenCV.
    cv2 = None


PUBG_CARD_RE = re.compile(
    r"(?<![A-Z0-9])S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}(?![A-Z0-9])"
)
MIN_THIRD_CANDIDATE_REVIEW_SCORE = 0.995
MIN_CPU_CONFIRMATION_SCORE = 0.90


@dataclass(frozen=True)
class VariantReviewResult:
    resolved: bool
    selected_engine: str = ""
    selected_card: str = ""
    review_card: str = ""
    review_score: float = 0.0
    latency_ms: int = 0
    reason: str = ""


def review_gpu_variant_conflict(
    original_path: str,
    original: dict[str, Any],
    enhanced: dict[str, Any],
    run_ocr: Callable[[str], tuple[dict[str, Any], int]],
) -> VariantReviewResult:
    """Resolve one-slot GPU conflicts using a mild transform of the original only.

    The review pass may select one of the two existing candidates. It never
    creates a third card or rewrites a character from format assumptions.
    """

    original_card = _single_card(original)
    enhanced_card = _single_card(enhanced)
    if not _eligible_conflict(original_card, enhanced_card):
        return VariantReviewResult(False, reason="not_eligible")

    review_path, review_scope = _write_review_image(
        original_path,
        original,
        original_card,
    )
    if not review_path:
        return VariantReviewResult(False, reason="review_image_failed")
    try:
        review, latency_ms = run_ocr(review_path)
    finally:
        try:
            os.unlink(review_path)
        except OSError:
            pass

    review_item = _single_card_item(review)
    if review_item is None:
        return VariantReviewResult(False, latency_ms=latency_ms, reason="no_review_card")
    review_card = review_item[0]
    if review_card == original_card:
        selected_engine = "original"
    elif review_card == enhanced_card:
        selected_engine = "enhanced"
    else:
        return VariantReviewResult(
            False,
            review_card=review_card,
            review_score=review_item[1],
            latency_ms=latency_ms,
            reason="third_candidate",
        )
    return VariantReviewResult(
        True,
        selected_engine=selected_engine,
        selected_card=review_card,
        review_card=review_card,
        review_score=review_item[1],
        latency_ms=latency_ms,
        reason=f"{review_scope}_original_confirmation",
    )


def confirm_third_candidate_with_cpu(
    result: VariantReviewResult,
    original: dict[str, Any],
    enhanced: dict[str, Any],
    cpu_payload: dict[str, Any],
) -> VariantReviewResult:
    """Confirm a third ROI candidate only with matching CPU glyph evidence.

    This path never derives a card from CPU text. The ROI pass must already
    return one complete valid card at high confidence, and all three GPU
    candidates must differ at the same single character position. CPU is only
    allowed to confirm the exact ROI suffix while rejecting both alternatives.
    """

    if (
        result.resolved
        or result.reason != "third_candidate"
        or result.review_score < MIN_THIRD_CANDIDATE_REVIEW_SCORE
        or not PUBG_CARD_RE.fullmatch(result.review_card)
    ):
        return result
    original_card = _single_card(original)
    enhanced_card = _single_card(enhanced)
    if not _same_single_conflict_slot(
        original_card,
        enhanced_card,
        result.review_card,
    ):
        return result
    if not _cpu_supports_only_candidate(
        cpu_payload,
        result.review_card,
        alternatives=(original_card, enhanced_card),
    ):
        return result
    return replace(
        result,
        resolved=True,
        selected_engine="roi_cpu",
        selected_card=result.review_card,
        reason="roi_cpu_confirmation",
    )


def apply_confirmed_review_card(
    selected: dict[str, Any],
    result: VariantReviewResult,
) -> dict[str, Any]:
    """Apply an already confirmed ROI card without changing its position."""

    if not result.resolved or result.selected_engine != "roi_cpu":
        return selected
    cards = list(selected.get("cards", []) or [])
    if len(cards) != 1:
        return selected
    current = str(
        cards[0].get("text", "") if isinstance(cards[0], dict) else cards[0]
    ).upper()
    if not PUBG_CARD_RE.fullmatch(current):
        return selected

    updated = deepcopy(selected)
    updated_card = updated["cards"][0]
    if isinstance(updated_card, dict):
        updated_card["text"] = result.selected_card
        updated_card["score"] = result.review_score
    else:
        updated["cards"][0] = result.selected_card
    for item in updated.get("texts", []) or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", ""))
        if current in text.upper():
            start = text.upper().index(current)
            item["text"] = (
                text[:start] + result.selected_card + text[start + len(current) :]
            )
            item["score"] = result.review_score
    return updated


def _write_review_image(
    original_path: str,
    original: dict[str, Any],
    card: str,
) -> tuple[str | None, str]:
    box = _card_box(original, card)
    if box:
        roi_path = write_roi_crop(original_path, box, scale=3)
        if roi_path:
            return roi_path, "roi"
    return write_mild_review_image(original_path), "mild"


def _card_box(result: dict[str, Any], card: str) -> Any | None:
    for item in result.get("texts", []) or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).upper()
        if card in text and item.get("box"):
            return item["box"]
    return None


def write_mild_review_image(original_path: str) -> str | None:
    """Upscale the original without changing contrast, color, or glyph edges."""

    if cv2 is None:
        return None
    image = cv2.imread(original_path)
    if image is None:
        return None
    try:
        mild = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
        handle, target = tempfile.mkstemp(suffix=".png")
        os.close(handle)
        if not cv2.imwrite(target, mild):
            os.unlink(target)
            return None
        return target
    except Exception:
        return None


def result_payload(result: VariantReviewResult) -> dict[str, Any]:
    return {
        "resolved": result.resolved,
        "selected_engine": result.selected_engine,
        "selected_card": result.selected_card,
        "review_card": result.review_card,
        "review_score": result.review_score,
        "latency_ms": result.latency_ms,
        "reason": result.reason,
    }


def _eligible_conflict(original_card: str, enhanced_card: str) -> bool:
    if not original_card or not enhanced_card or original_card == enhanced_card:
        return False
    if len(original_card) != len(enhanced_card):
        return False
    return sum(left != right for left, right in zip(original_card, enhanced_card)) == 1


def _same_single_conflict_slot(*cards: str) -> bool:
    if len(cards) < 3 or any(not PUBG_CARD_RE.fullmatch(card) for card in cards):
        return False
    if len({len(card) for card in cards}) != 1:
        return False
    differing = {
        index
        for index, values in enumerate(zip(*cards))
        if len(set(values)) > 1
    }
    return len(differing) == 1


def _cpu_supports_only_candidate(
    payload: dict[str, Any],
    candidate: str,
    *,
    alternatives: tuple[str, ...],
) -> bool:
    candidate_suffix = candidate[1:]
    alternative_suffixes = {card[1:] for card in alternatives if card}
    supporting_lines = 0
    for line in payload.get("lines", []) or []:
        try:
            score = float(line.get("score", 0.0))
        except (AttributeError, TypeError, ValueError):
            continue
        raw_text = re.sub(r"\s+", "", str(line.get("raw_text", "")).upper())
        if score < MIN_CPU_CONFIRMATION_SCORE or candidate_suffix not in raw_text:
            continue
        if any(suffix in raw_text for suffix in alternative_suffixes):
            return False
        supporting_lines += 1
    return supporting_lines == 1


def _single_card(result: dict[str, Any]) -> str:
    item = _single_card_item(result)
    return item[0] if item else ""


def _single_card_item(result: dict[str, Any]) -> tuple[str, float] | None:
    found: dict[str, float] = {}
    for item in result.get("cards", []) or []:
        text = str(item.get("text", "") if isinstance(item, dict) else item).upper()
        match = PUBG_CARD_RE.search(text)
        if not match:
            continue
        card = match.group(0)
        try:
            score = float(item.get("score", 0.0)) if isinstance(item, dict) else 0.0
        except (TypeError, ValueError):
            score = 0.0
        found[card] = max(found.get(card, 0.0), score)
    if len(found) != 1:
        return None
    return next(iter(found.items()))

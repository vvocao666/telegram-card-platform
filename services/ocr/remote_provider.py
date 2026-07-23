from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from services.ocr.multi_source_decision import (
    cpu_payload_requires_review,
    cpu_pubg_candidates,
)
from services.ocr.remote_execution_gate import RemoteWorkerBusy
from services.ocr.variant_rebuild_evidence import variant_rebuilt_card_scores


def recognize_remote(
    runtime: Any,
    image_path: Path,
    *,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> Any | None:
    """调用 owner-hybrid Worker，并从带坐标的原始文本重建卡密。"""
    if not runtime.REMOTE_OCR_ENABLED or not runtime.REMOTE_OCR_URL:
        return None
    if runtime.remote_ocr_is_circuit_open():
        runtime.logger.info(
            "REMOTE OCR SKIP reason=%s", runtime.remote_ocr_circuit_reason()
        )
        return None

    started_at = time.time()
    runtime.record_remote_ocr_start()
    runtime.logger.info("REMOTE OCR START url=%s", runtime.REMOTE_OCR_URL)
    try:
        client = runtime.get_remote_http_client(runtime.REMOTE_OCR_TIMEOUT)
        if runtime.LOCAL_HYBRID_FLAGS.worker_queue_v2:
            with runtime.remote_ocr_execution_slot():
                with image_path.open("rb") as image_file:
                    response = client.post(
                        f"{runtime.REMOTE_OCR_URL}/ocr",
                        files={"file": (image_path.name, image_file, "image/jpeg")},
                    )
        else:
            with image_path.open("rb") as image_file:
                response = client.post(
                    f"{runtime.REMOTE_OCR_URL}/ocr",
                    files={"file": (image_path.name, image_file, "image/jpeg")},
                )
        latency_ms = int((time.time() - started_at) * 1000)
        if response.status_code != 200:
            if runtime.LOCAL_HYBRID_FLAGS.busy_offline_separation and response.status_code in {429, 503}:
                runtime.record_remote_ocr_busy(f"status {response.status_code}")
                return None
            runtime.record_remote_ocr_status(
                False, latency_ms, error=f"status {response.status_code}"
            )
            runtime.mark_remote_ocr_offline(f"status {response.status_code}")
            return None
        payload = response.json()
        if payload.get("ok") is not True:
            runtime.record_remote_ocr_status(False, latency_ms, error="ok=false")
            return None
        gpu_variant_conflict = runtime.remote_variants_conflict(payload)
        cpu_review_required = cpu_payload_requires_review(payload)
        cpu_candidates = cpu_pubg_candidates(payload)
        cpu_payload = payload.get("cpu_ocr") if isinstance(payload.get("cpu_ocr"), dict) else {}
        cpu_review_reasons = tuple(
            str(reason) for reason in (cpu_payload.get("review_reasons", []) or [])
        )
        variant_conflict = gpu_variant_conflict or cpu_review_required
        original_card_scores, enhanced_card_scores = runtime.remote_variant_evidence(payload)
        original_rebuilt_card_scores = variant_rebuilt_card_scores(
            runtime, payload.get("ocr_original")
        )
        enhanced_rebuilt_card_scores = variant_rebuilt_card_scores(
            runtime, payload.get("ocr_enhanced")
        )
        worker_cards = payload.get("cards")
        if not isinstance(worker_cards, list):
            worker_cards = []

        text_items = payload.get("texts", []) or []
        ordered_lines = runtime.ordered_ocr_text_lines(text_items)
        ordered_line_cards, has_unresolved_pubg_fragment = (
            runtime.extract_cards_from_ordered_lines(ordered_lines)
        )
        text_values: list[str] = []
        for item in text_items:
            if isinstance(item, dict):
                value = str(item.get("text", "")).strip()
            else:
                value = str(item).strip()
            if value:
                text_values.append(value)
        if runtime.REMOTE_OCR_TRUST_CARDS:
            for item in worker_cards:
                if isinstance(item, dict):
                    value = str(item.get("text", "")).strip()
                else:
                    value = str(item).strip()
                if value:
                    text_values.append(value)

        raw_text = "\n".join(text_values)
        text_raw = "\n".join(line.text for line in ordered_lines)
        worker_text = "\n".join(runtime.ocr_item_text(item) for item in worker_cards)
        if ordered_lines and runtime.is_pubg_image_text(text_raw):
            extracted_cards = runtime.merge_text_rebuilt_and_worker_cards(
                ordered_line_cards,
                runtime.extract_cards(worker_text),
                [line.text for line in ordered_lines],
            )
        else:
            extracted_cards = ordered_line_cards or runtime.extract_cards(raw_text)
        recovered_prefix_cards = runtime.recover_single_prefix_digit_error(
            [line.text for line in ordered_lines], extracted_cards
        )
        for insert_at, recovered_card in recovered_prefix_cards:
            extracted_cards.insert(min(insert_at, len(extracted_cards)), recovered_card)
            runtime.logger.warning(
                "PUBG PREFIX CONSENSUS RECOVERED card=%s source=same_image_majority",
                recovered_card,
            )
        cards, uncertain, card_corrections = runtime.settle_and_correct_pubg_cards(
            extracted_cards
        )
        psn_ordered = runtime.limit_psn_ordered(
            runtime.psn_ordered_for_image(raw_text, cards, psn_hint=psn_hint),
            psn_expected_count,
        )
        psn_cards = runtime.exact_unique_psn(
            [card for card in psn_ordered if not card.endswith(runtime.FUZZY_SUFFIX)]
        )
        psn_uncertain = runtime.exact_unique_text(
            [card for card in psn_ordered if card.endswith(runtime.FUZZY_SUFFIX)]
        )
        if not cards and not psn_cards and not psn_uncertain and not cpu_candidates:
            runtime.record_remote_ocr_status(False, latency_ms, error="no valid cards")
            return None

        card_count = len(cards) + len(psn_cards) + len(psn_uncertain)
        remote_pubg_expected_count = runtime.merge_pubg_expected_count(
            pubg_expected_count, raw_text
        )
        # The original/enhanced pass can return the same complete card twice.
        # Count canonical card slots instead of raw OCR lines so a duplicate
        # display does not look like a missing second card.  Incomplete,
        # separately anchored markers remain distinct in the shared counter.
        ordered_pubg_markers = runtime.count_pubg_markers(text_raw) or 0
        if ordered_pubg_markers:
            remote_pubg_expected_count = max(
                remote_pubg_expected_count or 0, ordered_pubg_markers
            )
        runtime.mark_remote_ocr_online()
        runtime.record_remote_ocr_status(
            True,
            latency_ms,
            card_count=card_count,
            text_count=len(text_values),
            enhanced_used=bool(payload.get("enhanced_used")),
            cache_hit=bool(payload.get("cached")),
        )
        return runtime.OcrResult(
            cards=tuple(cards),
            psn_cards=tuple(psn_cards),
            psn_uncertain=tuple(psn_uncertain),
            psn_ordered=tuple(psn_ordered),
            pubg_expected_count=remote_pubg_expected_count,
            psn_expected_count=psn_expected_count,
            raw_text=raw_text,
            uncertain_count=uncertain,
            corrections_applied=card_corrections,
            remote_variant_conflict=gpu_variant_conflict,
            remote_original_card_scores=original_card_scores,
            remote_enhanced_card_scores=enhanced_card_scores,
            remote_original_rebuilt_card_scores=original_rebuilt_card_scores,
            remote_enhanced_rebuilt_card_scores=enhanced_rebuilt_card_scores,
            remote_cpu_candidates=cpu_candidates,
            remote_cpu_review_required=cpu_review_required,
            remote_cpu_review_reasons=cpu_review_reasons,
            has_unresolved_pubg_fragment=(
                has_unresolved_pubg_fragment or variant_conflict
            ),
        )
    except RemoteWorkerBusy:
        runtime.record_remote_ocr_busy("local_gate")
        return None
    except (httpx.TimeoutException, TimeoutError) as exc:
        latency_ms = int((time.time() - started_at) * 1000)
        if runtime.LOCAL_HYBRID_FLAGS.busy_offline_separation:
            healthy, _payload, _reason = runtime.remote_worker_health()
            if healthy:
                runtime.record_remote_ocr_busy(type(exc).__name__)
                return None
        runtime.record_remote_ocr_status(False, latency_ms, error=type(exc).__name__)
        runtime.mark_remote_ocr_offline(type(exc).__name__)
        return None
    except Exception as exc:
        latency_ms = int((time.time() - started_at) * 1000)
        runtime.record_remote_ocr_status(
            False, latency_ms, error=type(exc).__name__
        )
        runtime.mark_remote_ocr_offline(type(exc).__name__)
        return None

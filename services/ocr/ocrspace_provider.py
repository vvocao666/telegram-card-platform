from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
import time
from typing import Any

from services.ocr.base import OcrTextResult


def recognize_ocrspace(
    runtime: Any,
    image_path: Path,
    *,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> Any:
    """执行 OCR.space 多引擎与多 Key 回退，保持原有解析和纠错边界。"""
    if time.time() < runtime.ocrspace_cooldown_until:
        runtime.logger.warning("OCR.space is cooling down after rate limit.")
        return runtime.OcrResult(
            cards=tuple(),
            pubg_expected_count=pubg_expected_count,
            psn_expected_count=psn_expected_count,
        )
    if not runtime.OCR_SPACE_API_KEYS:
        return runtime.OcrResult(
            cards=tuple(),
            pubg_expected_count=pubg_expected_count,
            psn_expected_count=psn_expected_count,
        )

    upload_path: Path | None = None
    raw_chunks: list[str] = []
    all_cards: list[str] = []
    all_psn_ordered: list[str] = []
    ocr_stats = {
        "ocr_fixed_count": 0,
        "ocr_missing_count": 0,
        "ocr_false_negative": 0,
        "ocr_character_confusion": 0,
    }
    uncertain_total = 0
    try:
        upload_path = runtime.prepare_ocrspace_image(image_path)
        started_at = time.monotonic()
        with nullcontext(
            runtime.get_ocrspace_http_client(runtime.OCR_SPACE_TIMEOUT)
        ) as client:
            for engine in runtime.OCR_SPACE_ENGINES:
                if time.monotonic() - started_at >= runtime.OCR_SPACE_TOTAL_TIMEOUT:
                    runtime.logger.warning("OCRSPACE FAILED reason=total_timeout")
                    break
                response = None
                now = time.time()
                available_keys = [
                    key
                    for key in runtime.OCR_SPACE_API_KEYS
                    if runtime.ocrspace_key_cooldowns.get(key, 0) <= now
                ]
                if not available_keys:
                    runtime.ocrspace_cooldown_until = max(
                        runtime.ocrspace_cooldown_until,
                        min(
                            runtime.ocrspace_key_cooldowns.values(),
                            default=now + runtime.OCR_SPACE_429_COOLDOWN_SECONDS,
                        ),
                    )
                    runtime.logger.warning("All OCR.space keys are cooling down.")
                    break
                for key_index, api_key in enumerate(available_keys, start=1):
                    elapsed = time.monotonic() - started_at
                    remaining_timeout = runtime.OCR_SPACE_TOTAL_TIMEOUT - elapsed
                    if remaining_timeout <= 0:
                        runtime.logger.warning("OCRSPACE FAILED reason=total_timeout")
                        break
                    with upload_path.open("rb") as image_file:
                        request_started_at = time.monotonic()
                        try:
                            response = client.post(
                                "https://api.ocr.space/parse/image",
                                data={
                                    "apikey": api_key,
                                    "language": "eng",
                                    "OCREngine": engine,
                                    "scale": "true",
                                    "detectOrientation": "true",
                                    "isTable": "false",
                                },
                                files={
                                    "file": (
                                        upload_path.name,
                                        image_file,
                                        (
                                            "image/png"
                                            if upload_path.suffix.lower() == ".png"
                                            else "image/jpeg"
                                        ),
                                    )
                                },
                                timeout=max(
                                    0.5,
                                    min(runtime.OCR_SPACE_TIMEOUT, remaining_timeout),
                                ),
                            )
                        except runtime.httpx.TimeoutException as exc:
                            latency_ms = int(
                                (time.monotonic() - request_started_at) * 1000
                            )
                            runtime.logger.warning(
                                "OCRSPACE FAILED engine=%s key_index=%s latency_ms=%s reason=%s",
                                engine,
                                key_index,
                                latency_ms,
                                exc.__class__.__name__,
                            )
                            response = None
                            break
                    if response is None:
                        break
                    if 500 <= response.status_code <= 599:
                        latency_ms = int(
                            (time.monotonic() - request_started_at) * 1000
                        )
                        runtime.logger.warning(
                            "OCRSPACE TRANSIENT FAILURE engine=%s key_index=%s latency_ms=%s status=%s; trying next key/engine",
                            engine,
                            key_index,
                            latency_ms,
                            response.status_code,
                        )
                        # OCR.space 5xx responses are service-side failures.
                        # Do not abort the whole image: remaining configured
                        # keys and engines are a bounded, independent fallback.
                        response = None
                        continue
                    if response.status_code != 429:
                        break
                    runtime.ocrspace_key_cooldowns[api_key] = (
                        time.time() + runtime.OCR_SPACE_429_COOLDOWN_SECONDS
                    )
                    runtime.logger.warning(
                        "OCR.space key #%s rate limited; trying next key.", key_index
                    )
                    response = None
                if response is None:
                    continue
                response.raise_for_status()
                payload = response.json()
                if payload.get("IsErroredOnProcessing"):
                    runtime.logger.warning(
                        "OCR.space engine %s error: %s",
                        engine,
                        payload.get("ErrorMessage"),
                    )
                    continue

                chunks = [
                    parsed.get("ParsedText", "")
                    for parsed in payload.get("ParsedResults", []) or []
                ]
                raw_text = "\n".join(chunk for chunk in chunks if chunk)
                if raw_text:
                    raw_chunks.append(raw_text)

                if runtime.is_pubg_image_text(raw_text):
                    legacy_cards, unresolved = (
                        runtime.extract_source_anchored_pubg_cards(raw_text)
                    )
                    enhanced_cards = []
                    enhanced_stats = {
                        "ocr_fixed_count": 0,
                        "ocr_missing_count": 0,
                        "ocr_false_negative": 0,
                        "ocr_character_confusion": 0,
                    }
                    uncertain_total += int(unresolved)
                else:
                    legacy_cards = runtime.extract_cards(raw_text)
                    enhanced_cards, enhanced_stats = (
                        runtime.enhanced_ocrspace_pubg_cards(raw_text, legacy_cards)
                    )
                ocr_stats = runtime.merge_ocr_stats(ocr_stats, enhanced_stats)
                cards, uncertain, _card_corrections = (
                    runtime.settle_and_correct_pubg_cards(
                        enhanced_cards + legacy_cards
                    )
                )
                psn_ordered = runtime.psn_ordered_for_image(
                    raw_text, cards, psn_hint=psn_hint
                )
                all_cards.extend(cards)
                all_psn_ordered.extend(psn_ordered)
                uncertain_total += uncertain
                if runtime.remote_ocr_is_circuit_open() and (
                    cards or psn_ordered
                ):
                    runtime.logger.info(
                        "OCRSPACE FAST PATH engine=%s cards=%s psn=%s",
                        engine,
                        len(cards),
                        len(psn_ordered),
                    )
                    break

        merged_cards, conflict_count = runtime.merge_card_variants(all_cards)
        psn_ordered = runtime.limit_psn_ordered(
            runtime.prefer_labeled_psn_ordered(raw_chunks, all_psn_ordered),
            psn_expected_count,
        )
        psn_cards = runtime.exact_unique_psn(
            [
                card
                for card in psn_ordered
                if not card.endswith(runtime.FUZZY_SUFFIX)
            ]
        )
        psn_uncertain = runtime.exact_unique_text(
            [card for card in psn_ordered if card.endswith(runtime.FUZZY_SUFFIX)]
        )
        uncertain_total += conflict_count
        corrected_cards, correction_uncertain, card_corrections = (
            runtime.settle_and_correct_pubg_cards(merged_cards)
        )
        uncertain_total += correction_uncertain
        if corrected_cards or psn_cards or psn_uncertain:
            merged_raw_text = "\n".join(raw_chunks)
            return runtime.OcrResult(
                cards=tuple(corrected_cards),
                psn_cards=tuple(psn_cards),
                psn_uncertain=tuple(psn_uncertain),
                psn_ordered=tuple(psn_ordered),
                pubg_expected_count=runtime.merge_pubg_expected_count(
                    pubg_expected_count, merged_raw_text
                ),
                psn_expected_count=psn_expected_count,
                raw_text=merged_raw_text,
                uncertain_count=uncertain_total,
                ocr_fixed_count=ocr_stats["ocr_fixed_count"],
                ocr_missing_count=ocr_stats["ocr_missing_count"],
                ocr_false_negative=ocr_stats["ocr_false_negative"],
                ocr_character_confusion=ocr_stats["ocr_character_confusion"],
                corrections_applied=card_corrections,
            )
    except Exception:
        runtime.logger.exception("OCR.space request failed")
        return runtime.OcrResult(cards=tuple())
    finally:
        if upload_path:
            upload_path.unlink(missing_ok=True)

    merged_raw_text = "\n".join(raw_chunks)
    return runtime.OcrResult(
        cards=tuple(),
        psn_cards=tuple(),
        pubg_expected_count=runtime.merge_pubg_expected_count(
            pubg_expected_count, merged_raw_text
        ),
        psn_expected_count=psn_expected_count,
        raw_text=merged_raw_text,
        uncertain_count=uncertain_total,
        ocr_fixed_count=ocr_stats["ocr_fixed_count"],
        ocr_missing_count=ocr_stats["ocr_missing_count"],
        ocr_false_negative=ocr_stats["ocr_false_negative"],
        ocr_character_confusion=ocr_stats["ocr_character_confusion"],
    )


class OcrSpaceProvider:
    """兼容旧的文本 Provider 接口。"""

    def recognize(self, image_path: Path) -> OcrTextResult:
        from bot import run_ocrspace

        result = run_ocrspace(image_path)
        return OcrTextResult(raw_text=result.raw_text, provider="ocrspace")

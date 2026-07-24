from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from services.ocr.pubg_candidate_merge import is_same_slot_conflict
from services.ocr.source_consensus import repeated_pubg_source_consensus
from services.ocr.thin_strip_policy import is_thin_strip_image


def review_conflicting_thin_strip(
    runtime: Any,
    image_path: Path,
    result: Any,
    *,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> Any:
    """仅对细长单卡图的同槽候选冲突执行局部复核。

    该路径不能推测字符。只有 Remote 与 OCR.space 在独立的局部重读中
    返回同一张完整 PUBG 卡密时，才替换原结果；否则撤回冲突候选并要求人工核对。
    """
    source_consensus = repeated_pubg_source_consensus(result)
    if source_consensus:
        runtime.logger.info("OCR THIN STRIP SOURCE CONSENSUS card=%s", source_consensus)
        return replace(
            result,
            cards=(source_consensus,),
            pubg_expected_count=1,
            uncertain_count=0,
            has_unresolved_pubg_fragment=False,
        )
    if not _needs_review(runtime, image_path, result):
        return result

    original_cards = tuple(getattr(result, "cards", ()) or ())
    runtime.logger.warning(
        "OCR THIN STRIP REVIEW START candidates=%s", list(_raw_pubg_cards(runtime, result.raw_text))
    )
    try:
        with tempfile.TemporaryDirectory(prefix="ocr_thin_strip_review_") as directory:
            review_path = build_review_image(image_path, Path(directory))
            remote = runtime.run_remote_ocr(
                review_path,
                psn_hint=psn_hint,
                psn_expected_count=psn_expected_count,
                pubg_expected_count=pubg_expected_count,
            )
            cloud = None
            if runtime.OCR_PROVIDER == "ocrspace" and runtime.OCR_SPACE_API_KEYS:
                cloud = runtime.run_ocrspace(
                    review_path,
                    psn_hint=psn_hint,
                    psn_expected_count=psn_expected_count,
                    pubg_expected_count=pubg_expected_count,
                )
    except Exception as exc:
        runtime.logger.warning("OCR THIN STRIP REVIEW FAILED reason=%s", type(exc).__name__)
        return _drop_unconfirmed_conflict(result, original_cards)

    confirmed = _confirmed_candidate(
        runtime,
        original_cards,
        remote,
        cloud,
        original_raw_text=str(getattr(result, "raw_text", "")),
    )
    if confirmed:
        runtime.logger.info("OCR THIN STRIP REVIEW CONFIRMED card=%s", confirmed)
        review_raw = _review_raw_text(remote, cloud)
        only_confirmed_slot = _only_confirmed_slot(runtime, result, confirmed)
        return replace(
            result,
            cards=(confirmed,),
            card_locations=tuple(),
            raw_text="\n".join(part for part in (result.raw_text, review_raw) if part).strip(),
            pubg_expected_count=(
                1 if only_confirmed_slot else getattr(result, "pubg_expected_count", None)
            ),
            uncertain_count=_remaining_uncertainty(runtime, result, confirmed),
        )

    runtime.logger.warning(
        "OCR THIN STRIP REVIEW UNRESOLVED remote=%s ocrspace=%s",
        list(getattr(remote, "cards", ()) or ()),
        list(getattr(cloud, "cards", ()) or ()) if cloud is not None else [],
    )
    return _drop_unconfirmed_conflict(result, original_cards)


def build_review_image(image_path: Path, output_dir: Path) -> Path:
    """裁剪细长图的文字区域并放大，保留完整原始字符而不重排文本。"""
    with Image.open(image_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGB")
    # Preserve the whole strip. Threshold-based ROI cropping can clip the
    # faint leading "S" in small duplicate-row screenshots.
    working = source
    scale = min(4, max(1, 2600 // max(working.width, 1)))
    if scale > 1:
        working = working.resize(
            (working.width * scale, working.height * scale), Image.Resampling.LANCZOS
        )
    grayscale = ImageOps.grayscale(working)
    enhanced = ImageEnhance.Contrast(grayscale).enhance(1.6).filter(
        ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=2)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "thin_strip_review.png"
    enhanced.save(output_path, format="PNG", optimize=True)
    return output_path


def _needs_review(runtime: Any, image_path: Path, result: Any) -> bool:
    cards = tuple(getattr(result, "cards", ()) or ())
    if len(cards) != 1 or not is_thin_strip_image(image_path):
        return False
    raw_cards = _raw_pubg_cards(runtime, str(getattr(result, "raw_text", "")))
    return any(
        left != right and is_same_slot_conflict(left, right)
        for index, left in enumerate(raw_cards)
        for right in raw_cards[index + 1 :]
    )


def _raw_pubg_cards(runtime: Any, raw_text: str) -> list[str]:
    result: list[str] = []
    for card in runtime.extract_cards(raw_text):
        if runtime.valid_card(card) and card not in result:
            result.append(card)
    return result


def _confirmed_candidate(
    runtime: Any,
    originals: tuple[str, ...],
    remote: Any,
    cloud: Any,
    *,
    original_raw_text: str,
) -> str | None:
    """确认细长图冲突候选，避免因另一端短暂离线而丢卡。

    通常仍要求 Remote 和 OCR.space 在复核图上达成一致。只有原始选择已明确
    来自 OCR.space，且 OCR.space 对独立裁剪增强图再次读出同一卡时，才允许
    在 Remote 临时冷却或超时时保留该卡；这不是字符替换，也不会在其他路径生效。
    """
    remote_cards = _same_slot_cards(runtime, originals, getattr(remote, "cards", ()))
    cloud_cards = _same_slot_cards(runtime, originals, getattr(cloud, "cards", ()))
    shared = [card for card in remote_cards if card in cloud_cards]
    if len(shared) == 1:
        return shared[0]

    if "[OCRSPACE]" not in original_raw_text or len(originals) != 1:
        return None
    original = originals[0]
    if cloud_cards == [original]:
        return original
    return None


def _same_slot_cards(runtime: Any, originals: tuple[str, ...], candidates: Any) -> list[str]:
    result: list[str] = []
    for candidate in candidates or ():
        if not runtime.valid_card(candidate):
            continue
        if any(is_same_slot_conflict(candidate, original) for original in originals):
            if candidate not in result:
                result.append(candidate)
    return result


def _review_raw_text(remote: Any, cloud: Any) -> str:
    parts = []
    if remote is not None and getattr(remote, "raw_text", ""):
        parts.append(f"[THIN_STRIP_REVIEW_REMOTE]\n{remote.raw_text.strip()}")
    if cloud is not None and getattr(cloud, "raw_text", ""):
        parts.append(f"[THIN_STRIP_REVIEW_OCRSPACE]\n{cloud.raw_text.strip()}")
    return "\n".join(parts)


def _remaining_uncertainty(runtime: Any, result: Any, confirmed: str) -> int:
    """只清除已被独立复核解决的同槽冲突，不掩盖其他卡槽的不确定性。"""

    if _only_confirmed_slot(runtime, result, confirmed):
        return 0
    return int(getattr(result, "uncertain_count", 0) or 0)


def _only_confirmed_slot(runtime: Any, result: Any, confirmed: str) -> bool:
    raw_cards = _raw_pubg_cards(runtime, str(getattr(result, "raw_text", "")))
    return bool(raw_cards) and all(
        card == confirmed or is_same_slot_conflict(card, confirmed) for card in raw_cards
    )


def _drop_unconfirmed_conflict(result: Any, original_cards: tuple[str, ...]) -> Any:
    """冲突无法独立确认时不输出任一候选，避免把假卡交给用户。"""
    return replace(
        result,
        cards=tuple(card for card in result.cards if card not in original_cards),
        card_locations=tuple(),
        pubg_expected_count=max(int(getattr(result, "pubg_expected_count", 0) or 0), len(original_cards)),
        uncertain_count=int(getattr(result, "uncertain_count", 0) or 0) + 1,
        has_unresolved_pubg_fragment=True,
    )

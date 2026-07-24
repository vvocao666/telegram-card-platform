from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from services.ocr.thin_strip_review import review_conflicting_thin_strip
from services.ocr.clear_fast_path import confirmed_clear_remote_card
from services.ocr.prefix_recovery_policy import choose_cloud_same_slot_card
from services.ocr.remote_variant_policy import cloud_resolves_remote_variant_conflict
from services.ocr.source_consensus import (
    exact_pubg_cross_source_consensus,
    repeated_pubg_source_consensus,
)
from services.ocr.multi_card_consensus import (
    complete_dual_variant_multi_card_consensus,
    dual_variant_multi_card_consensus,
)
from services.ocr.multi_source_decision import (
    apply_cpu_cloud_confirmations,
    cpu_cloud_confirmed_cards,
)


def _review_thin_strip(
    runtime: Any,
    image_path: Path,
    result: Any,
    *,
    psn_hint: bool,
    psn_expected_count: int | None,
    pubg_expected_count: int | None,
) -> Any:
    return review_conflicting_thin_strip(
        runtime,
        image_path,
        result,
        psn_hint=psn_hint,
        psn_expected_count=psn_expected_count,
        pubg_expected_count=pubg_expected_count,
    )


def route_ocr(
    runtime: Any,
    image_path: Path,
    *,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> Any:
    """编排 Remote、OCR.space 与本地 OCR，运行时对象仅提供兼容依赖。"""
    remote = runtime.run_remote_ocr(
        image_path,
        psn_hint=psn_hint,
        psn_expected_count=psn_expected_count,
        pubg_expected_count=pubg_expected_count,
    )
    clear_remote_card = confirmed_clear_remote_card(remote) if remote is not None else None
    if clear_remote_card and runtime.is_thin_strip_image(image_path):
        runtime.logger.info(
            "OCR FAST PATH provider=remote evidence=gpu_original+gpu_enhanced+cpu card=%s",
            clear_remote_card,
        )
        return remote
    if (
        remote is not None
        and runtime.is_thin_strip_image(image_path)
        and runtime.OCR_PROVIDER == "ocrspace"
        and runtime.OCR_SPACE_API_KEYS
    ):
        cloud = runtime.run_ocrspace(
            image_path,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )
        selected, changed = runtime.choose_thin_strip_result(
            remote, cloud, valid_card=runtime.valid_card
        )
        if selected is cloud:
            selected = replace(
                cloud,
                raw_text=(
                    f"[REMOTE]\n{remote.raw_text.strip()}\n"
                    f"[OCRSPACE]\n{cloud.raw_text.strip()}"
                ).strip(),
                remote_original_card_scores=remote.remote_original_card_scores,
                remote_enhanced_card_scores=remote.remote_enhanced_card_scores,
                remote_original_rebuilt_card_scores=remote.remote_original_rebuilt_card_scores,
                remote_enhanced_rebuilt_card_scores=remote.remote_enhanced_rebuilt_card_scores,
                remote_cpu_candidates=remote.remote_cpu_candidates,
                remote_cpu_review_required=remote.remote_cpu_review_required,
                remote_cpu_review_reasons=remote.remote_cpu_review_reasons,
            )
            if changed:
                runtime.logger.warning(
                    "OCR THIN STRIP CONFLICT remote=%s cloud=%s selected=ocrspace",
                    list(remote.cards),
                    list(cloud.cards),
                )
            else:
                runtime.logger.info("OCR THIN STRIP VERIFIED card=%s", cloud.cards[0])
            return _review_thin_strip(
                runtime,
                image_path,
                selected,
                psn_hint=psn_hint,
                psn_expected_count=psn_expected_count,
                pubg_expected_count=pubg_expected_count,
            )

    complete_multi_card_consensus = (
        complete_dual_variant_multi_card_consensus(remote)
        if remote is not None
        else None
    )
    if complete_multi_card_consensus:
        runtime.logger.info(
            "OCR MULTI CARD DUAL VARIANT FAST PATH cards=%s",
            len(complete_multi_card_consensus),
        )
        return replace(
            remote,
            cards=complete_multi_card_consensus,
            pubg_expected_count=len(complete_multi_card_consensus),
            uncertain_count=0,
            has_unresolved_pubg_fragment=False,
        )

    needs_complement = False
    complement_reason = ""
    if remote is not None:
        needs_complement, complement_reason = runtime.remote_needs_ocrspace_complement(remote)
    if (
        remote is not None
        and needs_complement
        and runtime.OCR_PROVIDER == "ocrspace"
        and runtime.OCR_SPACE_API_KEYS
    ):
        runtime.record_remote_ocr_fallback(complement_reason)
        fallback = runtime.run_ocrspace(
            image_path,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )
        merged_raw_text = (
            f"[REMOTE]\n{remote.raw_text.strip()}\n"
            f"[OCRSPACE]\n{fallback.raw_text.strip()}"
        ).strip()
        source_consensus_result = replace(remote, raw_text=merged_raw_text)
        exact_cross_source = exact_pubg_cross_source_consensus(remote, fallback)
        if exact_cross_source:
            runtime.logger.info(
                "OCR EXACT CROSS SOURCE CONSENSUS card=%s", exact_cross_source
            )
            return replace(
                source_consensus_result,
                cards=(exact_cross_source,),
                pubg_expected_count=1,
                uncertain_count=0,
                has_unresolved_pubg_fragment=False,
            )
        multi_card_consensus = dual_variant_multi_card_consensus(
            source_consensus_result, fallback
        )
        if multi_card_consensus:
            runtime.logger.info(
                "OCR MULTI CARD DUAL VARIANT CONSENSUS cards=%s",
                len(multi_card_consensus),
            )
            return replace(
                source_consensus_result,
                cards=multi_card_consensus,
                pubg_expected_count=len(multi_card_consensus),
                uncertain_count=0,
                has_unresolved_pubg_fragment=False,
            )
        source_consensus = repeated_pubg_source_consensus(
            source_consensus_result,
            cloud_candidates=tuple(fallback.cards),
            adjacent_wrap_only=not runtime.is_thin_strip_image(image_path),
        )
        if source_consensus:
            runtime.logger.info(
                "OCR SOURCE CONSENSUS BEFORE CPU card=%s", source_consensus
            )
            return replace(
                source_consensus_result,
                cards=(source_consensus,),
                pubg_expected_count=1,
                uncertain_count=0,
                has_unresolved_pubg_fragment=False,
            )
        cpu_cloud_cards = cpu_cloud_confirmed_cards(
            tuple(remote.remote_cpu_candidates), tuple(fallback.cards)
        )
        cpu_cloud_result, cpu_cloud_resolved = apply_cpu_cloud_confirmations(
            tuple(remote.cards),
            cpu_cloud_cards,
            likely_same_card=runtime.likely_same_card,
        )
        if cpu_cloud_resolved:
            runtime.logger.warning(
                "OCR CPU+CLOUD CONFIRMED cards=%s resolved=%s",
                list(cpu_cloud_cards),
                cpu_cloud_resolved,
            )
        if complement_reason == "recovered pubg prefix requires cloud confirmation":
            confirmed = choose_cloud_same_slot_card(
                tuple(remote.cards),
                tuple(fallback.cards),
                valid_card=runtime.valid_card,
            )
            if confirmed:
                runtime.logger.warning(
                    "OCRSPACE PREFIX REVIEW SELECTED card=%s remote=%s",
                    confirmed,
                    list(remote.cards),
                )
                return _review_thin_strip(
                    runtime,
                    image_path,
                    replace(
                        fallback,
                        cards=(confirmed,),
                        raw_text=(
                            f"[REMOTE]\n{remote.raw_text.strip()}\n"
                            f"[OCRSPACE_PREFIX_REVIEW]\n{fallback.raw_text.strip()}"
                        ).strip(),
                    ),
                    psn_hint=psn_hint,
                    psn_expected_count=psn_expected_count,
                    pubg_expected_count=pubg_expected_count,
                )
        if cpu_cloud_resolved:
            merged, conflict_count = runtime.merge_without_guessing(
                list(cpu_cloud_result), list(fallback.cards)
            )
        elif len(fallback.cards) >= len(remote.cards):
            merged, conflict_count = runtime.merge_without_guessing(
                list(fallback.cards), list(remote.cards)
            )
        else:
            # 云端只补到部分卡密时保留 Remote 图片顺序，避免补充导致倒序。
            merged, conflict_count = runtime.merge_without_guessing(
                list(remote.cards), list(fallback.cards)
            )
        settled_cards, correction_conflicts, card_corrections = (
            runtime.settle_and_correct_pubg_cards(merged)
        )
        resolved_variant_conflict = cloud_resolves_remote_variant_conflict(
            remote,
            fallback,
            valid_card=runtime.valid_card,
        )
        if resolved_variant_conflict:
            conflict_count = max(0, conflict_count - 1)
            runtime.logger.info(
                "OCR VARIANT CONFLICT RESOLVED card=%s evidence=enhanced+higher_confidence+ocrspace",
                fallback.cards[0],
            )
        merged_psn = runtime.exact_unique_psn(
            list(remote.psn_cards) + list(fallback.psn_cards)
        )
        merged_psn_uncertain = runtime.exact_unique_text(
            list(remote.psn_uncertain) + list(fallback.psn_uncertain)
        )
        merged_psn_ordered = runtime.limit_psn_ordered(
            list(remote.psn_ordered) + list(fallback.psn_ordered), psn_expected_count
        )
        if settled_cards or runtime.is_pubg_image_text(merged_raw_text):
            merged_psn = []
            merged_psn_uncertain = []
            merged_psn_ordered = []
        if settled_cards or merged_psn or merged_psn_uncertain:
            return _review_thin_strip(
                runtime,
                image_path,
                runtime.OcrResult(
                cards=tuple(settled_cards),
                psn_cards=tuple(merged_psn),
                psn_uncertain=tuple(merged_psn_uncertain),
                psn_ordered=tuple(merged_psn_ordered),
                pubg_expected_count=max(pubg_expected_count or 0, len(settled_cards)) or None,
                psn_expected_count=psn_expected_count,
                raw_text=merged_raw_text,
                uncertain_count=(
                    remote.uncertain_count
                    + fallback.uncertain_count
                    + conflict_count
                    + correction_conflicts
                ),
                ocr_fixed_count=remote.ocr_fixed_count + fallback.ocr_fixed_count,
                ocr_missing_count=remote.ocr_missing_count + fallback.ocr_missing_count,
                ocr_false_negative=remote.ocr_false_negative + fallback.ocr_false_negative,
                ocr_character_confusion=(
                    remote.ocr_character_confusion + fallback.ocr_character_confusion
                ),
                corrections_applied=tuple(
                    list(remote.corrections_applied)
                    + list(fallback.corrections_applied)
                    + list(card_corrections)
                ),
                remote_variant_conflict=False,
                remote_original_card_scores=remote.remote_original_card_scores,
                remote_enhanced_card_scores=remote.remote_enhanced_card_scores,
                remote_original_rebuilt_card_scores=remote.remote_original_rebuilt_card_scores,
                remote_enhanced_rebuilt_card_scores=remote.remote_enhanced_rebuilt_card_scores,
                remote_cpu_candidates=remote.remote_cpu_candidates,
                remote_cpu_review_required=remote.remote_cpu_review_required,
                remote_cpu_review_reasons=remote.remote_cpu_review_reasons,
                ),
                psn_hint=psn_hint,
                psn_expected_count=psn_expected_count,
                pubg_expected_count=pubg_expected_count,
            )

    if remote is not None:
        runtime.logger.info(
            "OCR FAST PATH provider=remote cards=%s psn=%s markers=%s",
            len(remote.cards),
            len(remote.psn_cards) + len(remote.psn_uncertain),
            runtime.count_pubg_markers(remote.raw_text) or 0,
        )
        return _review_thin_strip(
            runtime,
            image_path,
            remote,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )

    if runtime.OCR_PROVIDER == "ocrspace" and runtime.OCR_SPACE_API_KEYS:
        runtime.record_remote_ocr_fallback(runtime.remote_ocr_fallback_reason())
        cloud = runtime.run_ocrspace(
            image_path,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )
        if (
            cloud.cards or cloud.psn_cards or cloud.psn_uncertain
        ) and not runtime.VERIFY_WITH_LOCAL and not runtime.LOCAL_COMPLEMENT:
            return _review_thin_strip(
                runtime,
                image_path,
                cloud,
                psn_hint=psn_hint,
                psn_expected_count=psn_expected_count,
                pubg_expected_count=pubg_expected_count,
            )
        if not runtime.LOCAL_FALLBACK and not runtime.VERIFY_WITH_LOCAL:
            return _review_thin_strip(
                runtime,
                image_path,
                cloud,
                psn_hint=psn_hint,
                psn_expected_count=psn_expected_count,
                pubg_expected_count=pubg_expected_count,
            )

        local = runtime.run_local_ocr(
            image_path,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )
        merged, uncertain = runtime.merge_without_guessing(
            list(cloud.cards), list(local.cards)
        )
        merged_psn = runtime.exact_unique_psn(
            list(cloud.psn_cards) + list(local.psn_cards)
        )
        merged_psn_uncertain = runtime.exact_unique_text(
            list(cloud.psn_uncertain) + list(local.psn_uncertain)
        )
        merged_psn_ordered = runtime.limit_psn_ordered(
            list(cloud.psn_ordered) + list(local.psn_ordered), psn_expected_count
        )
        settled_cards, conflict_count, card_corrections = (
            runtime.settle_and_correct_pubg_cards(merged)
        )
        merged_raw_text = cloud.raw_text + "\n" + local.raw_text
        if settled_cards or runtime.is_pubg_image_text(merged_raw_text):
            merged_psn = []
            merged_psn_uncertain = []
            merged_psn_ordered = []
        uncertain += cloud.uncertain_count + local.uncertain_count + conflict_count
        if settled_cards or merged_psn or merged_psn_uncertain:
            return runtime.OcrResult(
                cards=tuple(settled_cards),
                psn_cards=tuple(merged_psn),
                psn_uncertain=tuple(merged_psn_uncertain),
                psn_ordered=tuple(merged_psn_ordered),
                pubg_expected_count=pubg_expected_count,
                psn_expected_count=psn_expected_count,
                raw_text=merged_raw_text,
                uncertain_count=uncertain,
                ocr_fixed_count=cloud.ocr_fixed_count + local.ocr_fixed_count,
                ocr_missing_count=cloud.ocr_missing_count + local.ocr_missing_count,
                ocr_false_negative=cloud.ocr_false_negative + local.ocr_false_negative,
                ocr_character_confusion=(
                    cloud.ocr_character_confusion + local.ocr_character_confusion
                ),
                corrections_applied=tuple(
                    list(cloud.corrections_applied)
                    + list(local.corrections_applied)
                    + list(card_corrections)
                ),
            )
        return runtime.OcrResult(
            cards=tuple(),
            psn_cards=tuple(),
            psn_uncertain=tuple(merged_psn_uncertain),
            psn_ordered=tuple(merged_psn_ordered),
            pubg_expected_count=pubg_expected_count,
            psn_expected_count=psn_expected_count,
            raw_text=merged_raw_text,
            uncertain_count=uncertain,
            ocr_fixed_count=cloud.ocr_fixed_count + local.ocr_fixed_count,
            ocr_missing_count=cloud.ocr_missing_count + local.ocr_missing_count,
            ocr_false_negative=cloud.ocr_false_negative + local.ocr_false_negative,
            ocr_character_confusion=(
                cloud.ocr_character_confusion + local.ocr_character_confusion
            ),
            corrections_applied=tuple(
                list(cloud.corrections_applied) + list(local.corrections_applied)
            ),
        )

    return runtime.run_local_ocr(
        image_path,
        psn_hint=psn_hint,
        psn_expected_count=psn_expected_count,
        pubg_expected_count=pubg_expected_count,
    )

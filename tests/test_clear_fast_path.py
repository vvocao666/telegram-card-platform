from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from services.ocr.clear_fast_path import confirmed_clear_remote_card
from services.ocr.provider_orchestration import route_ocr


CARD = "S07336-ABCD-EFGH-JKLMN"


def result(**overrides):
    values = {
        "cards": (CARD,),
        "psn_cards": (),
        "uncertain_count": 0,
        "has_unresolved_pubg_fragment": False,
        "remote_variant_conflict": False,
        "pubg_expected_count": 1,
        "remote_original_card_scores": ((CARD, 0.995),),
        "remote_enhanced_card_scores": ((CARD, 0.996),),
        "remote_cpu_candidates": (CARD,),
        "remote_cpu_review_required": False,
        "remote_cpu_review_reasons": (),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_three_exact_sources_allow_clear_fast_path():
    assert confirmed_clear_remote_card(result()) == CARD


def test_cpu_disagreement_keeps_existing_review_path():
    other = "S07336-ABCD-EFGH-JKLMX"
    assert confirmed_clear_remote_card(result(remote_cpu_candidates=(other,))) is None


def test_missing_enhanced_evidence_keeps_existing_review_path():
    assert confirmed_clear_remote_card(result(remote_enhanced_card_scores=())) is None


def test_low_confidence_keeps_existing_review_path():
    assert (
        confirmed_clear_remote_card(
            result(remote_original_card_scores=((CARD, 0.97),))
        )
        is None
    )


def test_thin_strip_shape_only_review_allows_exact_three_source_consensus():
    current = result(
        has_unresolved_pubg_fragment=True,
        remote_original_card_scores=((CARD, 0.9775),),
        remote_enhanced_card_scores=((CARD, 0.9999),),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg",),
    )

    assert confirmed_clear_remote_card(current) == CARD


def test_thin_strip_consensus_requires_one_strong_gpu_read():
    current = result(
        has_unresolved_pubg_fragment=True,
        remote_original_card_scores=((CARD, 0.9775),),
        remote_enhanced_card_scores=((CARD, 0.9849),),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg",),
    )

    assert confirmed_clear_remote_card(current) is None


def test_thin_strip_consensus_does_not_clear_other_review_reasons():
    current = result(
        has_unresolved_pubg_fragment=True,
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg", "line_roi_recovery"),
    )

    assert confirmed_clear_remote_card(current) is None


def test_uncertainty_keeps_existing_review_path():
    assert confirmed_clear_remote_card(result(uncertain_count=1)) is None


def test_multiple_cards_keep_existing_review_path():
    assert confirmed_clear_remote_card(result(cards=(CARD, CARD))) is None


def test_non_pubg_value_never_uses_clear_fast_path():
    psn = "ABCD-EFGH-JKLM"
    assert (
        confirmed_clear_remote_card(
            result(
                cards=(psn,),
                remote_original_card_scores=((psn, 0.999),),
                remote_enhanced_card_scores=((psn, 0.999),),
                remote_cpu_candidates=(psn,),
            )
        )
        is None
    )


def test_route_skips_ocrspace_only_for_confirmed_clear_remote_card():
    remote = result()

    class Runtime:
        OCR_PROVIDER = "ocrspace"
        OCR_SPACE_API_KEYS = ("unused",)
        logger = SimpleNamespace(info=lambda *args: None)

        @staticmethod
        def run_remote_ocr(*args, **kwargs):
            return remote

        @staticmethod
        def is_thin_strip_image(*args, **kwargs):
            return True

        @staticmethod
        def run_ocrspace(*args, **kwargs):
            raise AssertionError("confirmed clear remote result must skip OCR.space")

    assert route_ocr(Runtime(), Path("unused.png")) is remote


def test_route_skips_noisy_cloud_for_exact_thin_strip_three_source_consensus():
    remote = result(
        has_unresolved_pubg_fragment=True,
        remote_original_card_scores=((CARD, 0.9775),),
        remote_enhanced_card_scores=((CARD, 0.9999),),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg",),
    )

    class Runtime:
        OCR_PROVIDER = "ocrspace"
        OCR_SPACE_API_KEYS = ("unused",)
        logger = SimpleNamespace(info=lambda *args: None)

        @staticmethod
        def run_remote_ocr(*args, **kwargs):
            return remote

        @staticmethod
        def is_thin_strip_image(*args, **kwargs):
            return True

        @staticmethod
        def run_ocrspace(*args, **kwargs):
            raise AssertionError("exact GPU+CPU consensus must not call noisy OCR.space")

    assert route_ocr(Runtime(), Path("unused.png")) is remote

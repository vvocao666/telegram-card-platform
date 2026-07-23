from types import SimpleNamespace

from services.ocr.multi_card_consensus import dual_variant_multi_card_consensus
from services.ocr.variant_rebuild_evidence import variant_rebuilt_card_scores
from services import runtime


CARDS = (
    "S07336-6LHE-R6DA-2YHHN",
    "S07336-YDCG-SCWP-WF977",
    "S07336-QEDY-ST2R-HTJDA",
    "S07336-2Z38-JYAU-3LX7L",
)


def test_variant_rebuilds_wrapped_cards_in_coordinate_order():
    payload = {
        "texts": [
            {"text": "HTJDA", "score": 0.991, "box": [10, 150, 100, 170]},
            {"text": "S07336-6LHE-R6DA-2YHHN", "score": 0.999, "box": [10, 10, 280, 30]},
            {"text": "S07336-YDCG-SCWP-", "score": 0.998, "box": [10, 50, 220, 70]},
            {"text": "WF977", "score": 0.997, "box": [10, 75, 100, 95]},
            {"text": "S07336-QEDY-ST2R-", "score": 0.996, "box": [10, 120, 220, 140]},
            {"text": "S07336-2Z38-", "score": 0.995, "box": [10, 190, 180, 210]},
            {"text": "JYAU-3LX7L", "score": 0.994, "box": [10, 220, 160, 240]},
        ]
    }

    evidence = variant_rebuilt_card_scores(runtime, payload)

    assert tuple(card for card, _score in evidence) == CARDS
    assert evidence[1][1] == 0.997
    assert evidence[2][1] == 0.991
    assert evidence[3][1] == 0.994


def test_variant_does_not_join_across_label_or_next_card():
    payload = {
        "texts": [
            {"text": "S07336-YDCG-SCWP-", "score": 0.999, "box": [10, 10, 220, 30]},
            {"text": "密码：", "score": 0.999, "box": [10, 40, 80, 60]},
            {"text": "WF977", "score": 0.999, "box": [10, 70, 100, 90]},
            {"text": "S07336-QEDY-ST2R-", "score": 0.999, "box": [10, 100, 220, 120]},
            {"text": "HTJDA", "score": 0.999, "box": [10, 130, 100, 150]},
        ]
    }

    evidence = variant_rebuilt_card_scores(runtime, payload)

    assert evidence == (("S07336-QEDY-ST2R-HTJDA", 0.999),)


def _result(
    cards=CARDS,
    *,
    original=CARDS,
    enhanced=CARDS,
    scores=(0.999, 0.998, 0.997, 0.996),
    expected=4,
    uncertain=0,
):
    return SimpleNamespace(
        cards=cards,
        psn_cards=tuple(),
        pubg_expected_count=expected,
        uncertain_count=uncertain,
        remote_original_rebuilt_card_scores=tuple(zip(original, scores)),
        remote_enhanced_rebuilt_card_scores=tuple(zip(enhanced, scores)),
    )


def test_dual_variant_multi_card_consensus_accepts_one_cloud_character_conflict():
    cloud = _result(
        cards=CARDS[:3] + ("S07336-2238-JYAU-3LX7L",),
        expected=None,
    )

    assert dual_variant_multi_card_consensus(_result(), cloud) == CARDS


def test_dual_variant_multi_card_consensus_accepts_ordered_partial_cloud_evidence():
    cloud = _result(
        cards=(CARDS[0], CARDS[2], "S07336-2238-JYAU-3LX7L"),
        expected=None,
    )

    assert dual_variant_multi_card_consensus(_result(), cloud) == CARDS


def test_dual_variant_multi_card_consensus_rejects_low_score():
    remote = _result(scores=(0.999, 0.998, 0.997, 0.96))
    cloud = _result(cards=CARDS[:3] + ("S07336-2238-JYAU-3LX7L",), expected=None)

    assert dual_variant_multi_card_consensus(remote, cloud) is None


def test_dual_variant_multi_card_consensus_rejects_variant_mismatch():
    wrong = CARDS[:3] + ("S07336-2238-JYAU-3LX7L",)
    cloud = _result(cards=wrong, expected=None)

    assert dual_variant_multi_card_consensus(_result(enhanced=wrong), cloud) is None


def test_dual_variant_multi_card_consensus_rejects_cloud_reorder():
    cloud = _result(cards=(CARDS[1], CARDS[0], CARDS[2], CARDS[3]), expected=None)

    assert dual_variant_multi_card_consensus(_result(), cloud) is None


def test_dual_variant_multi_card_consensus_rejects_multi_character_conflict():
    cloud = _result(
        cards=CARDS[:3] + ("S07336-2238-JYAU-3LX77",),
        expected=None,
    )

    assert dual_variant_multi_card_consensus(_result(), cloud) is None


def test_dual_variant_multi_card_consensus_rejects_cpu_character_candidate():
    remote = _result()
    remote.remote_cpu_candidates = ("S07336-2238-JYAU-3LX7L",)
    cloud = _result(cards=(CARDS[0], CARDS[2], CARDS[3]), expected=None)

    assert dual_variant_multi_card_consensus(remote, cloud) is None

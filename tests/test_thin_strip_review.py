from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from services.ocr.manual_review import ManualReviewNotifier
from services.ocr.thin_strip_review import (
    build_review_image,
    build_retry_review_image,
    review_conflicting_thin_strip,
)


PUBG_RE = re.compile(r"^S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}$", re.MULTILINE)


@dataclass(frozen=True)
class Result:
    cards: tuple[str, ...] = ()
    psn_cards: tuple[str, ...] = ()
    psn_uncertain: tuple[str, ...] = ()
    psn_ordered: tuple[str, ...] = ()
    card_locations: tuple[tuple[str, int, int], ...] = ()
    pubg_expected_count: int | None = None
    psn_expected_count: int | None = None
    raw_text: str = ""
    uncertain_count: int = 0
    has_unresolved_pubg_fragment: bool = False
    remote_original_card_scores: tuple[tuple[str, float], ...] = ()
    remote_enhanced_card_scores: tuple[tuple[str, float], ...] = ()
    remote_cpu_candidates: tuple[str, ...] = ()
    remote_cpu_review_required: bool = False
    remote_cpu_review_reasons: tuple[str, ...] = ()


class Runtime:
    OCR_PROVIDER = "ocrspace"
    OCR_SPACE_API_KEYS = ["test"]
    logger = logging.getLogger("thin-strip-review-test")

    def __init__(self, remote: Result | None, cloud: Result | None) -> None:
        self.remote = remote
        self.cloud = cloud
        self.remote_calls = 0
        self.cloud_calls = 0

    @staticmethod
    def valid_card(value: str) -> bool:
        return bool(PUBG_RE.fullmatch(value))

    def extract_cards(self, text: str) -> list[str]:
        return PUBG_RE.findall(text)

    def run_remote_ocr(self, *_args, **_kwargs):
        self.remote_calls += 1
        return self.remote

    def run_ocrspace(self, *_args, **_kwargs):
        self.cloud_calls += 1
        return self.cloud


def make_thin_image(tmp_path: Path) -> Path:
    path = tmp_path / "thin.jpg"
    Image.new("RGB", (700, 100), "white").save(path)
    return path


def test_review_image_preserves_full_strip_before_upscale(tmp_path):
    image = tmp_path / "duplicate-rows.jpg"
    source = Image.new("RGB", (236, 83), "white")
    source.putpixel((0, 40), (0, 0, 0))
    source.save(image)

    review = build_review_image(image, tmp_path / "review")

    with Image.open(review) as opened:
        assert opened.size == (944, 332)
        assert opened.getpixel((0, 160)) < 255


def test_retry_review_image_adds_padding_without_clipping_strip_edges(tmp_path):
    image = tmp_path / "faint-card.jpg"
    source = Image.new("RGB", (260, 50), "white")
    source.putpixel((0, 25), (0, 0, 0))
    source.save(image)

    review = build_retry_review_image(image, tmp_path / "review")

    with Image.open(review) as opened:
        assert opened.size == (1340, 290)
        assert opened.getpixel((20, 145)) < 255


def test_conflicting_thin_strip_uses_independent_matching_review_results(tmp_path):
    image = make_thin_image(tmp_path)
    initial = Result(
        cards=("S07330-FSQH-FWJD-W3N8D",),
        raw_text="S07330-FSQH-FWJD-W3N8D\nS07330-FSQH-FVJD-W3N8D",
        pubg_expected_count=2,
        uncertain_count=1,
    )
    corrected = Result(cards=("S07330-FSQH-FJVD-W3N8D",), raw_text="S07330-FSQH-FJVD-W3N8D")
    runtime = Runtime(corrected, corrected)

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == ("S07330-FSQH-FJVD-W3N8D",)
    assert result.pubg_expected_count == 1
    assert result.uncertain_count == 0
    assert "[THIN_STRIP_REVIEW_REMOTE]" in result.raw_text
    assert "[THIN_STRIP_REVIEW_OCRSPACE]" in result.raw_text
    assert runtime.remote_calls == 1
    assert runtime.cloud_calls == 1
    assert ManualReviewNotifier().needs_review(result) is None


def test_confirmed_same_slot_conflict_does_not_trigger_false_missing_count_review(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07324-8K4P-AQ4Z-CXHPL"
    conflicting = "S07324-BK4P-AQ4Z-CXHPL"
    initial = Result(
        cards=(confirmed,),
        raw_text=f"{confirmed}\n{conflicting}",
        pubg_expected_count=2,
        uncertain_count=1,
    )
    runtime = Runtime(
        Result(cards=(confirmed,), raw_text=confirmed),
        Result(cards=(confirmed,), raw_text=f"{confirmed}\n{confirmed}"),
    )

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == (confirmed,)
    assert result.pubg_expected_count == 1
    assert result.uncertain_count == 0
    assert ManualReviewNotifier().needs_review(result) is None


def test_unconfirmed_thin_strip_conflict_is_not_output_as_a_false_card(tmp_path):
    image = make_thin_image(tmp_path)
    initial = Result(
        cards=("S07330-FSQH-FWJD-W3N8D",),
        raw_text="S07330-FSQH-FWJD-W3N8D\nS07330-FSQH-FVJD-W3N8D",
    )
    runtime = Runtime(
        Result(cards=("S07330-FSQH-FJVD-W3N8D",)),
        Result(cards=("S07330-FSQH-FVJD-W3N8D",)),
    )

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == ()
    assert result.uncertain_count == 1
    assert result.has_unresolved_pubg_fragment is True
    assert runtime.remote_calls == 2
    assert runtime.cloud_calls == 2


def test_second_review_render_can_resolve_a_tiny_single_card_conflict(tmp_path):
    image = make_thin_image(tmp_path)
    initial = Result(
        cards=("S07362-QZZ3-GBT8-K2JWP",),
        raw_text="S07362-QZZ3-GBT8-K2JWP\nS07362-QZZ3-GBT8-K2JWR",
        uncertain_count=1,
    )
    first_remote = Result(cards=("S07362-QZZ3-GBT8-K2JWP",))
    first_cloud = Result(cards=("S07362-QZZ3-GBT8-K2JWR",))
    confirmed = Result(cards=("S07362-QZZ3-GBT8-K2JWP",))

    class RetryRuntime(Runtime):
        def __init__(self):
            super().__init__(None, None)
            self.remote_results = [first_remote, confirmed]
            self.cloud_results = [first_cloud, confirmed]

        def run_remote_ocr(self, *_args, **_kwargs):
            self.remote_calls += 1
            return self.remote_results.pop(0)

        def run_ocrspace(self, *_args, **_kwargs):
            self.cloud_calls += 1
            return self.cloud_results.pop(0)

    runtime = RetryRuntime()
    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == ("S07362-QZZ3-GBT8-K2JWP",)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False
    assert runtime.remote_calls == 2
    assert runtime.cloud_calls == 2


def test_gpu_variants_and_cpu_confirm_remote_tail_over_wrong_cloud_review(tmp_path):
    image = make_thin_image(tmp_path)
    correct = "S07317-4WW8-F35W-RJA3W"
    cloud_wrong = "S07317-4WW8-F35W-RJA3T"
    initial = Result(
        cards=(correct,),
        raw_text=f"[REMOTE]\n{correct}\n[OCRSPACE]\n{cloud_wrong}",
        uncertain_count=1,
    )
    remote_review = Result(
        cards=(correct,),
        raw_text=correct,
        remote_original_card_scores=((correct, 0.9946),),
        remote_enhanced_card_scores=((correct, 0.9991),),
        remote_cpu_candidates=(correct,),
        remote_cpu_review_required=True,
        remote_cpu_review_reasons=("thin_strip_pubg",),
    )
    runtime = Runtime(remote_review, Result(cards=(cloud_wrong,), raw_text=cloud_wrong))

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == (correct,)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False


def test_ocrspace_repeat_confirms_conflict_when_remote_review_is_temporarily_unavailable(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07336-BFE9-UMA7-L33X8"
    initial = Result(
        cards=(confirmed,),
        raw_text=(
            "[REMOTE]\nS07336-BFE9-UMA7-L33X6\n"
            "[OCRSPACE]\nS07336-BFE9-UMA7-L33X8"
        ),
        uncertain_count=1,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(
        runtime,
        image,
        initial,
        primary_provider="ocrspace",
    )

    assert result.cards == (confirmed,)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False
    assert runtime.remote_calls == 1
    assert runtime.cloud_calls == 1


def test_cloud_primary_and_independent_review_confirm_same_single_card(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07330-QL67-QUWH-SWPEB"
    conflicting = "S07330-QL67-QUWH-SWEB"
    initial = Result(
        cards=(confirmed,),
        raw_text=f"{conflicting}\n{confirmed}",
        uncertain_count=1,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(
        runtime,
        image,
        initial,
        primary_provider="ocrspace",
    )

    assert result.cards == (confirmed,)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False
    assert runtime.remote_calls == 1
    assert runtime.cloud_calls == 1
    assert ManualReviewNotifier().needs_review(result) is None


def test_cloud_review_resolves_multiple_variants_from_one_card_slot(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07330-UFZ6-DWUD-4FSRL"
    initial = Result(
        cards=("S07330-UF26-DWUD-4FSRL",),
        raw_text="S07330-UF26-DWUD-4FSRL\nS07330-UF26-DWUD-4FSAL",
        uncertain_count=2,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(
        runtime,
        image,
        initial,
        primary_provider="ocrspace",
    )

    assert result.cards == (confirmed,)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False
    assert ManualReviewNotifier().needs_review(result) is None


def test_cloud_review_does_not_merge_candidates_from_different_card_slots(tmp_path):
    image = make_thin_image(tmp_path)
    initial = Result(
        cards=("S07330-UF26-DWUD-4FSRL",),
        raw_text="S07330-UF26-DWUD-4FSRL\nS07336-ABCD-EFGH-JKLMN",
        uncertain_count=2,
    )
    runtime = Runtime(
        None,
        Result(cards=("S07330-UFZ6-DWUD-4FSRL",), raw_text="S07330-UFZ6-DWUD-4FSRL"),
    )

    result = review_conflicting_thin_strip(
        runtime,
        image,
        initial,
        primary_provider="ocrspace",
    )

    assert result.cards == ("S07330-UFZ6-DWUD-4FSRL",)
    assert result.uncertain_count == 2
    assert ManualReviewNotifier().needs_review(result) is not None


def test_repeated_card_with_same_slot_noise_is_confirmed_without_manual_review(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07336-CM57-HC46-F79KY"
    conflicting = "S07336-CMS7-HC46-F79KY"
    initial = Result(
        cards=(confirmed,),
        raw_text=(
            f"[REMOTE]\n{confirmed}\n{confirmed}\n"
            f"[OCRSPACE]\n{confirmed}\n{confirmed}\n{conflicting}\n{conflicting}"
        ),
        pubg_expected_count=2,
        uncertain_count=2,
        has_unresolved_pubg_fragment=True,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == (confirmed,)
    assert result.pubg_expected_count == 1
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False
    assert runtime.remote_calls == 0
    assert runtime.cloud_calls == 0


def test_confirmed_slot_does_not_clear_uncertainty_for_another_card_slot(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07336-CM57-HC46-F79KY"
    conflicting = "S07336-CMS7-HC46-F79KY"
    other_slot = "S07336-ABCD-EFGH-JKLMN"
    initial = Result(
        cards=(confirmed,),
        raw_text=(
            f"[REMOTE]\n{confirmed}\n{conflicting}\n{other_slot}\n"
            f"[OCRSPACE]\n{confirmed}"
        ),
        pubg_expected_count=2,
        uncertain_count=2,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(
        runtime,
        image,
        initial,
        primary_provider="ocrspace",
    )

    assert result.cards == (confirmed,)
    assert result.pubg_expected_count == 2
    assert result.uncertain_count == 2


def test_complete_non_conflicting_thin_strip_uses_no_extra_ocr(tmp_path):
    image = make_thin_image(tmp_path)
    initial = Result(
        cards=("S07330-FSQH-FJVD-W3N8D",),
        raw_text="S07330-FSQH-FJVD-W3N8D",
    )
    runtime = Runtime(None, None)

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result is initial
    assert runtime.remote_calls == 0
    assert runtime.cloud_calls == 0


def test_multi_card_compact_image_is_not_collapsed_by_single_card_review(tmp_path):
    image = make_thin_image(tmp_path)
    confirmed = "S07336-N5TA-EQ7G-VDVE6"
    initial = Result(
        cards=(confirmed,),
        raw_text=(
            "S07336-H8EE-4GYJ-MBI6]\n"
            "S07336-707T-PWV7-F5YH3\n"
            f"{confirmed}"
        ),
        pubg_expected_count=3,
        uncertain_count=2,
        has_unresolved_pubg_fragment=True,
    )
    runtime = Runtime(
        Result(cards=("S07336-H8EE-4GYJ-MBJ6J",)),
        Result(cards=("S07336-7Q7T-PWVZ-F5YH3",)),
    )
    runtime.count_pubg_markers = lambda _text: 3

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result is initial
    assert result.cards == (confirmed,)
    assert result.pubg_expected_count == 3
    assert runtime.remote_calls == 0
    assert runtime.cloud_calls == 0

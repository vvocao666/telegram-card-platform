from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from services.ocr.thin_strip_review import review_conflicting_thin_strip


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


def test_conflicting_thin_strip_uses_independent_matching_review_results(tmp_path):
    image = make_thin_image(tmp_path)
    initial = Result(
        cards=("S07330-FSQH-FWJD-W3N8D",),
        raw_text="S07330-FSQH-FWJD-W3N8D\nS07330-FSQH-FVJD-W3N8D",
        uncertain_count=1,
    )
    corrected = Result(cards=("S07330-FSQH-FJVD-W3N8D",), raw_text="S07330-FSQH-FJVD-W3N8D")
    runtime = Runtime(corrected, corrected)

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == ("S07330-FSQH-FJVD-W3N8D",)
    assert result.uncertain_count == 0
    assert "[THIN_STRIP_REVIEW_REMOTE]" in result.raw_text
    assert "[THIN_STRIP_REVIEW_OCRSPACE]" in result.raw_text
    assert runtime.remote_calls == 1
    assert runtime.cloud_calls == 1


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

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == (confirmed,)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False
    assert runtime.remote_calls == 1
    assert runtime.cloud_calls == 1


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
        uncertain_count=2,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == (confirmed,)
    assert result.uncertain_count == 0
    assert result.has_unresolved_pubg_fragment is False


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
        uncertain_count=2,
    )
    runtime = Runtime(None, Result(cards=(confirmed,), raw_text=confirmed))

    result = review_conflicting_thin_strip(runtime, image, initial)

    assert result.cards == (confirmed,)
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

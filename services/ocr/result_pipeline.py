from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Callable, Pattern


BLUE_LINK = "https://t.me/"


@dataclass(frozen=True)
class ResultPipelineHooks:
    occurrence_type: type
    valid_card: Callable[[str], bool]
    canonical_card: Callable[[str], str]
    psn_key: Callable[[str], str | None]
    psn_is_pubg_substring: Callable[[str, list[str]], bool]
    filter_psn_pubg_substrings: Callable[[list[str], list[str]], list[str]]
    exact_unique_psn: Callable[[list[str]], list[str]]
    exact_unique_text: Callable[[list[str]], list[str]]
    limit_psn_ordered: Callable[[list[str], int | None], list[str]]
    format_duplicate_lines: Callable[[list[tuple[int, list[int]]]], list[str]]
    format_card_codes: Callable[[list[str]], str]
    result_location: Callable[[int, Any], str]
    fuzzy_suffix: str
    success_prefix: str
    count_suffix: str
    uncertain_prefix: str
    uncertain_suffix: str
    manual_review_summary: str
    pubg_label: str
    psn_label: str


def _linked_count(value: int) -> str:
    """将统计数字显示为 Telegram 蓝色链接，保持账单数字的交互样式一致。"""
    return f'<a href="{BLUE_LINK}"><b>【 {value} 】</b></a>'


def count_unique_pubg_markers(
    text: str,
    *,
    normalize_text: Callable[[str], str],
    prefix_pattern: Pattern[str],
) -> int | None:
    anchors: list[tuple[str, ...]] = []
    normalized = normalize_text(text)
    body_pattern = re.compile(
        r"^\s*-\s*([A-Z0-9]{1,5})"
        r"(?:\s*-\s*([A-Z0-9]{1,5}))?"
        r"(?:\s*-\s*([A-Z0-9]{1,5}))?"
    )
    for line in normalized.splitlines():
        for match in prefix_pattern.finditer(line):
            anchor = [match.group(0)]
            body_match = body_pattern.match(line[match.end() :])
            if body_match:
                for value in body_match.groups():
                    if value is None:
                        break
                    anchor.append(value)
            anchors.append(tuple(anchor))

    unique: list[tuple[str, ...]] = []
    for anchor in sorted(anchors, key=len, reverse=True):
        if any(_same_pubg_marker_slot(anchor, existing) for existing in unique):
            continue
        unique.append(anchor)
    return len(unique) or None


def _same_pubg_marker_slot(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Collapse OCR variants of one card without hiding distinct card slots.

    Original and enhanced OCR passes can disagree only on a PUBG tail while
    retaining the prefix and both four-character body groups.  Those are two
    readings of the same visible card, not evidence of a second card.  Partial
    fragments keep the earlier prefix comparison so a genuinely unresolved
    card still triggers the fallback path.
    """
    if len(left) >= 3 and len(right) >= 3:
        if left[:3] == right[:3]:
            return True
        if _is_one_character_missing_duplicate(left, right):
            return True
    # A bare/short prefix can be a separate wrapped card whose remaining
    # groups are on following lines.  Collapsing it into another S07 marker
    # would hide a real missing card, so only sufficiently anchored readings
    # are eligible for same-slot deduplication.
    return False


def _is_one_character_missing_duplicate(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> bool:
    """Collapse one malformed duplicate line without merging two legal cards.

    OCR.space can read a duplicated on-screen card once in full and once with
    one missing character in either four-character body group.  The malformed
    reading is evidence for the same visible slot, not a second card.  Tail
    differences are deliberately excluded because four/five-character tails
    are independently accepted by other compatibility paths.
    """
    if len(left) != 4 or len(right) != 4 or left[0] != right[0]:
        return False

    expected_lengths = (4, 4, 5)
    left_groups = left[1:]
    right_groups = right[1:]
    left_valid = tuple(map(len, left_groups)) == expected_lengths
    right_valid = tuple(map(len, right_groups)) == expected_lengths
    if left_valid == right_valid:
        return False

    complete, malformed = (
        (left_groups, right_groups) if left_valid else (right_groups, left_groups)
    )
    differences = [
        index
        for index, pair in enumerate(zip(complete, malformed))
        if pair[0] != pair[1]
    ]
    if len(differences) != 1 or differences[0] not in (0, 1):
        return False

    index = differences[0]
    full_group = complete[index]
    short_group = malformed[index]
    return len(short_group) == 3 and any(
        full_group[:offset] + full_group[offset + 1 :] == short_group
        for offset in range(len(full_group))
    )


def ordered_pubg_occurrences(results: list[Any], hooks: ResultPipelineHooks) -> list[Any]:
    occurrences: list[Any] = []
    for image_index, result in enumerate(results, start=1):
        sequence_index = result.sequence_index or image_index
        if result.card_locations:
            for card, y, x in result.card_locations:
                key = hooks.canonical_card(card)
                if key and hooks.valid_card(card):
                    occurrences.append(
                        hooks.occurrence_type(
                            card=card,
                            image_index=sequence_index,
                            y=int(y),
                            x=int(x),
                            duplicate_key=key,
                        )
                    )
            continue
        for y, card in enumerate(result.cards):
            key = hooks.canonical_card(card)
            if key and hooks.valid_card(card):
                occurrences.append(
                    hooks.occurrence_type(
                        card=card,
                        image_index=sequence_index,
                        y=y,
                        x=0,
                        duplicate_key=key,
                    )
                )
    return sorted(occurrences, key=lambda item: (item.image_index, item.y, item.x))


def ordered_psn_occurrences(results: list[Any], hooks: ResultPipelineHooks) -> list[Any]:
    occurrences: list[Any] = []
    all_pubg_cards = [card for result in results for card in result.cards if hooks.valid_card(card)]
    for image_index, result in enumerate(results, start=1):
        sequence_index = result.sequence_index or image_index
        if result.psn_locations:
            for line, y, x in result.psn_locations:
                key = hooks.psn_key(line)
                if not key or hooks.psn_is_pubg_substring(key, all_pubg_cards):
                    continue
                display = f"{key}{hooks.fuzzy_suffix}" if line.endswith(hooks.fuzzy_suffix) else key
                occurrences.append(
                    hooks.occurrence_type(
                        card=key,
                        image_index=sequence_index,
                        y=int(y),
                        x=int(x),
                        duplicate_key=key,
                        display=display,
                    )
                )
            continue
        if result.psn_ordered:
            ordered_psn = list(result.psn_ordered)
        else:
            ordered_psn = hooks.exact_unique_psn(list(result.psn_cards)) + hooks.exact_unique_text(
                list(result.psn_uncertain)
            )
        ordered_psn = hooks.filter_psn_pubg_substrings(ordered_psn, all_pubg_cards)
        ordered_psn = hooks.limit_psn_ordered(ordered_psn, result.psn_expected_count)
        for y, line in enumerate(ordered_psn):
            key = hooks.psn_key(line)
            if not key or hooks.psn_is_pubg_substring(key, all_pubg_cards):
                continue
            display = f"{key}{hooks.fuzzy_suffix}" if line.endswith(hooks.fuzzy_suffix) else key
            occurrences.append(
                hooks.occurrence_type(
                    card=key,
                    image_index=sequence_index,
                    y=y,
                    x=0,
                    duplicate_key=key,
                    display=display,
                )
            )
    return sorted(occurrences, key=lambda item: (item.image_index, item.y, item.x))


def format_reply(results: list[Any], hooks: ResultPipelineHooks) -> str:
    pubg_occurrences = ordered_pubg_occurrences(results, hooks)
    psn_occurrences = ordered_psn_occurrences(results, hooks)
    conflict_lines: list[str] = []
    expected_pubg_total = 0
    expected_psn_total = 0
    pubg_image_count = 0
    psn_image_count = 0
    uncertain_count = 0
    for index, result in enumerate(results, start=1):
        image_pubg = [item for item in pubg_occurrences if item.image_index == index]
        image_psn = [item for item in psn_occurrences if item.image_index == index]
        if image_pubg:
            pubg_image_count += 1
        if image_psn:
            psn_image_count += 1
        if result.pubg_expected_count:
            expected_pubg_total += result.pubg_expected_count
        if result.psn_expected_count:
            expected_psn_total += result.psn_expected_count
        if result.uncertain_count:
            conflict_lines.append(
                f"{hooks.result_location(index, result)}："
                f"{hooks.uncertain_prefix}{result.uncertain_count}{hooks.uncertain_suffix}"
            )
        uncertain_count += result.uncertain_count

    pubg_cards: list[str] = []
    seen_pubg: dict[str, int] = {}
    pubg_duplicate_groups: dict[int, list[int]] = {}
    for occurrence in pubg_occurrences:
        if not hooks.valid_card(occurrence.card):
            continue
        if occurrence.duplicate_key not in seen_pubg:
            seen_pubg[occurrence.duplicate_key] = occurrence.image_index
            pubg_cards.append(occurrence.card)
            continue
        pubg_duplicate_groups.setdefault(seen_pubg[occurrence.duplicate_key], []).append(occurrence.image_index)

    psn_lines: list[str] = []
    seen_psn: dict[str, int] = {}
    psn_duplicate_groups: dict[int, list[int]] = {}
    for occurrence in psn_occurrences:
        if occurrence.duplicate_key not in seen_psn:
            seen_psn[occurrence.duplicate_key] = occurrence.image_index
            psn_lines.append(occurrence.display)
            continue
        psn_duplicate_groups.setdefault(seen_psn[occurrence.duplicate_key], []).append(occurrence.image_index)
    psn_cards = hooks.exact_unique_psn([card for card in psn_lines if not card.endswith(hooks.fuzzy_suffix)])
    psn_uncertain = hooks.exact_unique_text([card for card in psn_lines if card.endswith(hooks.fuzzy_suffix)])
    pubg_duplicate_lines = hooks.format_duplicate_lines(list(pubg_duplicate_groups.items()))
    psn_duplicate_lines = hooks.format_duplicate_lines(list(psn_duplicate_groups.items()))

    sections: list[str] = []
    if pubg_cards:
        pubg_summary = (
            f"<b>本次识别{hooks.pubg_label}：</b>{_linked_count(len(pubg_cards))}<b>{hooks.count_suffix}</b>\n"
            f"<b>本次识别PUBG图片：</b>{_linked_count(pubg_image_count)}<b>张</b>"
        )
        if expected_pubg_total and len(pubg_cards) < expected_pubg_total:
            pubg_summary += (
                f"\n{hooks.manual_review_summary}{hooks.pubg_label}"
                f"{expected_pubg_total - len(pubg_cards)}{hooks.count_suffix}"
            )
        if pubg_duplicate_lines:
            pubg_summary += "\n" + "\n".join(pubg_duplicate_lines)
        sections.append(
            f"<b>【{hooks.pubg_label}】</b>\n\n{hooks.format_card_codes(pubg_cards)}\n\n{pubg_summary}"
        )

    if psn_lines:
        psn_summary = (
            f"<b>本次识别{hooks.psn_label}：</b>{_linked_count(len(psn_cards))}<b>{hooks.count_suffix}</b>\n"
            f"<b>本次识别PSN图片：</b>{_linked_count(psn_image_count)}<b>张</b>"
        )
        if psn_uncertain:
            psn_summary += (
                f"\n{hooks.manual_review_summary}{hooks.psn_label}{len(psn_uncertain)}{hooks.count_suffix}"
            )
        if expected_psn_total and len(psn_lines) < expected_psn_total:
            psn_summary += (
                f"\n{hooks.manual_review_summary}{hooks.psn_label}"
                f"{expected_psn_total - len(psn_lines)}{hooks.count_suffix}"
            )
        if psn_duplicate_lines:
            psn_summary += "\n" + "\n".join(psn_duplicate_lines)
        sections.append(f"<b>【{hooks.psn_label}】</b>\n\n{hooks.format_card_codes(psn_lines)}\n\n{psn_summary}")

    if uncertain_count:
        if conflict_lines:
            sections.append(
                f"{hooks.uncertain_prefix}\n"
                f"<blockquote>{html.escape(chr(10).join(conflict_lines))}</blockquote>\n"
                f"{hooks.uncertain_prefix}{uncertain_count}{hooks.uncertain_suffix}"
            )
        else:
            sections.append(f"{hooks.uncertain_prefix}{uncertain_count}{hooks.uncertain_suffix}")
    if not sections:
        sections.append("未识别到卡密")
    return "\n\n".join(sections)


def result_card_lines(results: list[Any], hooks: ResultPipelineHooks) -> tuple[list[str], list[str]]:
    pubg_cards: list[str] = []
    psn_lines: list[str] = []
    seen_pubg: set[str] = set()
    for occurrence in ordered_pubg_occurrences(results, hooks):
        if occurrence.duplicate_key in seen_pubg:
            continue
        seen_pubg.add(occurrence.duplicate_key)
        pubg_cards.append(occurrence.card)
    seen_psn: set[str] = set()
    for occurrence in ordered_psn_occurrences(results, hooks):
        if occurrence.duplicate_key in seen_psn:
            continue
        seen_psn.add(occurrence.duplicate_key)
        psn_lines.append(occurrence.display)
    return pubg_cards, psn_lines

from __future__ import annotations

from collections import Counter
import re


PUBG_CARD_PATTERN = re.compile(
    r"(?<![A-Z0-9])([A-Z][0-9]{5})-([A-Z0-9]{4})-([A-Z0-9]{4})-([A-Z0-9]{5})(?![A-Z0-9])"
)
VALID_PREFIX_PATTERN = re.compile(r"S07[0-9]{3}")


def recover_single_prefix_digit_error(
    line_texts: list[str] | tuple[str, ...],
    existing_cards: list[str] | tuple[str, ...],
) -> list[tuple[int, str]]:
    """仅按同图多数前缀恢复一位数字误读，正文字符保持原样。"""
    valid_prefixes = [card.split("-", 1)[0] for card in existing_cards if "-" in card]
    if not valid_prefixes:
        return []
    prefix_counts = Counter(prefix for prefix in valid_prefixes if VALID_PREFIX_PATTERN.fullmatch(prefix))
    if not prefix_counts:
        return []
    dominant_prefix, dominant_count = prefix_counts.most_common(1)[0]
    if dominant_count < 2:
        return []

    recovered: list[tuple[int, str]] = []
    prefix_ordinal = 0
    for text in line_texts:
        line = str(text).upper()
        for match in PUBG_CARD_PATTERN.finditer(line):
            observed_prefix = match.group(1)
            candidate = "-".join((dominant_prefix, *match.groups()[1:]))
            if (
                not VALID_PREFIX_PATTERN.fullmatch(observed_prefix)
                and observed_prefix[0:2] == "S0"
                and sum(left != right for left, right in zip(observed_prefix, dominant_prefix)) == 1
                and candidate not in existing_cards
                and all(candidate != item[1] for item in recovered)
            ):
                recovered.append((prefix_ordinal, candidate))
            prefix_ordinal += 1
    return recovered

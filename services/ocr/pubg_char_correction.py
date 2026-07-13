from __future__ import annotations

from dataclasses import dataclass
import re

from services.ocr.font_repository import FontRepository


PUBG_PREFIXES = (
    "S07304",
    "S07234",
    "S07303",
    "S07240",
    "S07292",
    "S07298",
    "S07213",
    "S07291",
    "S07205",
    "S07239",
    "S07228",
    "S07286",
)
PUBG_RE = re.compile(r"^S07[A-Z0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}$")
DEFAULT_FONT_HASH = "unknown_font"


@dataclass(frozen=True)
class PubgCorrection:
    original: str
    corrected: str
    reason: str

    def as_dict(self) -> dict[str, str]:
        return {"from": self.original, "to": self.corrected, "reason": self.reason}


@dataclass(frozen=True)
class PubgCorrectionResult:
    cards: tuple[str, ...]
    corrections: tuple[PubgCorrection, ...]
    needs_review: bool = False


# 只允许字体、位置和字符对同时匹配的保守字符级规则。
SAFE_CONFUSIONS = {
    ("9", "S"),
    ("S", "9"),
    ("9", "6"),
    ("6", "9"),
    ("0", "O"),
    ("O", "0"),
    ("1", "I"),
    ("I", "1"),
    ("5", "S"),
    ("S", "5"),
    ("8", "B"),
    ("B", "8"),
    ("3", "9"),
    ("9", "3"),
    ("J", "U"),
}


def apply_pubg_char_corrections(
    cards: list[str] | tuple[str, ...],
    font_repository: FontRepository | None = None,
    font_hash: str = DEFAULT_FONT_HASH,
) -> PubgCorrectionResult:
    corrected_cards: list[str] = []
    corrections: list[PubgCorrection] = []
    for card in cards:
        corrected, reason = correct_pubg_card(card, font_repository=font_repository, font_hash=font_hash)
        if corrected != card:
            corrections.append(PubgCorrection(original=card, corrected=corrected, reason=reason))
        corrected_cards.append(corrected)
    return PubgCorrectionResult(cards=tuple(_stable_unique(corrected_cards)), corrections=tuple(corrections))


def correct_pubg_card(
    card: str,
    font_repository: FontRepository | None = None,
    font_hash: str = DEFAULT_FONT_HASH,
) -> tuple[str, str]:
    normalized = normalize_pubg_prefix(card)
    if not PUBG_RE.fullmatch(normalized):
        return card, "invalid_pubg_format"

    learned = apply_learned_rules(normalized, font_repository=font_repository, font_hash=font_hash)
    if learned != normalized and PUBG_RE.fullmatch(learned):
        return learned, "learned_font_rule"

    return normalized, "unchanged"


def normalize_pubg_prefix(card: str) -> str:
    value = card.strip().upper()
    if len(value) >= 6 and value[1:6] == "07304" and value[0] in {"9", "5", "$"}:
        value = f"S{value[1:]}"
    if len(value) >= 6 and value[:2] in {"SO", "S0"} and value[2:6] == "7304":
        value = f"S07{value[3:]}"
    return value


def apply_learned_rules(
    card: str,
    font_repository: FontRepository | None,
    font_hash: str,
) -> str:
    if not font_repository or not font_hash or font_hash == DEFAULT_FONT_HASH:
        return card
    profile = font_repository.get_profile(font_hash)
    if not profile or not profile.enabled or profile.card_type not in {None, "PUBG"}:
        return card

    chars = list(card)
    changed = False
    for key, count in profile.position_rules.items():
        if count < 3:
            continue
        parsed = parse_position_rule(key)
        if not parsed:
            continue
        position, wrong, correct = parsed
        if position < 0 or position >= len(chars):
            continue
        if (wrong, correct) not in SAFE_CONFUSIONS:
            continue
        if chars[position] != wrong:
            continue
        chars[position] = correct
        changed = True
    candidate = "".join(chars)
    return candidate if changed and PUBG_RE.fullmatch(candidate) else card


def parse_position_rule(key: str) -> tuple[int, str, str] | None:
    try:
        position_text, pair = key.split(":", 1)
        wrong, correct = pair.split(">", 1)
        return int(position_text), wrong, correct
    except (ValueError, TypeError):
        return None


def _stable_unique(cards: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if card in seen:
            continue
        seen.add(card)
        result.append(card)
    return result

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import re


@dataclass(frozen=True)
class Candidate:
    raw_text: str
    corrected_text: str
    card_type: str | None
    changes: tuple[str, ...] = tuple()
    confidence: float = 0.0


SEPARATED_CARD_RE = re.compile(r"[A-Z0-9]{4,6}(?:-[A-Z0-9]{4,5}){2,3}")
PUBG_CARD_WINDOW_RE = re.compile(r"[A-Z0-9]{6}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}")
PSN_CARD_WINDOW_RE = re.compile(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}")
PUBG_PREFIX_REPAIRS = {"507", "SO7", "S0T"}
DASH_TRANSLATION = str.maketrans({
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "_": "-",
})


def normalize_ocr_text(raw_text: str) -> str:
    normalized = raw_text.upper().translate(DASH_TRANSLATION)
    return re.sub(r"\s+", "", normalized)


def extract_raw_candidates(raw_text: str, card_type: str | None = None) -> list[Candidate]:
    normalized = normalize_ocr_text(raw_text)
    values = []
    seen: set[str] = set()
    patterns = [SEPARATED_CARD_RE]
    if card_type == "PUBG":
        patterns.insert(0, PUBG_CARD_WINDOW_RE)
    elif card_type == "PSN":
        patterns.insert(0, PSN_CARD_WINDOW_RE)
    for pattern in patterns:
        for match in pattern.finditer(normalized):
            value = match.group(0)
            if value not in seen:
                seen.add(value)
                values.append(Candidate(raw_text=raw_text, corrected_text=value, card_type=card_type))
    return values


def repair_pubg_prefix(candidate: str) -> str | None:
    parts = candidate.split("-")
    if len(parts) != 4 or len(parts[0]) != 6:
        return None
    prefix = parts[0][:3]
    if prefix == "S07":
        return None
    if prefix not in PUBG_PREFIX_REPAIRS:
        return None
    parts[0] = "S07" + parts[0][3:]
    return "-".join(parts)


def generate_replacement_candidates(
    raw_text: str,
    replacements: dict[str, tuple[str, ...]],
    card_type: str | None = None,
    max_changes: int = 2,
) -> list[Candidate]:
    base_candidates = extract_raw_candidates(raw_text, card_type=card_type)
    generated: list[Candidate] = []
    seen: set[str] = set()
    for candidate in base_candidates:
        if card_type == "PUBG":
            repaired = repair_pubg_prefix(candidate.corrected_text)
            if repaired and repaired not in seen:
                seen.add(repaired)
                generated.append(
                    Candidate(
                        raw_text=candidate.raw_text,
                        corrected_text=repaired,
                        card_type=card_type,
                        changes=(f"{candidate.corrected_text[:3]}->S07@0",),
                    )
                )
        positions = [(index, char, replacements[char]) for index, char in enumerate(candidate.corrected_text) if char in replacements]
        limited_positions = positions[:max_changes]
        replacement_sets = [[char, *values] for _, char, values in limited_positions]
        for combo in product(*replacement_sets) if replacement_sets else [()]:
            chars = list(candidate.corrected_text)
            changes: list[str] = []
            confidence = 0.0
            for (index, original, _), replacement in zip(limited_positions, combo):
                if replacement != original:
                    chars[index] = replacement
                    changes.append(f"{original}->{replacement}@{index}")
                    if original == "2" and replacement == "Z" and card_type == "PUBG" and index == 19:
                        confidence += 0.95
            value = "".join(chars)
            if value not in seen:
                seen.add(value)
                generated.append(
                    Candidate(
                        raw_text=candidate.raw_text,
                        corrected_text=value,
                        card_type=card_type,
                        changes=tuple(changes),
                        confidence=confidence,
                    )
                )
    return generated

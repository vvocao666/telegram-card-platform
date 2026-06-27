from __future__ import annotations

import re


PUBG_CARD_RE = re.compile(r"^S07[A-Z0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}$")
PSN_CARD_RE = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")


def normalize_candidate(candidate: str) -> str:
    return candidate.strip().upper()


def valid_pubg_card(candidate: str) -> bool:
    normalized = normalize_candidate(candidate)
    return bool(PUBG_CARD_RE.fullmatch(normalized))


def valid_psn_candidate(candidate: str) -> bool:
    normalized = normalize_candidate(candidate)
    return bool(PSN_CARD_RE.fullmatch(normalized))


def detect_card_type(candidate: str) -> str | None:
    if valid_pubg_card(candidate):
        return "PUBG"
    if valid_psn_candidate(candidate):
        return "PSN"
    return None


def validate_candidate(candidate: str, card_type: str | None = None) -> bool:
    if card_type == "PUBG":
        return valid_pubg_card(candidate)
    if card_type == "PSN":
        return valid_psn_candidate(candidate)
    return detect_card_type(candidate) is not None


def validator_reject_reason(candidate: str, card_type: str | None = None) -> str | None:
    normalized = normalize_candidate(candidate)
    if validate_candidate(normalized, card_type=card_type):
        return None
    if card_type == "PUBG":
        parts = normalized.split("-")
        if not normalized.startswith("S07"):
            return "pubg_prefix_not_s07"
        if len(parts) != 4:
            return "pubg_group_count_invalid"
        lengths = [len(part) for part in parts]
        if lengths != [6, 4, 4, 5]:
            return "pubg_group_length_invalid"
        if not all(part.isalnum() for part in parts):
            return "pubg_charset_invalid"
        return "pubg_format_invalid"
    if card_type == "PSN":
        parts = normalized.split("-")
        if len(parts) != 3:
            return "psn_group_count_invalid"
        if [len(part) for part in parts] != [4, 4, 4]:
            return "psn_group_length_invalid"
        if not all(part.isalnum() for part in parts):
            return "psn_charset_invalid"
        return "psn_format_invalid"
    return "unknown_card_type"


def filter_valid_candidates(candidates: list[str], card_type: str | None = None) -> list[str]:
    valid: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        if validate_candidate(candidate, card_type=card_type):
            seen.add(candidate)
            valid.append(candidate)
    return valid

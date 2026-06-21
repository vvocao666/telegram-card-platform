from __future__ import annotations

from dataclasses import dataclass

from services.ocr.candidate_generator import Candidate
from services.ocr.validator import validate_candidate


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    score: float
    reasons: tuple[str, ...]


def score_candidate(candidate: Candidate, learned_count: int = 0) -> ScoredCandidate:
    score = 0.0
    reasons: list[str] = []
    if validate_candidate(candidate.corrected_text, candidate.card_type):
        score += 100.0
        reasons.append("valid_format")
    if not candidate.changes:
        score += 10.0
        reasons.append("unchanged")
    else:
        score -= len(candidate.changes) * 5.0
        reasons.append("changed")
    if candidate.confidence:
        score += candidate.confidence * 30.0
        reasons.append("confidence")
    if learned_count >= 3:
        score += min(learned_count, 20)
        reasons.append("learned_priority")
    return ScoredCandidate(candidate=candidate, score=score, reasons=tuple(reasons))


def choose_best_candidate(candidates: list[Candidate], learned_counts: dict[str, int] | None = None) -> ScoredCandidate | None:
    learned_counts = learned_counts or {}
    scored = [
        score_candidate(candidate, learned_counts.get(candidate.corrected_text, 0))
        for candidate in candidates
        if validate_candidate(candidate.corrected_text, candidate.card_type)
    ]
    if not scored:
        return None
    return max(scored, key=lambda item: (item.score, -len(item.candidate.changes), item.candidate.corrected_text))

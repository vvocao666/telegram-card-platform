from __future__ import annotations

from dataclasses import dataclass
import logging

from services.ocr.candidate_generator import Candidate, extract_raw_candidates, generate_replacement_candidates
from services.ocr.correction_rules import replacement_map
from services.ocr.scoring_engine import ScoredCandidate, choose_best_candidate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorrectionResult:
    raw_text: str
    candidates: tuple[Candidate, ...]
    best_candidate: ScoredCandidate | None


def apply_corrections(raw_text: str, card_type: str | None = None) -> CorrectionResult:
    raw_candidates = extract_raw_candidates(raw_text, card_type=card_type)
    replacement_candidates = generate_replacement_candidates(
        raw_text,
        replacement_map(card_type),
        card_type=card_type,
    )
    candidates = tuple({candidate.corrected_text: candidate for candidate in [*raw_candidates, *replacement_candidates]}.values())
    best = choose_best_candidate(list(candidates))
    if best and best.candidate.corrected_text != raw_text:
        logger.info("OCR correction candidate selected: %s", best.candidate.corrected_text)
    return CorrectionResult(raw_text=raw_text, candidates=candidates, best_candidate=best)

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from services.ocr.candidate_generator import Candidate, extract_raw_candidates, generate_replacement_candidates
from services.ocr.correction_rules import replacement_map
from services.ocr.scoring_engine import ScoredCandidate, choose_best_candidate, score_candidate
from services.ocr.validator import validator_reject_reason


DEFAULT_AUDIT_PATH = Path("outputs/ocr_candidates.json")


@dataclass(frozen=True)
class CandidateAuditRecord:
    ocr_raw: str
    candidate_list: list[dict[str, object]]
    validator_reject_reason: dict[str, str]
    best_score: float | None
    best_candidate: str | None
    created_at: str


def build_candidate_audit(raw_text: str, card_type: str | None = None) -> CandidateAuditRecord:
    raw_candidates = extract_raw_candidates(raw_text, card_type=card_type)
    replacement_candidates = generate_replacement_candidates(
        raw_text,
        replacement_map(card_type),
        card_type=card_type,
    )
    candidates = _dedupe_candidates([*raw_candidates, *replacement_candidates])
    scored = [score_candidate(candidate) for candidate in candidates]
    best = choose_best_candidate(candidates)
    return CandidateAuditRecord(
        ocr_raw=raw_text,
        candidate_list=[_candidate_payload(candidate, scored) for candidate in candidates],
        validator_reject_reason=_reject_reasons(candidates, card_type=card_type),
        best_score=best.score if best else None,
        best_candidate=best.candidate.corrected_text if best else None,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def append_candidate_audit(
    raw_text: str,
    card_type: str | None = None,
    output_path: Path | str = DEFAULT_AUDIT_PATH,
) -> CandidateAuditRecord:
    record = build_candidate_audit(raw_text, card_type=card_type)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_records(path)
    existing.append(asdict(record))
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    values: dict[str, Candidate] = {}
    for candidate in candidates:
        values.setdefault(candidate.corrected_text, candidate)
    return list(values.values())


def _candidate_payload(candidate: Candidate, scored: list[ScoredCandidate]) -> dict[str, object]:
    score = next((item for item in scored if item.candidate.corrected_text == candidate.corrected_text), None)
    return {
        "value": candidate.corrected_text,
        "card_type": candidate.card_type,
        "changes": list(candidate.changes),
        "score": score.score if score else None,
        "score_reasons": list(score.reasons) if score else [],
    }


def _reject_reasons(candidates: list[Candidate], card_type: str | None = None) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for candidate in candidates:
        reason = validator_reject_reason(candidate.corrected_text, card_type=card_type or candidate.card_type)
        if reason:
            reasons[candidate.corrected_text] = reason
    return reasons


def _read_existing_records(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    return []

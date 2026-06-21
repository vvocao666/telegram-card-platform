from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib


@dataclass(frozen=True)
class FontProfile:
    font_hash: str
    card_type: str | None
    source_chat_id: int | None
    source_user_id: int | None
    sample_count: int
    error_pairs: dict[str, int]
    position_rules: dict[str, int]
    confidence: float
    last_seen: str
    enabled: bool = True

    @property
    def confusion_pairs(self) -> dict[str, int]:
        return self.error_pairs


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_text_font_hash(sample_text: str, card_type: str | None = None) -> str:
    normalized = "".join(sample_text.upper().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    prefix = (card_type or "ocr").lower()
    return f"{prefix}_font_{digest}"


def build_font_hash(sample_text: str) -> str:
    return build_text_font_hash(sample_text)


def build_font_profile(
    sample_text: str,
    card_type: str | None = None,
    confusion_pairs: dict[str, int] | None = None,
    error_pairs: dict[str, int] | None = None,
    position_rules: dict[str, int] | None = None,
    source_chat_id: int | None = None,
    source_user_id: int | None = None,
    sample_count: int = 1,
    confidence: float = 0.5,
    enabled: bool = True,
    font_hash: str | None = None,
) -> FontProfile:
    return FontProfile(
        font_hash=font_hash or build_text_font_hash(sample_text, card_type=card_type),
        card_type=card_type,
        source_chat_id=source_chat_id,
        source_user_id=source_user_id,
        sample_count=sample_count,
        error_pairs=error_pairs or confusion_pairs or {},
        position_rules=position_rules or {},
        confidence=confidence,
        last_seen=utc_now(),
        enabled=enabled,
    )


def serialize_font_profile(profile: FontProfile) -> dict[str, object]:
    return asdict(profile)


def deserialize_font_profile(data: dict[str, object]) -> FontProfile:
    return FontProfile(
        font_hash=str(data.get("font_hash", "")),
        card_type=data.get("card_type") if isinstance(data.get("card_type"), str) else None,
        source_chat_id=_optional_int(data.get("source_chat_id")),
        source_user_id=_optional_int(data.get("source_user_id")),
        sample_count=int(data.get("sample_count", 0)),
        error_pairs=_int_dict(data.get("error_pairs") or data.get("confusion_pairs") or {}),
        position_rules=_int_dict(data.get("position_rules") or {}),
        confidence=float(data.get("confidence", 0.0)),
        last_seen=str(data.get("last_seen", "")),
        enabled=bool(data.get("enabled", True)),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): int(item) for key, item in value.items()}

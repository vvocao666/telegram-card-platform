from __future__ import annotations

import json
from pathlib import Path

from services.ocr.font_profile import (
    FontProfile,
    build_font_profile,
    deserialize_font_profile,
    serialize_font_profile,
    utc_now,
)


DEFAULT_FONT_PROFILE_PATH = Path("outputs/font_profiles.json")


class FontRepository:
    def __init__(self, path: Path | str = DEFAULT_FONT_PROFILE_PATH) -> None:
        self.path = Path(path)

    def save_profile(self, profile: FontProfile) -> FontProfile:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        profiles = self._read_profiles()
        current = profiles.get(profile.font_hash)
        if current:
            merged = _merge_profile(current, profile)
            profiles[profile.font_hash] = serialize_font_profile(merged)
        else:
            profiles[profile.font_hash] = serialize_font_profile(profile)
        self.path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get_profile(profile.font_hash) or profile

    def learn_sample(
        self,
        sample_text: str,
        card_type: str | None = None,
        confusion_pairs: dict[str, int] | None = None,
        error_pairs: dict[str, int] | None = None,
        position_rules: dict[str, int] | None = None,
        source_chat_id: int | None = None,
        source_user_id: int | None = None,
        font_hash: str | None = None,
    ) -> FontProfile:
        profile = build_font_profile(
            sample_text,
            card_type=card_type,
            confusion_pairs=confusion_pairs,
            error_pairs=error_pairs,
            position_rules=position_rules,
            source_chat_id=source_chat_id,
            source_user_id=source_user_id,
            font_hash=font_hash,
        )
        return self.save_profile(profile)

    def get_profile(self, font_hash: str) -> FontProfile | None:
        data = self._read_profiles().get(font_hash)
        return deserialize_font_profile(data) if data else None

    def list_profiles(self, enabled_only: bool = False) -> list[FontProfile]:
        profiles = [deserialize_font_profile(data) for data in self._read_profiles().values()]
        if enabled_only:
            profiles = [profile for profile in profiles if profile.enabled]
        return sorted(profiles, key=lambda profile: profile.last_seen, reverse=True)

    def set_enabled(self, font_hash: str, enabled: bool) -> bool:
        profiles = self._read_profiles()
        if font_hash not in profiles:
            return False
        profile = deserialize_font_profile(profiles[font_hash])
        updated = FontProfile(
            font_hash=profile.font_hash,
            card_type=profile.card_type,
            source_chat_id=profile.source_chat_id,
            source_user_id=profile.source_user_id,
            sample_count=profile.sample_count,
            error_pairs=profile.error_pairs,
            position_rules=profile.position_rules,
            confidence=profile.confidence,
            last_seen=profile.last_seen,
            enabled=enabled,
        )
        profiles[font_hash] = serialize_font_profile(updated)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def touch_profile(self, font_hash: str) -> bool:
        profiles = self._read_profiles()
        if font_hash not in profiles:
            return False
        profile = deserialize_font_profile(profiles[font_hash])
        touched = FontProfile(
            font_hash=profile.font_hash,
            card_type=profile.card_type,
            source_chat_id=profile.source_chat_id,
            source_user_id=profile.source_user_id,
            sample_count=profile.sample_count,
            error_pairs=profile.error_pairs,
            position_rules=profile.position_rules,
            confidence=profile.confidence,
            last_seen=utc_now(),
            enabled=profile.enabled,
        )
        profiles[font_hash] = serialize_font_profile(touched)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
        return True

    def rules_for(self, font_hash: str) -> dict[str, object]:
        profile = self.get_profile(font_hash)
        if not profile:
            return {}
        return {
            "font_hash": profile.font_hash,
            "enabled": profile.enabled,
            "error_pairs": profile.error_pairs,
            "position_rules": profile.position_rules,
            "confidence": profile.confidence,
        }

    def stats(self) -> dict[str, object]:
        profiles = self.list_profiles()
        error_pairs: dict[str, int] = {}
        for profile in profiles:
            for key, value in profile.error_pairs.items():
                error_pairs[key] = error_pairs.get(key, 0) + value
        return {
            "profile_count": len(profiles),
            "enabled_count": len([profile for profile in profiles if profile.enabled]),
            "sample_count": sum(profile.sample_count for profile in profiles),
            "font_hashes": [profile.font_hash for profile in profiles],
            "top_error_pairs": sorted(error_pairs.items(), key=lambda item: item[1], reverse=True)[:10],
        }

    def _read_profiles(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items() if isinstance(value, dict)}
        return {}


def _merge_profile(current: dict[str, object], incoming: FontProfile) -> FontProfile:
    profile = deserialize_font_profile(current)
    merged_count = profile.sample_count + incoming.sample_count
    merged_errors = _merge_counts(profile.error_pairs, incoming.error_pairs)
    merged_positions = _merge_counts(profile.position_rules, incoming.position_rules)
    return FontProfile(
        font_hash=incoming.font_hash,
        card_type=incoming.card_type or profile.card_type,
        source_chat_id=incoming.source_chat_id if incoming.source_chat_id is not None else profile.source_chat_id,
        source_user_id=incoming.source_user_id if incoming.source_user_id is not None else profile.source_user_id,
        sample_count=merged_count,
        error_pairs=merged_errors,
        position_rules=merged_positions,
        confidence=max(profile.confidence, incoming.confidence),
        last_seen=incoming.last_seen,
        enabled=profile.enabled and incoming.enabled,
    )


def _merge_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = merged.get(key, 0) + value
    return merged

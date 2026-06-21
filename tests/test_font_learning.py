from services.ocr.font_profile import build_font_hash, build_font_profile
from services.ocr.font_repository import FontRepository


def test_font_hash_is_stable_for_spacing_changes():
    assert build_font_hash("S07304 GM7D") == build_font_hash("S07304GM7D")


def test_font_repository_merges_profile_counts(tmp_path):
    repository = FontRepository(tmp_path / "ocr_font_profiles.json")
    profile = build_font_profile(
        "S07304-GM7D-JQ93-9NHLV",
        card_type="PUBG",
        confusion_pairs={"2>Z": 1},
    )

    repository.save_profile(profile)
    repository.save_profile(profile)
    stats = repository.stats()

    assert stats["profile_count"] == 1
    assert stats["sample_count"] == 2

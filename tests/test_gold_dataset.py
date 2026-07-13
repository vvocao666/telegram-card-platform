import hashlib
import json

from services.ocr.gold_dataset import collect_gold_dataset_cases, write_gold_dataset


def test_gold_dataset_accepts_only_confirmed_images_and_deduplicates_hash(tmp_path):
    image = tmp_path / "card.png"
    duplicate = tmp_path / "duplicate.png"
    review = tmp_path / "review.png"
    image.write_bytes(b"confirmed-image")
    duplicate.write_bytes(b"confirmed-image")
    review.write_bytes(b"review-image")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    audit = tmp_path / "2026-07-13-audit.json"
    audit.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "confirmed",
                        "image": "card.png",
                        "image_sha256": digest,
                        "status": "confirmed_error",
                        "profile": "thin|clear|pubg",
                        "expected_pubg": ["S07336-AAAA-BBBB-CCCCC"],
                    },
                    {"case_id": "duplicate", "image": "duplicate.png", "status": "confirmed_match"},
                    {"case_id": "review", "image": "review.png", "status": "needs_review"},
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = collect_gold_dataset_cases([audit])

    assert len(cases) == 1
    assert cases[0].image_hash == digest


def test_gold_dataset_manifest_preserves_type_and_order_without_source_metadata(tmp_path):
    image = tmp_path / "psn.jpg"
    image.write_bytes(b"psn-image")
    audit = tmp_path / "2026-07-13-audit.json"
    audit.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "psn-order",
                        "image": "psn.jpg",
                        "status": "confirmed_match",
                        "profile": "multi|clear|psn",
                        "expected_psn": ["AAAA-BBBB-CCCC", "DDDD-EEEE-FFFF"],
                        "chat_id": 123,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = collect_gold_dataset_cases([audit])
    manifest = write_gold_dataset(tmp_path / "gold", cases)
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert payload["cases"][0]["expected_psn"] == ["AAAA-BBBB-CCCC", "DDDD-EEEE-FFFF"]
    assert "chat_id" not in payload["cases"][0]

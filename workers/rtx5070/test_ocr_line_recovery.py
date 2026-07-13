from ocr_line_recovery import recover_suspicious_pubg_lines


def test_recovery_requires_same_image_prefix_majority(monkeypatch):
    result = {
        "texts": [
            {"text": "S07336-ZEBT-JFGP-KR4YE", "score": 0.99, "box": [0, 0, 100, 20]},
            {"text": "S01336-3SRE-ETDS-QEXR)", "score": 0.95, "box": [0, 30, 100, 50]},
            {"text": "S07336-BHSN-T4TA-CH39R", "score": 0.99, "box": [0, 60, 100, 80]},
        ],
        "cards": [
            {"text": "S07336-ZEBT-JFGP-KR4YE", "score": 0.99},
            {"text": "1336-3SRE-ETDS", "score": 0.95},
            {"text": "S07336-BHSN-T4TA-CH39R", "score": 0.99},
        ],
    }
    monkeypatch.setattr("ocr_line_recovery._write_line_crop", lambda *_args: "crop.png")
    monkeypatch.setattr("ocr_line_recovery.os.unlink", lambda *_args: None)

    def fake_ocr(_path):
        return {"texts": [{"text": "S01336-3SRE-ETDS-QEXR7", "score": 0.98}]}, 10

    updated, recoveries = recover_suspicious_pubg_lines("image.png", result, fake_ocr)

    assert updated["cards"][1]["text"] == "S07336-3SRE-ETDS-QEXR7"
    assert [item["text"] for item in updated["cards"]] == [
        "S07336-ZEBT-JFGP-KR4YE",
        "S07336-3SRE-ETDS-QEXR7",
        "S07336-BHSN-T4TA-CH39R",
    ]
    assert recoveries == [
        {
            "from": "S01336-3SRE-ETDS-QEXR)",
            "to": "S07336-3SRE-ETDS-QEXR7",
            "reason": "line_roi_recheck",
        }
    ]


def test_recovery_does_not_guess_without_two_valid_sibling_cards(monkeypatch):
    result = {
        "texts": [
            {"text": "S01336-3SRE-ETDS-QEXR)", "score": 0.95, "box": [0, 0, 100, 20]},
        ],
        "cards": [],
    }
    updated, recoveries = recover_suspicious_pubg_lines("image.png", result, lambda _path: ({}, 0))
    assert updated == result
    assert recoveries == []


def test_prefix_majority_accepts_sibling_with_overlong_tail(monkeypatch):
    result = {
        "texts": [
            {"text": "S07336-ZEBT-JFGP-KR4YEK", "score": 0.95, "box": [0, 0, 100, 20]},
            {"text": "S01336-3SRE-ETDS-QEXR)", "score": 0.95, "box": [0, 30, 100, 50]},
            {"text": "S07336-BHSN-T4TA-CH39R", "score": 0.99, "box": [0, 60, 100, 80]},
        ],
        "cards": [],
    }
    monkeypatch.setattr("ocr_line_recovery._write_line_crop", lambda *_args: "crop.png")
    monkeypatch.setattr("ocr_line_recovery.os.unlink", lambda *_args: None)

    updated, recoveries = recover_suspicious_pubg_lines(
        "image.png",
        result,
        lambda _path: ({"texts": [{"text": "S01336-3SRE-ETDS-QEXR7", "score": 0.98}]}, 10),
    )

    assert "S07336-3SRE-ETDS-QEXR7" in [item["text"] for item in updated["cards"]]
    assert recoveries[0]["reason"] == "line_roi_recheck"


def test_recovery_uses_enhanced_roi_when_original_roi_is_still_wrong(monkeypatch):
    result = {
        "texts": [
            {"text": "S07336-ZEBT-JFGP-KR4YEK", "score": 0.95, "box": [0, 0, 100, 20]},
            {"text": "S01336-3SRE-ETDS-QEXR)", "score": 0.95, "box": [0, 30, 100, 50]},
            {"text": "S07336-BHSN-T4TA-CH39R", "score": 0.99, "box": [0, 60, 100, 80]},
        ],
        "cards": [],
    }
    monkeypatch.setattr("ocr_line_recovery._write_line_crop", lambda *_args: "crop.png")
    monkeypatch.setattr("ocr_line_recovery._write_enhanced_crop", lambda *_args: "enhanced.png")
    monkeypatch.setattr("ocr_line_recovery.os.unlink", lambda *_args: None)

    results = iter(
        [
            ({"texts": [{"text": "S01336-3SRE-ETOS-QEXR1", "score": 0.95}]}, 10),
            ({"texts": [{"text": "S01336-3SRE-ETDS-QEXR7", "score": 0.98}]}, 12),
        ]
    )
    updated, recoveries = recover_suspicious_pubg_lines(
        "image.png", result, lambda _path: next(results)
    )

    assert "S07336-3SRE-ETDS-QEXR7" in [item["text"] for item in updated["cards"]]
    assert recoveries[0]["reason"] == "line_roi_recheck"


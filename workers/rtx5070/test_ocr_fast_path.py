from __future__ import annotations

import unittest

from ocr_fast_path import enhance_reason


def result(cards, texts=None, avg_score=0.50):
    return {
        "cards": cards,
        "texts": texts if texts is not None else cards,
        "card_count": len(cards),
        "avg_score": avg_score,
    }


def metrics(width=700, height=240, variance=180.0):
    return {"width": width, "height": height, "image_variance": variance}


class FastPathTests(unittest.TestCase):
    def test_clear_single_pubg_uses_original_fast_path(self):
        card = {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.995}
        self.assertEqual(enhance_reason(metrics(), result([card])), "not_needed")

    def test_unrelated_low_score_text_does_not_override_card_confidence(self):
        card = {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.995}
        texts = [card, {"text": "复制密码", "score": 0.40}]
        self.assertEqual(enhance_reason(metrics(), result([card], texts, avg_score=0.50)), "not_needed")

    def test_multi_card_image_keeps_enhanced_ocr(self):
        cards = [
            {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.995},
            {"text": "S07336-PQRS-TUVW-XYZAB", "score": 0.995},
        ]
        self.assertEqual(enhance_reason(metrics(), result(cards)), "multi_card_image")

    def test_incomplete_pubg_line_keeps_enhanced_ocr(self):
        card = {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.995}
        texts = [card, {"text": "S07336-PQRS-", "score": 0.99}]
        self.assertEqual(enhance_reason(metrics(), result([card], texts)), "incomplete_pubg_line")

    def test_low_card_score_keeps_enhanced_ocr(self):
        card = {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.96}
        self.assertEqual(enhance_reason(metrics(), result([card])), "card_score<0.985")

    def test_long_image_keeps_enhanced_ocr(self):
        card = {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.995}
        self.assertEqual(enhance_reason(metrics(height=900), result([card])), "height>500")

    def test_low_quality_image_keeps_enhanced_ocr(self):
        card = {"text": "S07336-ABCD-EFGH-JKLMN", "score": 0.995}
        self.assertEqual(enhance_reason(metrics(variance=40.0), result([card])), "image_variance<80")

    def test_psn_does_not_use_pubg_fast_path(self):
        card = {"text": "ABCD-EFGH-JKLM", "score": 0.995}
        self.assertEqual(enhance_reason(metrics(), result([card])), "non_pubg_or_mixed_cards")


if __name__ == "__main__":
    unittest.main()


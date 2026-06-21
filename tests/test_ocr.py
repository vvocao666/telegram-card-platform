from pathlib import Path

import bot
from services.ocr import ocr_service


def test_ocr_service_exports_current_functions():
    snapshot = Path("services/ocr/ocr_service.py")

    assert snapshot.exists()
    assert ocr_service.run_ocrspace is bot.run_ocrspace
    assert ocr_service.run_local_ocr is bot.run_local_ocr
    assert ocr_service.run_ocr is bot.run_ocr


def test_ocr_key_parser_keeps_current_behavior():
    assert bot.parse_ocrspace_api_keys("a,b; c", "d") == ["a", "b", "c", "d"]

from __future__ import annotations

from collections import Counter
import os
import re
import tempfile
from typing import Any, Callable

import cv2


VALID_CARD_RE = re.compile(
    r"(?<![A-Z0-9])(S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5})(?![A-Z0-9])"
)
VALID_PREFIX_RE = re.compile(r"(?<![A-Z0-9])(S07[0-9]{3})(?![0-9])")
FULL_CANDIDATE_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z][0-9]{5})-([A-Z0-9]{4})-([A-Z0-9]{4})-([A-Z0-9]{5})(?![A-Z0-9])"
)
SUSPICIOUS_CANDIDATE_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z][0-9]{5})-([A-Z0-9]{4})-([A-Z0-9]{4})-([A-Z0-9]{4})([^A-Z0-9\s-])(?![A-Z0-9])"
)


def recover_suspicious_pubg_lines(
    image_path: str,
    result: dict[str, Any],
    run_ocr_path: Callable[[str], tuple[dict[str, Any], int]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """只对同图多数前缀支持的异常行做局部放大复识别。"""
    texts = list(result.get("texts", []))
    dominant_prefix = _dominant_prefix(texts)
    if not dominant_prefix:
        return result, []

    recoveries: list[dict[str, str]] = []
    updated_texts = [dict(item) for item in texts]
    for index, item in enumerate(updated_texts):
        raw_text = str(item.get("text", "")).upper()
        suspicious = SUSPICIOUS_CANDIDATE_RE.search(raw_text)
        box = item.get("box")
        if not suspicious or not _one_prefix_digit_diff(suspicious.group(1), dominant_prefix) or not box:
            continue
        crop_path = _write_line_crop(image_path, box)
        if not crop_path:
            continue
        try:
            crop_results = [run_ocr_path(crop_path)[0]]
            enhanced_crop_path = _write_enhanced_crop(crop_path)
            if enhanced_crop_path:
                try:
                    crop_results.append(run_ocr_path(enhanced_crop_path)[0])
                finally:
                    try:
                        os.unlink(enhanced_crop_path)
                    except OSError:
                        pass
        finally:
            try:
                os.unlink(crop_path)
            except OSError:
                pass
        recovered = next(
            (
                candidate
                for crop_result in crop_results
                if (candidate := _select_recovered_card(crop_result, suspicious, dominant_prefix))
            ),
            None,
        )
        if not recovered:
            continue
        item["raw_text"] = item.get("text", "")
        item["text"] = recovered
        item["recovered"] = True
        recoveries.append(
            {
                "from": suspicious.group(0),
                "to": recovered,
                "reason": "line_roi_recheck",
            }
        )

    if not recoveries:
        return result, []
    updated = dict(result)
    updated["texts"] = updated_texts
    updated["cards"] = _cards_from_texts(updated_texts, result.get("cards", []))
    updated["text_count"] = len(updated_texts)
    updated["card_count"] = len(updated["cards"])
    return updated, recoveries


def _dominant_prefix(texts: list[dict[str, Any]]) -> str | None:
    prefixes: list[str] = []
    for item in texts:
        prefixes.extend(VALID_PREFIX_RE.findall(str(item.get("text", "")).upper()))
    if not prefixes:
        return None
    prefix, count = Counter(prefixes).most_common(1)[0]
    return prefix if count >= 2 else None


def _one_prefix_digit_diff(observed: str, expected: str) -> bool:
    return (
        len(observed) == len(expected) == 6
        and observed[:2] == expected[:2] == "S0"
        and sum(left != right for left, right in zip(observed, expected)) == 1
    )


def _select_recovered_card(
    crop_result: dict[str, Any],
    suspicious: re.Match[str],
    dominant_prefix: str,
) -> str | None:
    for item in crop_result.get("texts", []):
        text = str(item.get("text", "")).upper()
        for candidate in FULL_CANDIDATE_RE.finditer(text):
            if not _one_prefix_digit_diff(candidate.group(1), dominant_prefix):
                continue
            if candidate.group(2) != suspicious.group(2) or candidate.group(3) != suspicious.group(3):
                continue
            if candidate.group(4)[:4] != suspicious.group(4):
                continue
            return "-".join((dominant_prefix, candidate.group(2), candidate.group(3), candidate.group(4)))
    return None


def _write_line_crop(image_path: str, box: Any) -> str | None:
    image = cv2.imread(image_path)
    if image is None:
        return None
    values = _flat_box(box)
    if len(values) < 4:
        return None
    x1, y1, x2, y2 = values[:4]
    height, width = image.shape[:2]
    margin_x = max(8, int((x2 - x1) * 0.08))
    margin_y = max(5, int((y2 - y1) * 0.35))
    x1, y1 = max(0, x1 - margin_x), max(0, y1 - margin_y)
    x2, y2 = min(width, x2 + margin_x), min(height, y2 + margin_y)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = image[y1:y2, x1:x2]
    crop = cv2.resize(crop, None, fx=5, fy=5, interpolation=cv2.INTER_LANCZOS4)
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    if not cv2.imwrite(path, crop):
        os.unlink(path)
        return None
    return path


def _write_enhanced_crop(crop_path: str) -> str | None:
    image = cv2.imread(crop_path)
    if image is None:
        return None
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    filtered = cv2.bilateralFilter(enhanced, 5, 50, 50)
    blurred = cv2.GaussianBlur(filtered, (0, 0), 1.0)
    sharpened = cv2.addWeighted(filtered, 1.6, blurred, -0.6, 0)
    upscaled = cv2.resize(sharpened, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    if not cv2.imwrite(path, upscaled):
        os.unlink(path)
        return None
    return path


def _flat_box(box: Any) -> list[int]:
    values = box.tolist() if hasattr(box, "tolist") else box
    if not isinstance(values, (list, tuple)):
        return []
    if values and isinstance(values[0], (list, tuple)):
        xs = [int(point[0]) for point in values]
        ys = [int(point[1]) for point in values]
        return [min(xs), min(ys), max(xs), max(ys)]
    return [int(value) for value in values]


def _cards_from_texts(
    texts: list[dict[str, Any]], original_cards: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in texts:
        score = float(item.get("score", 0.0))
        text = str(item.get("text", "")).upper()
        if item.get("recovered"):
            candidates = VALID_CARD_RE.findall(text)
        else:
            candidates = [
                str(card.get("text", "")).upper()
                for card in original_cards
                if str(card.get("text", "")).upper() in text
            ]
            if not candidates:
                candidates = VALID_CARD_RE.findall(text)
        for card in candidates:
            if all(existing["text"] != card for existing in cards):
                cards.append({"text": card, "score": score})
    return cards


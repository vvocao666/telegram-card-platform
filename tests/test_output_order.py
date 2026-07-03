from __future__ import annotations

import html
import re
import time
import asyncio

import bot


def _card(index: int) -> str:
    return f"S07304-A{index:03d}-B{index:03d}-C{index:04d}"


def _pubg_lines(reply: str) -> list[str]:
    pre_match = re.search(r"<pre>(.*?)</pre>", reply, flags=re.S)
    if pre_match:
        return html.unescape(pre_match.group(1)).splitlines()
    code_match = re.search(r"<code>(.*?)</code>", reply, flags=re.S)
    return [html.unescape(code_match.group(1))] if code_match else []


def test_output_order_five_images_twenty_five_cards_matches_image_order():
    expected = [_card(index) for index in range(1, 26)]
    results = [
        bot.OcrResult(cards=tuple(expected[start : start + 5]))
        for start in range(0, 25, 5)
    ]

    reply = bot.format_reply(results)

    assert _pubg_lines(reply) == expected


def test_output_order_same_image_top_to_bottom():
    top = _card(1)
    middle = _card(2)
    bottom = _card(3)
    result = bot.OcrResult(
        cards=(bottom, top, middle),
        card_locations=(
            (bottom, 30, 0),
            (top, 10, 0),
            (middle, 20, 0),
        ),
    )

    reply = bot.format_reply([result])

    assert _pubg_lines(reply) == [top, middle, bottom]


def test_output_order_same_line_left_to_right():
    left = _card(1)
    center = _card(2)
    right = _card(3)
    result = bot.OcrResult(
        cards=(right, left, center),
        card_locations=(
            (right, 10, 30),
            (left, 10, 5),
            (center, 10, 20),
        ),
    )

    reply = bot.format_reply([result])

    assert _pubg_lines(reply) == [left, center, right]


def test_output_order_duplicate_keeps_first_position():
    first = _card(1)
    second = _card(2)
    third = _card(3)
    results = [
        bot.OcrResult(cards=(first, second)),
        bot.OcrResult(cards=(third, first)),
    ]

    reply = bot.format_reply(results)

    assert _pubg_lines(reply) == [first, second, third]
    assert reply.count(first) == 1


def test_output_order_thirty_one_images_uses_received_sequence_not_completion_order():
    first = "S07292-U4F9-EAVG-A29Q6"
    last = "S07292-VBKQ-6DJH-FJX6V"
    middle = [_card(index) for index in range(2, 31)]
    expected = [first, *middle, last]
    completed_out_of_order = [
        bot.OcrResult(cards=(card,), sequence_index=index)
        for index, card in reversed(list(enumerate(expected, start=1)))
    ]

    reply = bot.format_reply(completed_out_of_order)
    lines = _pubg_lines(reply)

    assert lines == expected
    assert lines[0] == first
    assert lines[-1] == last


def test_output_order_media_group_keeps_received_sequence_when_processing_finishes_out_of_order():
    first = _card(1)
    second = _card(2)
    third = _card(3)
    results = [
        bot.OcrResult(cards=(third,), sequence_index=3),
        bot.OcrResult(cards=(first,), sequence_index=1),
        bot.OcrResult(cards=(second,), sequence_index=2),
    ]

    reply = bot.format_reply(results)

    assert _pubg_lines(reply) == [first, second, third]


def test_output_order_duplicate_keeps_first_sequence_position():
    first = _card(1)
    duplicate = first
    second = _card(2)
    results = [
        bot.OcrResult(cards=(duplicate,), sequence_index=3),
        bot.OcrResult(cards=(second,), sequence_index=2),
        bot.OcrResult(cards=(first,), sequence_index=1),
    ]

    reply = bot.format_reply(results)

    assert _pubg_lines(reply) == [first, second]


def test_s07_marker_count_adds_missing_review_hint():
    result = bot.OcrResult(
        cards=("S07336-Y34D-KCW7-3X5DK",),
        pubg_expected_count=3,
    )

    reply = bot.format_reply([result])

    assert "S07336-Y34D-KCW7-3X5DK" in reply
    assert "2" in reply


def test_photo_display_order_prefers_telegram_message_id_over_receive_sequence():
    first_update = type("Update", (), {"message": type("Message", (), {"message_id": 5})()})()
    second_update = type("Update", (), {"message": type("Message", (), {"message_id": 9})()})()
    bot.photo_sequence_by_update.clear()
    bot.photo_sequence_by_update[id(first_update)] = 2
    bot.photo_sequence_by_update[id(second_update)] = 1

    updates = [second_update, first_update]
    updates.sort(key=bot.photo_display_order)

    assert updates == [first_update, second_update]


class _FakeProgressMessage:
    def __init__(self, text: str) -> None:
        self.texts = [text]
        self.deleted = False

    async def edit_text(self, text: str) -> None:
        self.texts.append(text)

    async def delete(self) -> None:
        self.deleted = True


class _FakeMessage:
    def __init__(self) -> None:
        self.progress_message: _FakeProgressMessage | None = None

    async def reply_text(self, text: str) -> _FakeProgressMessage:
        self.progress_message = _FakeProgressMessage(text)
        return self.progress_message


def test_ocr_batch_progress_edits_single_message_and_deletes_on_success():
    async def run_case():
        message = _FakeMessage()
        progress = bot.OcrBatchProgress(message, 20)

        await progress.start()
        for _ in range(19):
            await progress.mark_done()
        await progress.mark_done()
        await progress.finish(True)

        assert message.progress_message is not None
        assert message.progress_message.texts[0] == "正在识别 20 张图片，请稍候..."
        assert message.progress_message.texts[-1].endswith("处理进度：20/20")
        assert message.progress_message.deleted is True

    old_enabled = bot.OCR_PROGRESS_ENABLED
    old_min = bot.OCR_PROGRESS_MIN_IMAGES
    old_seconds = bot.OCR_PROGRESS_UPDATE_SECONDS
    try:
        bot.OCR_PROGRESS_ENABLED = True
        bot.OCR_PROGRESS_MIN_IMAGES = 3
        bot.OCR_PROGRESS_UPDATE_SECONDS = 999
        asyncio.run(run_case())
    finally:
        bot.OCR_PROGRESS_ENABLED = old_enabled
        bot.OCR_PROGRESS_MIN_IMAGES = old_min
        bot.OCR_PROGRESS_UPDATE_SECONDS = old_seconds


def test_ocr_batch_progress_throttles_intermediate_updates(monkeypatch):
    async def run_case():
        message = _FakeMessage()
        progress = bot.OcrBatchProgress(message, 5)

        await progress.start()
        await progress.mark_done()
        await progress.mark_done()
        current["value"] += 11
        await progress.mark_done()

        assert message.progress_message is not None
        assert message.progress_message.texts == [
            "正在识别 5 张图片，请稍候...",
            "正在识别 5 张图片，请稍候...\n处理进度：3/5",
        ]

    old_enabled = bot.OCR_PROGRESS_ENABLED
    old_min = bot.OCR_PROGRESS_MIN_IMAGES
    old_seconds = bot.OCR_PROGRESS_UPDATE_SECONDS
    try:
        bot.OCR_PROGRESS_ENABLED = True
        bot.OCR_PROGRESS_MIN_IMAGES = 3
        bot.OCR_PROGRESS_UPDATE_SECONDS = 10
        current = {"value": 1000.0}
        monkeypatch.setattr(time, "time", lambda: current["value"])
        asyncio.run(run_case())
    finally:
        bot.OCR_PROGRESS_ENABLED = old_enabled
        bot.OCR_PROGRESS_MIN_IMAGES = old_min
        bot.OCR_PROGRESS_UPDATE_SECONDS = old_seconds

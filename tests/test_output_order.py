from __future__ import annotations

import html
import re

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

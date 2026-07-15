import asyncio
from types import SimpleNamespace

from services.ocr.manual_review import ManualReviewNotifier


class Bot:
    def __init__(self):
        self.calls = []

    async def send_photo(self, **kwargs):
        self.calls.append(kwargs)


def result(**changes):
    values = {
        "pubg_expected_count": None,
        "psn_expected_count": None,
        "cards": (),
        "psn_cards": (),
        "uncertain_count": 0,
        "has_unresolved_pubg_fragment": False,
        "raw_text": "",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_review_replies_with_same_photo_once():
    notifier = ManualReviewNotifier()
    item = notifier.needs_review(result(pubg_expected_count=2, cards=("S07336-AAAA-BBBB-CCCCC",)))
    assert item is not None
    bot = Bot()
    update = SimpleNamespace(
        message=SimpleNamespace(
            chat=SimpleNamespace(id=99),
            message_id=12,
            photo=[SimpleNamespace(file_id="file", file_unique_id="unique")],
        )
    )
    context = SimpleNamespace(bot=bot)

    assert asyncio.run(notifier.notify(update, context, batch_index=3, item=item))
    assert not asyncio.run(notifier.notify(update, context, batch_index=3, item=item))
    assert bot.calls == [
        {
            "chat_id": 99,
            "photo": "file",
            "caption": "本批第 3 张图片识别结果无法确认，请人工核对。\n原因：识别数量少于图片中的卡密标记",
            "reply_to_message_id": 12,
        }
    ]


def test_review_does_not_require_confirmed_result():
    notifier = ManualReviewNotifier()
    assert notifier.needs_review(result(cards=("S07336-AAAA-BBBB-CCCCC",))) is None
    assert notifier.needs_review(result(has_unresolved_pubg_fragment=True)) is not None


def test_exact_repeated_pubg_evidence_does_not_trigger_review():
    notifier = ManualReviewNotifier()
    card = "S07317-3MEW-GA8A-BDTVA"
    raw_text = "\n".join(
        (
            card,
            card,
            f"{card}E",
            f"{card}#1",
            "VAIQE-VGVO-M3AT-LELOS",
        )
    )

    assert notifier.needs_review(result(cards=(card,), uncertain_count=1, raw_text=raw_text)) is None


def test_different_complete_pubg_candidate_still_triggers_review():
    notifier = ManualReviewNotifier()
    card = "S07336-TPM2-RZ9J-HCTBS"
    other = "S07336-TPM2-RZ9J-VICTB"

    item = notifier.needs_review(
        result(cards=(card,), uncertain_count=1, raw_text=f"{card}\n{card}\n{other}")
    )

    assert item is not None
    assert item.reason == "识别结果存在冲突，无法安全确认"

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

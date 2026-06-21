import asyncio

import pytest
from telegram.ext import ApplicationHandlerStop

import services.runtime as runtime
from services.ocr.today_cache import append_today_ocr_cache


class FakeUser:
    def __init__(self, user_id: int) -> None:
        self.id = user_id


class FakeMessage:
    def __init__(self, text: str, chat_id: int = 1) -> None:
        self.text = text
        self.chat_id = chat_id
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, text: str, user_id: int) -> None:
        self.message = FakeMessage(text)
        self.effective_user = FakeUser(user_id)
        self.effective_chat = None


class FakeContext:
    args: list[str] = []


HUMAN_TEXT = """S07304-AAAA-BBBB-CCCCC
S07304-DDDD-EEEE-FFFFF
S07304-1111-2222-33333
S07304-4444-5555-66666
S07304-7777-8888-99999"""


def test_owner_can_start_learn_cards_confirmation(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "OWNER_CHAT_ID", "1")
    runtime.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate("/learn_cards\n" + HUMAN_TEXT, user_id=1)

    asyncio.run(runtime.learn_cards_command(update, FakeContext()))

    assert "检测到 5 条人工正确卡密" in update.message.replies[-1]
    assert runtime.pending_learning_texts[1] == HUMAN_TEXT


def test_non_owner_cannot_start_learning(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "OWNER_CHAT_ID", "1")
    runtime.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate("/learn_cards\n" + HUMAN_TEXT, user_id=2)

    asyncio.run(runtime.learn_cards_command(update, FakeContext()))

    assert update.message.replies == []
    assert runtime.pending_learning_texts == {}


def test_learn_confirm_executes_and_cancel_discards(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "OWNER_CHAT_ID", "1")
    runtime.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    runtime.pending_learning_texts[1] = HUMAN_TEXT
    confirm = FakeUpdate("/learn_confirm", user_id=1)

    asyncio.run(runtime.learn_confirm_command(confirm, FakeContext()))

    assert "今日OCR学习完成" in confirm.message.replies[-1]
    assert 1 not in runtime.pending_learning_texts

    runtime.pending_learning_texts[1] = HUMAN_TEXT
    cancel = FakeUpdate("/learn_cancel", user_id=1)
    asyncio.run(runtime.learn_cancel_command(cancel, FakeContext()))

    assert "已取消" in cancel.message.replies[-1]
    assert 1 not in runtime.pending_learning_texts


def test_owner_plain_text_auto_enters_learning_confirmation(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "OWNER_CHAT_ID", "1")
    runtime.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate(HUMAN_TEXT, user_id=1)

    with pytest.raises(ApplicationHandlerStop):
        asyncio.run(runtime.auto_learn_cards_text(update, FakeContext()))

    assert "/learn_confirm" in update.message.replies[-1]
    assert runtime.pending_learning_texts[1] == HUMAN_TEXT


def test_non_owner_plain_text_does_not_trigger_learning(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime, "OWNER_CHAT_ID", "1")
    runtime.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate(HUMAN_TEXT, user_id=2)

    asyncio.run(runtime.auto_learn_cards_text(update, FakeContext()))

    assert update.message.replies == []
    assert runtime.pending_learning_texts == {}

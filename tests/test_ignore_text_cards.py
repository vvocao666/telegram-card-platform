import asyncio
from pathlib import Path

import bot
from services.ocr.today_cache import append_today_ocr_cache
from storage.repositories.ledger_storage import LedgerStore


class FakeUser:
    def __init__(self, user_id: int = 1) -> None:
        self.id = user_id
        self.username = "tester"
        self.first_name = "Test"
        self.last_name = ""


class FakeChat:
    def __init__(self, chat_id: int = -1001, chat_type: str = "group") -> None:
        self.id = chat_id
        self.type = chat_type
        self.title = "group"


class FakeMessage:
    def __init__(self, text: str, chat_id: int = -1001, user_id: int = 1) -> None:
        self.text = text
        self.caption = None
        self.chat_id = chat_id
        self.message_id = 10
        self.reply_to_message = None
        self.from_user = FakeUser(user_id)
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, text: str, user_id: int = 1, chat_id: int = -1001) -> None:
        self.message = FakeMessage(text, chat_id=chat_id, user_id=user_id)
        self.effective_user = self.message.from_user
        self.effective_chat = FakeChat(chat_id)


class FakeContext:
    args: list[str] = []


TEXT_CARDS = """S07304-AAAA-BBBB-CCCCC
S07304-DDDD-EEEE-FFFFF
S07304-1111-2222-33333
S07304-4444-5555-66666
S07304-7777-8888-99999"""


def install_temp_ledger_store(monkeypatch, tmp_path):
    old_store = bot.ledger_store
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    store.set_recognition_enabled(-1001, True)
    monkeypatch.setattr(bot, "ledger_store", store)
    return old_store, store


def test_plain_text_pubg_card_is_silent(monkeypatch, tmp_path):
    old_store, store = install_temp_ledger_store(monkeypatch, tmp_path)
    try:
        update = FakeUpdate("S07304-AAAA-BBBB-CCCCC")

        handled = asyncio.run(bot.handle_ledger_text(update, FakeContext()))

        assert handled is False
        assert update.message.replies == []
    finally:
        monkeypatch.setattr(bot, "ledger_store", old_store)
        store.close()


def test_multiline_text_cards_are_silent(monkeypatch, tmp_path):
    old_store, store = install_temp_ledger_store(monkeypatch, tmp_path)
    try:
        update = FakeUpdate(TEXT_CARDS)

        handled = asyncio.run(bot.handle_ledger_text(update, FakeContext()))

        assert handled is False
        assert update.message.replies == []
    finally:
        monkeypatch.setattr(bot, "ledger_store", old_store)
        store.close()


def test_owner_plain_text_no_longer_auto_enters_learning(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "1")
    bot.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate(TEXT_CARDS, user_id=1)

    asyncio.run(bot.auto_learn_cards_text(update, FakeContext()))

    assert update.message.replies == []
    assert bot.pending_learning_texts == {}


def test_learn_cards_command_still_works(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "1")
    bot.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate("/learn_cards\n" + TEXT_CARDS, user_id=1)

    asyncio.run(bot.learn_cards_command(update, FakeContext()))

    assert update.message.replies
    assert bot.pending_learning_texts[1] == TEXT_CARDS


def test_chinese_learn_cards_command_still_works(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bot, "OWNER_CHAT_ID", "1")
    bot.pending_learning_texts.clear()
    append_today_ocr_cache(["S07304-AAAA-BBBB-CCCCC"], path=tmp_path / "outputs" / "today_ocr_cache.json")
    update = FakeUpdate("学习卡密\n" + TEXT_CARDS, user_id=1, chat_id=1)

    asyncio.run(bot.learn_cards_command(update, FakeContext()))

    assert update.message.replies
    assert bot.pending_learning_texts[1] == TEXT_CARDS


def test_photo_and_status_handlers_remain_registered():
    registry_source = Path("handlers/registry.py").read_text(encoding="utf-8")

    assert "MessageHandler(filters.PHOTO, handle_photo)" in registry_source
    assert 'CommandHandler(["status", "ocr_status"], status_panel_command)' in registry_source
    assert r'^/状态' in registry_source
    assert 'CommandHandler("learn_cards", learn_cards_command)' in registry_source
    assert r"^/?学习卡密" in registry_source
    assert "auto_learn_cards_text" not in registry_source

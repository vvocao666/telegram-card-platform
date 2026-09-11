import asyncio
from types import SimpleNamespace

import pytest
from telegram.error import BadRequest, TimedOut

from services.ledger.bill_messages import replace_bill, send_bill
from storage.repositories.ledger_storage import LedgerStore


class Transport:
    def __init__(self):
        self.messages = {}
        self.next_id = 100
        self.delete_error = None
        self.send_error = False

    async def reply_text(self, text, **kwargs):
        assert kwargs['do_quote'] is False
        if self.send_error:
            raise TimedOut()
        self.next_id += 1
        self.messages[self.next_id] = text
        return SimpleNamespace(message_id=self.next_id)

    async def edit_message_text(self, chat_id, message_id, text, **kwargs):
        assert chat_id == -1001
        if message_id not in self.messages:
            raise BadRequest("Message to edit not found")
        if self.messages[message_id] == text:
            raise BadRequest("Message is not modified")
        self.messages[message_id] = text

    async def delete_message(self, chat_id, message_id):
        assert chat_id == -1001
        if self.delete_error:
            raise self.delete_error
        if message_id not in self.messages:
            raise BadRequest("Message to delete not found")
        del self.messages[message_id]

    def query(self, root_id):
        async def edit_root(**kwargs):
            await self.edit_message_text(-1001, root_id, **kwargs)

        return SimpleNamespace(
            message=SimpleNamespace(chat_id=-1001, message_id=root_id, reply_text=self.reply_text),
            get_bot=lambda: self,
            edit_message_text=edit_root,
        )


def test_long_bill_collapses_after_restart_without_touching_another_bill(tmp_path):
    path = tmp_path / 'ledger.sqlite3'
    store = LedgerStore(path)
    bot = Transport()
    message = SimpleNamespace(chat_id=-1001, reply_text=bot.reply_text)
    asyncio.run(send_bill(message, ['bill', 'page2', 'page3'], object(), store))
    first_pages = store.bill_pages(-1001, 101)
    assert first_pages == [102, 103]
    asyncio.run(send_bill(message, ['other bill', 'other page'], object(), store))
    store.close()
    store = LedgerStore(path)
    asyncio.run(replace_bill(bot.query(101), ['compact'], object(), store))
    assert bot.messages == {101: 'compact', 104: 'other bill', 105: 'other page'}
    assert store.bill_pages(-1001, 101) == []
    assert store.bill_pages(-1001, 104) == [105]
    for _ in range(2):
        asyncio.run(replace_bill(bot.query(101), ['detailed', 'page2', 'page3'], object(), store))
        assert len(bot.messages) == 5
        asyncio.run(replace_bill(bot.query(101), ['compact'], object(), store))
        assert len(bot.messages) == 3
    store.close()


@pytest.mark.parametrize('missing', [True, False])
def test_missing_and_too_old_pages_are_safely_collapsed(tmp_path, missing):
    store = LedgerStore(tmp_path / 'ledger.sqlite3')
    bot = Transport()
    message = SimpleNamespace(chat_id=-1001, reply_text=bot.reply_text)
    asyncio.run(send_bill(message, ['bill', 'page2'], object(), store))
    if missing:
        del bot.messages[102]
    else:
        bot.delete_error = BadRequest("Message can't be deleted")
    asyncio.run(replace_bill(bot.query(101), ['compact'], object(), store))
    assert 'page2' not in bot.messages.values()
    assert store.bill_pages(-1001, 101) == []
    store.close()


def test_delete_timeout_keeps_page_mapping_for_retry(tmp_path):
    store = LedgerStore(tmp_path / 'ledger.sqlite3')
    bot = Transport()
    message = SimpleNamespace(chat_id=-1001, reply_text=bot.reply_text)
    asyncio.run(send_bill(message, ['bill', 'page2'], object(), store))
    bot.delete_error = TimedOut()
    with pytest.raises(TimedOut):
        asyncio.run(replace_bill(bot.query(101), ['compact'], object(), store))
    assert store.bill_pages(-1001, 101) == [102]
    bot.delete_error = None
    asyncio.run(replace_bill(bot.query(101), ['compact'], object(), store))
    assert bot.messages == {101: 'compact'}
    store.close()

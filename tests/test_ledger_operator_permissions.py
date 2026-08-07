from services.ledger import ledger_commands
from storage.repositories.ledger_storage import LedgerStore


CHAT_ID = -1001
OWNER_ID = 100


def _actor(user_id: int, name: str) -> ledger_commands.Actor:
    return ledger_commands.Actor(user_id=user_id, username="", display_name=name)


def test_operator_can_manage_ledger_without_permission_escalation(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    owner = _actor(OWNER_ID, "群主")
    operator = _actor(200, "操作员")
    another_user = _actor(300, "普通成员")
    try:
        store.set_chat_owner(CHAT_ID, owner.user_id)
        store.add_operator(
            CHAT_ID,
            operator.user_id,
            operator.username,
            operator.display_name,
            owner.user_id,
        )

        assert "已设置为：10.00" in ledger_commands.handle_text(
            store, CHAT_ID, operator, "设置汇率 10", {OWNER_ID}
        ).text
        assert "已设置为：5.00%" in ledger_commands.handle_text(
            store, CHAT_ID, operator, "设置费率 5", {OWNER_ID}
        ).text
        assert "每天 01:00" in ledger_commands.handle_text(
            store, CHAT_ID, operator, "设置日切 1点", {OWNER_ID}
        ).text
        assert "记账功能已关闭" in ledger_commands.handle_text(
            store, CHAT_ID, operator, "关闭记账", {OWNER_ID}
        ).text
        assert "记账功能已开启" in ledger_commands.handle_text(
            store, CHAT_ID, operator, "开启记账", {OWNER_ID}
        ).text

        ledger_commands.handle_text(store, CHAT_ID, operator, "+100", {OWNER_ID})
        cleared = ledger_commands.handle_text(store, CHAT_ID, operator, "清空", {OWNER_ID})
        assert cleared is not None
        assert "已清空 1 笔流水" in cleared.text
        assert store.entries(CHAT_ID) == []

        denied = ledger_commands.handle_text(
            store,
            CHAT_ID,
            operator,
            "添加权限",
            {OWNER_ID},
            reply_user=another_user,
        )
        assert denied is not None
        assert "只有拉机器人进群的人可以添加操作员" in denied.text
        assert not store.is_operator(CHAT_ID, another_user.user_id, {OWNER_ID})
    finally:
        store.close()


def test_regular_member_still_cannot_manage_ledger(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite3")
    member = _actor(300, "普通成员")
    try:
        store.set_chat_owner(CHAT_ID, OWNER_ID)

        for command in ("关闭记账", "设置日切 1点", "清空"):
            result = ledger_commands.handle_text(store, CHAT_ID, member, command, {OWNER_ID})
            assert result is not None
            assert "只有群主或操作员" in result.text
    finally:
        store.close()

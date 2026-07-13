import asyncio
from decimal import Decimal
from pathlib import Path

from PIL import Image

from handlers.start_handler import add_group_keyboard, main_menu_keyboard, start_help_text
from services.forward.audit_service import audit_photo_file_ids, audit_source_text, update_is_private_chat
from services.group.group_service import group_welcome_message, parse_class_mode_command
from services.price.price_service import format_okx_prices, parse_okx_c2c_usdt_cny_prices
from services.status.status_service import StatusPanelSnapshot, render_status_panel
from services.trc20.verify_service import extract_trc20_address, make_trc20_verify_image
from utils.permission_utils import parse_chat_id, update_user_is_owner, update_user_or_chat_is_owner
from utils.telegram_utils import reply_html_chunks, send_html_chunks


def test_price_service_preserves_five_level_format():
    payload = {"data": {"sell": [{"price": value} for value in ("6.80", "6.81", "6.82", "6.83", "6.84", "6.85")]}}

    prices = parse_okx_c2c_usdt_cny_prices(payload)

    assert prices == [Decimal("6.80"), Decimal("6.81"), Decimal("6.82"), Decimal("6.83"), Decimal("6.84")]
    assert format_okx_prices(prices, "OKX C2C卖单").splitlines()[-1] == "来源：OKX C2C卖单"


def test_trc20_service_preserves_address_and_image_contract():
    address = "T" + "A" * 33

    assert extract_trc20_address(f"收款地址 {address}") == address
    image_data = make_trc20_verify_image(address)
    with Image.open(image_data) as image:
        assert image.size == (860, 300)
        assert image.format == "PNG"


def test_service_modules_do_not_import_runtime():
    for module_path in (
        Path("services/price/price_service.py"),
        Path("services/group/group_service.py"),
        Path("services/forward/audit_service.py"),
        Path("services/status/status_service.py"),
        Path("services/status/system_info.py"),
        Path("services/trc20/verify_service.py"),
        Path("handlers/start_handler.py"),
        Path("config/constants.py"),
        Path("utils/permission_utils.py"),
        Path("utils/telegram_utils.py"),
    ):
        assert "services.runtime" not in module_path.read_text(encoding="utf-8")


def test_start_handler_preserves_help_and_menu_contract():
    assert "<code>+10000</code>" in start_help_text()
    assert add_group_keyboard("kamibot").inline_keyboard[0][0].url == "https://t.me/kamibot?startgroup=true"
    assert main_menu_keyboard().keyboard[0][0].text == "✅记账拉机器人进群"


def test_audit_service_preserves_source_and_photo_contract():
    user = type(
        "User",
        (),
        {"id": 123, "username": "alice", "first_name": "Alice", "last_name": "Chen"},
    )()
    chat = type("Chat", (), {"id": -1001, "type": "group", "title": "Test <Group>"})()
    small = type("Photo", (), {"file_id": "small"})()
    large = type("Photo", (), {"file_id": "large"})()
    message = type("Message", (), {"photo": [small, large]})()
    update = type("Update", (), {"effective_user": user, "effective_chat": chat, "message": message})()

    assert "群组（Test &lt;Group&gt;）" in audit_source_text(update)
    assert "123 | @alice | Alice Chen" in audit_source_text(update)
    assert audit_photo_file_ids([update, update]) == ["large"]
    assert update_is_private_chat(update) is False


def test_status_service_preserves_panel_contract():
    text = render_status_panel(
        StatusPanelSnapshot(
            service_state="active",
            branch="main",
            commit="abc1234",
            memory="12.5 MB",
            uptime="2小时3分钟",
            ledger_exists=True,
            remote_label="RTX5070",
            remote_enabled=True,
            worker_ok=True,
            worker_status="ok",
            worker_gpu="RTX5070",
            worker_engine="paddlex_ocr",
            remote_url="127.0.0.1:8000",
            avg_remote_latency_ms=600,
            last_success="12:00:00",
            last_failed="无",
            last_error="无",
            current_provider="RTX5070",
            ocrspace_available=True,
            remote_calls=4,
            remote_success=3,
            remote_failed=1,
            fallback_count=1,
            cache_hit_rate="25.0%",
            enhanced_rate="50.0%",
            image_count=2,
            card_count=2,
            pubg_count=1,
            psn_count=1,
            duplicate_count=1,
            worker_extra=["opencv: True"],
        )
    )

    assert "状态：运行中" in text
    assert "服务：telegram-card-platform active/running" in text
    assert "GPU：RTX5070" in text
    assert "opencv: True" in text
    assert "缓存命中率：25.0%" in text
    assert "图片：2 张" in text


def test_group_service_preserves_command_and_welcome_contract():
    assert parse_class_mode_command("/上课") == "on"
    assert parse_class_mode_command("/下课@card_bot") == "off"
    assert parse_class_mode_command("上课") is None
    text = group_welcome_message()
    assert "记账与卡密识别机器人已加入本群" in text
    assert "<code>设置实时汇率</code>" in text
    assert "日切：每天 00:00（北京时间）" in text


def test_permission_utils_preserve_owner_matching_contract():
    user = type("User", (), {"id": 123})()
    chat = type("Chat", (), {"id": 456})()
    update = type("Update", (), {"effective_user": user, "effective_chat": chat})()

    assert parse_chat_id("123") == 123
    assert parse_chat_id("invalid") is None
    assert update_user_is_owner(update, "123") is True
    assert update_user_is_owner(update, "456") is False
    assert update_user_or_chat_is_owner(update, "456") is True


def test_telegram_utils_preserve_chunk_send_contract(monkeypatch):
    monkeypatch.setattr("utils.telegram_utils.split_html_message", lambda text: ["first", "second"])

    class Message:
        def __init__(self):
            self.calls = []

        async def reply_text(self, text, **kwargs):
            self.calls.append((text, kwargs))

    class Bot:
        def __init__(self):
            self.calls = []

        async def send_message(self, **kwargs):
            self.calls.append(kwargs)

    message = Message()
    bot = Bot()
    context = type("Context", (), {"bot": bot})()

    asyncio.run(reply_html_chunks(message, "content", reply_markup="keyboard"))
    asyncio.run(send_html_chunks(context, 123, "content"))

    assert message.calls[0][1]["reply_markup"] == "keyboard"
    assert "reply_markup" not in message.calls[1][1]
    assert [call["text"] for call in bot.calls] == ["first", "second"]
    assert all(call["disable_web_page_preview"] is True for call in bot.calls)

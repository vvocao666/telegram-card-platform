import os
import asyncio
import unittest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import bot
from services.ledger import ledger_commands
from storage.repositories import ledger_storage
from PIL import Image


class BotFormattingTests(unittest.TestCase):
    def make_update_stub(
        self,
        user_id=67890,
        chat_id=67890,
        chat_type="private",
        username="tester",
        first_name="Test",
        last_name="User",
        title="Test Group",
    ):
        User = type(
            "User",
            (),
            {
                "id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
            },
        )
        Chat = type("Chat", (), {"id": chat_id, "type": chat_type, "title": title})
        UpdateStub = type("UpdateStub", (), {"effective_user": User(), "effective_chat": Chat()})

        return UpdateStub()

    def test_owner_update_is_not_audit_forwarded(self):
        old_owner = bot.OWNER_CHAT_ID
        try:
            bot.OWNER_CHAT_ID = "12345"
            self.assertTrue(bot.update_is_from_owner(self.make_update_stub(user_id=12345, chat_id=99999)))
        finally:
            bot.OWNER_CHAT_ID = old_owner

    def test_start_help_mentions_core_features(self):
        help_text = bot.start_help_text()
        keyboard = bot.add_group_keyboard("kamibot")

        self.assertIn("卡密识别", help_text)
        self.assertIn("记账功能", help_text)
        self.assertIn("群发广播", help_text)
        self.assertIn("币价", help_text)
        self.assertNotIn("TRX 能量租赁", help_text)
        self.assertEqual("https://t.me/kamibot?startgroup=true", keyboard.inline_keyboard[0][0].url)

    def test_main_reply_keyboard_has_requested_menu_only(self):
        keyboard = bot.main_menu_keyboard()
        labels = [[button.text for button in row] for row in keyboard.keyboard]

        self.assertEqual(labels, [[bot.TEXT_LEDGER_ADD_GROUP]])



    def test_non_owner_update_can_be_audit_forwarded(self):
        old_owner = bot.OWNER_CHAT_ID
        try:
            bot.OWNER_CHAT_ID = "12345"
            self.assertFalse(bot.update_is_from_owner(self.make_update_stub(user_id=67890, chat_id=67890)))
        finally:
            bot.OWNER_CHAT_ID = old_owner

    def test_owner_private_uses_full_reply_and_skips_audit(self):
        old_owner = bot.OWNER_CHAT_ID
        old_audit_token = bot.AUDIT_BOT_TOKEN
        try:
            bot.OWNER_CHAT_ID = "12345"
            bot.AUDIT_BOT_TOKEN = "audit-token"
            updates = [self.make_update_stub(user_id=12345, chat_id=12345, chat_type="private")]
            results = [bot.OcrResult(cards=("S07304-EGWK-7K2G-4NVLH",))]

            reply = bot.format_source_reply(updates, results)

            self.assertIn("S07304-EGWK-7K2G-4NVLH", reply)
            self.assertIn("\u672c\u6b21\u8bc6\u522b\u6210\u529fPUBG\u5361\u5bc6\uff1a1\u4e2a\uff08\u70b9\u51fb\u5361\u5bc6\u590d\u5236\uff09", reply)
            self.assertFalse(bot.should_send_audit(updates))
        finally:
            bot.OWNER_CHAT_ID = old_owner
            bot.AUDIT_BOT_TOKEN = old_audit_token

    def test_non_owner_private_replies_and_sends_audit(self):
        old_owner = bot.OWNER_CHAT_ID
        old_audit_token = bot.AUDIT_BOT_TOKEN
        try:
            bot.OWNER_CHAT_ID = "12345"
            bot.AUDIT_BOT_TOKEN = "audit-token"
            updates = [self.make_update_stub(user_id=67890, chat_id=67890, chat_type="private")]

            self.assertTrue(bot.should_reply_to_source(updates))
            self.assertTrue(bot.should_send_audit(updates))
        finally:
            bot.OWNER_CHAT_ID = old_owner
            bot.AUDIT_BOT_TOKEN = old_audit_token

    def test_group_messages_reply_and_send_audit_even_from_owner(self):
        old_owner = bot.OWNER_CHAT_ID
        old_audit_token = bot.AUDIT_BOT_TOKEN
        try:
            bot.OWNER_CHAT_ID = "12345"
            bot.AUDIT_BOT_TOKEN = "audit-token"
            updates = [self.make_update_stub(user_id=12345, chat_id=-100123, chat_type="group")]

            self.assertTrue(bot.should_reply_to_source(updates))
            self.assertTrue(bot.should_send_audit(updates))
        finally:
            bot.OWNER_CHAT_ID = old_owner
            bot.AUDIT_BOT_TOKEN = old_audit_token

    def test_audit_source_text_includes_group_and_sender(self):
        update = self.make_update_stub(
            user_id=67890,
            chat_id=-100123,
            chat_type="group",
            username="alice",
            first_name="Alice",
            last_name="Chen",
            title="\u9e21\u5361\u84b8\u4e91",
        )

        text = bot.audit_source_text(update)

        self.assertIn("\u6765\u6e90: \u7fa4\u7ec4\uff08\u9e21\u5361\u84b8\u4e91\uff09", text)
        self.assertIn("\u53d1\u9001\u7528\u6237: 67890 | @alice | Alice Chen", text)

    def test_audit_source_text_marks_private_chat(self):
        update = self.make_update_stub(user_id=67890, chat_id=67890, chat_type="private")

        text = bot.audit_source_text(update)

        self.assertIn("\u6765\u6e90: \u79c1\u804a", text)

    def test_audit_photo_file_ids_use_largest_photo_once(self):
        update = self.make_update_stub(user_id=67890, chat_id=-1001, chat_type="group")
        small = type("Photo", (), {"file_id": "small"})()
        large = type("Photo", (), {"file_id": "large"})()
        update.message = type("Message", (), {"photo": [small, large]})()

        self.assertEqual(["large"], bot.audit_photo_file_ids([update, update]))

    def test_bot_groups_are_recorded_for_broadcast(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                update = self.make_update_stub(chat_id=-1001, chat_type="group", title="Test Broadcast Group")
                bot.remember_bot_chat(update)
                rows = store.list_active_bot_groups()

                self.assertEqual(1, len(rows))
                self.assertEqual(-1001, rows[0]["chat_id"])
                self.assertEqual("Test Broadcast Group", rows[0]["title"])
            finally:
                bot.ledger_store = old_store
                store.close()

    def test_calculator_expression(self):
        self.assertEqual("60*3=180.00", bot.calculate_expression("60*3"))
        self.assertEqual("80*6.8=544.00", bot.calculate_expression("80*6.8"))
        self.assertEqual("61075/8978=6.80", bot.calculate_expression("61075/8978"))
        self.assertEqual("(10+30)/2=20.00", bot.calculate_expression("(10 + 30) / 2"))
        self.assertEqual("100-25=75.00", bot.calculate_expression("100-25"))
        self.assertEqual("5*1.5=7.50", bot.calculate_expression("5*1.5"))
        self.assertEqual("1+2*3+2*6=19.00", bot.calculate_expression("1+2x3+2x6"))
        self.assertEqual("1+2*3+2*6=19.00", bot.calculate_expression("1+2×3+2×6"))
        self.assertEqual("60/3=20.00", bot.calculate_expression("60÷3"))
        self.assertEqual("1+2*3+2*6=19.00", bot.calculate_expression("１＋２×３＋２×６"))
    def test_calculator_ignores_non_expressions(self):
        self.assertIsNone(bot.calculate_expression("+100"))
        self.assertIsNone(bot.calculate_expression("账单"))
        self.assertIsNone(bot.calculate_expression("60abc*3"))

    def test_okx_price_parses_and_formats_five_levels(self):
        payload = {"data": {"sell": [{"price": str(6.70 + index / 100)} for index in range(6)]}}

        prices = bot.parse_okx_c2c_usdt_cny_prices(payload, limit=5)
        text = bot.format_okx_prices(prices, "OKX C2C卖单")

        self.assertEqual(5, len(prices))
        self.assertIn("欧意USDT/CNY 最新5档", text)
        self.assertIn("1. 6.7", text)
        self.assertIn("5. 6.74", text)
        self.assertNotIn("6. 6.75", text)

    def test_help_includes_okx_price_command(self):
        self.assertIn("币价/bj/z0 - 查看欧意USDT/CNY最新5档价格", ledger_commands.HELP_TEXT)
        self.assertIn("关闭记账/开启记账 - 暂停或恢复记账", ledger_commands.HELP_TEXT)
        self.assertIn("暂停/开启 - 关闭记账/开启记账的简写", ledger_commands.HELP_TEXT)
        self.assertIn("关闭识别/开启识别", ledger_commands.HELP_TEXT)
        self.assertIn("日切1 - 每天凌晨1点账单自动归0", ledger_commands.HELP_TEXT)
        self.assertIn("设置汇率1", ledger_commands.HELP_TEXT)

    def test_recognition_can_be_disabled_and_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                self.assertTrue(store.is_recognition_enabled(-1001))
                store.set_recognition_enabled(-1001, False)
                self.assertFalse(store.is_recognition_enabled(-1001))
                store.set_recognition_enabled(-1001, True)
                self.assertTrue(store.is_recognition_enabled(-1001))
            finally:
                store.close()

    def test_price_command_aliases(self):
        for text in ("币价", "bj", "BJ", "Bj", "bJ", "z0", "Z0", "/price"):
            self.assertTrue(bot.is_price_command(text))
        self.assertFalse(bot.is_price_command("bjj"))

    def test_long_html_messages_are_split_safely(self):
        text = "<b>PUBG卡密</b>\n\n<pre>" + "\n".join(f"S07304-TEST-{index:04d}-ABCDE" for index in range(80)) + "</pre>"

        chunks = bot.split_html_message(text, limit=500)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 520 for chunk in chunks))
        self.assertEqual(text.count("S07304-TEST-"), sum(chunk.count("S07304-TEST-") for chunk in chunks))
        for chunk in chunks:
            self.assertEqual(chunk.count("<pre>"), chunk.count("</pre>"))

    def test_local_ocr_card_candidates_need_votes(self):
        cards = [
            "S07304-CLFB-MVRN-MDQKJ",
            "S07304-CLFB-MVRN-MDQKJ",
            "S07304-E990-CFWT-5T3GP",
        ]

        self.assertEqual(["S07304-CLFB-MVRN-MDQKJ"], bot.filter_local_ocr_cards(cards, min_votes=2))
        self.assertEqual(
            ["S07304-CLFB-MVRN-MDQKJ", "S07304-E990-CFWT-5T3GP"],
            bot.filter_local_ocr_cards(cards, min_votes=1),
        )

    def test_ocrspace_api_key_parser_supports_rotation(self):
        self.assertEqual(
            ["key1", "key2", "legacy"],
            bot.parse_ocrspace_api_keys("key1,key2;key1", "legacy"),
        )
        self.assertEqual(["legacy"], bot.parse_ocrspace_api_keys("", "legacy"))

    def test_trc20_address_detection_and_image(self):
        address = "TUpTiQHHPUEWrbeABxjjwu3WULbjxJ2ZCZ"

        self.assertEqual(address, bot.extract_trc20_address(f"收款地址 {address}"))
        self.assertIsNone(bot.extract_trc20_address("T123"))

        image = bot.make_trc20_verify_image(address)
        self.assertEqual(b"\x89PNG\r\n\x1a\n", image.getvalue()[:8])

    def test_unrelated_images_are_ignored(self):
        reply = bot.format_reply([bot.OcrResult(cards=tuple())])

        self.assertEqual("\u672a\u8bc6\u522b\u5230\u5361\u5bc6", reply)
        self.assertNotIn("\u7b2c1\u5f20", reply)
        self.assertNotIn("\u8bc6\u522b\u6a21\u7cca", reply)
        self.assertNotIn("\u0401", reply)
        self.assertNotIn("\u041a", reply)

    def test_psn_limit_is_applied_before_summary_and_output(self):
        reply = bot.format_reply(
            [
                bot.OcrResult(
                    cards=tuple(),
                    psn_ordered=(
                        "AAAA-BBBB-CCCC",
                        "DDDD-EEEE-FFFF",
                        "GGGG-HHHH-IIII",
                    ),
                    psn_expected_count=None,
                )
            ]
        )

        self.assertIn("AAAA-BBBB-CCCC", reply)
        self.assertIn("DDDD-EEEE-FFFF", reply)
        self.assertNotIn("GGGG-HHHH-IIII", reply)
        self.assertIn("PSN\u5361\u5bc6\uff1a2\u4e2a\uff08\u70b9\u51fb\u5361\u5bc6\u590d\u5236\uff09", reply)

    def test_labeled_psn_suppresses_unlabeled_noise(self):
        ordered = bot.prefer_labeled_psn_ordered(
            [
                "\u5361\u53f7\uff1a X498-XRRB-3QGD",
                "Q00E-8UUX-86VX",
            ],
            ["X498-XRRB-3QGD", "Q00E-8UUX-86VX"],
        )
        reply = bot.format_reply([bot.OcrResult(cards=tuple(), psn_ordered=tuple(ordered))])

        self.assertEqual(["X498-XRRB-3QGD"], ordered)
        self.assertIn("X498-XRRB-3QGD", reply)
        self.assertNotIn("Q00E-8UUX-86VX", reply)
        self.assertIn("PSN\u5361\u5bc6\uff1a1\u4e2a\uff08\u70b9\u51fb\u5361\u5bc6\u590d\u5236\uff09", reply)

    def test_labeled_psn_takes_only_first_code_after_label(self):
        ordered = bot.prefer_labeled_psn_ordered(
            ["\u5361\u53f7\uff1a X498-XRRB-3QGD Q00E-8UUX-86VX"],
            ["X498-XRRB-3QGD", "Q00E-8UUX-86VX"],
        )

        self.assertEqual(["X498-XRRB-3QGD"], ordered)

    def test_labeled_psn_takes_one_code_per_label_same_line(self):
        ordered = bot.prefer_labeled_psn_ordered(
            ["\u5361\u53f7\uff1a FAK2-HXK2-MD99 \u5361\u53f7\uff1a 83BA-JPDT-5L8F"],
            ["FAK2-HXK2-MD99", "83BA-JPDT-5L8F"],
        )

        self.assertEqual(["FAK2-HXK2-MD99", "83BA-JPDT-5L8F"], ordered)

    def test_labeled_psn_takes_one_code_per_label_next_line(self):
        ordered = bot.prefer_labeled_psn_ordered(
            [
                "\u5361\u53f7\uff1a",
                "FAK2-HXK2-MD99",
                "\u5361\u53f7\uff1a",
                "83BA-JPDT-5L8F",
            ],
            ["FAK2-HXK2-MD99", "83BA-JPDT-5L8F"],
        )

        self.assertEqual(["FAK2-HXK2-MD99", "83BA-JPDT-5L8F"], ordered)

    def test_reply_includes_type_image_counts(self):
        reply = bot.format_reply(
            [
                bot.OcrResult(cards=("S07240-EVOO-N5GW-9A2KZ",)),
                bot.OcrResult(cards=("S07205-2QEJ-CRMP-N7CAW",)),
                bot.OcrResult(cards=("S07205-RHPA-KC2A-XYWFZ",)),
                bot.OcrResult(cards=tuple(), psn_ordered=("MELG-BTF8-JCJN", "NH9G-JN94-C292")),
                bot.OcrResult(cards=tuple(), psn_ordered=("6J6J-MHFL-77AX", "TCLL-7B6X-9B72")),
                bot.OcrResult(cards=tuple(), psn_ordered=("HFPP-6FAL-33E7",)),
                bot.OcrResult(cards=tuple()),
                bot.OcrResult(cards=tuple(), psn_ordered=("NK4A-5QTB-GDP5",)),
            ]
        )

        self.assertIn("<b>【PUBG\u5361\u5bc6】</b>", reply)
        self.assertIn("<b>\u672c\u6b21\u8bc6\u522b\u6210\u529fPUBG\u5361\u5bc6\uff1a3\u4e2a\uff08\u70b9\u51fb\u5361\u5bc6\u590d\u5236\uff09</b>", reply)
        self.assertIn("<pre>S07240-EVOO-N5GW-9A2KZ", reply)
        self.assertIn("\u672c\u6b21\u8bc6\u522bPUBG\u56fe\u7247\uff1a3\u5f20", reply)
        self.assertIn("<b>【PSN\u5361\u5bc6】</b>", reply)
        self.assertIn("<b>\u672c\u6b21\u8bc6\u522b\u6210\u529fPSN\u5361\u5bc6\uff1a6\u4e2a\uff08\u70b9\u51fb\u5361\u5bc6\u590d\u5236\uff09</b>", reply)
        self.assertIn("<pre>MELG-BTF8-JCJN", reply)
        self.assertIn("\u672c\u6b21\u8bc6\u522bPSN\u56fe\u7247\uff1a4\u5f20", reply)
        self.assertNotIn("\u8bc6\u522b\u6a21\u7cca", reply)

    def test_duplicate_pubg_cards_are_reported_by_image(self):
        reply = bot.format_reply(
            [
                bot.OcrResult(cards=("S07304-EGWK-7K2G-4NVLH",)),
                bot.OcrResult(cards=("S07304-EGWK-7K2G-4NVLH",)),
                bot.OcrResult(cards=("S07304-EGWK-7K2G-4NVLH",)),
            ]
        )

        self.assertEqual(reply.count("S07304-EGWK-7K2G-4NVLH"), 1)
        self.assertIn("<code>S07304-EGWK-7K2G-4NVLH</code>", reply)
        self.assertNotIn("<pre>S07304-EGWK-7K2G-4NVLH</pre>", reply)
        self.assertIn("\u672c\u6b21\u8bc6\u522b\u6210\u529fPUBG\u5361\u5bc6\uff1a1\u4e2a", reply)
        self.assertIn("\u672c\u6b21\u8bc6\u522bPUBG\u56fe\u7247\uff1a3\u5f20", reply)
        self.assertIn("\u91cd\u590d\u5361\u5bc6\uff1a\u7b2c2\u5f20\u7b2c3\u5f20\u4e0e\u7b2c1\u5f20\u91cd\u590d", reply)

    def test_pubg_ocr_variant_with_extra_character_is_suppressed(self):
        self.assertTrue(bot.likely_same_card("S07304-KVTE-JZGW-JVB4U", "S07304-KVTE-JZGW-JVB41J"))

    def test_pubg_card_length_is_strict(self):
        self.assertTrue(bot.valid_card("S07304-KVTE-JZGW-JVB4U"))
        self.assertFalse(bot.valid_card("S07304-KVTE-JZGW-JVB41J"))
        self.assertFalse(bot.valid_card("S0734-KVTE-JZGW-JVB4U"))
        self.assertFalse(bot.valid_card("S07304-KVTE1-JZGW-JVB4U"))
        self.assertFalse(bot.valid_card("S07304-KVTE-JZGW-JVB4"))

        self.assertEqual(["S07304-KVTE-JZGW-JVB4U"], bot.extract_cards("S07304-KVTE-JZGW-JVB4U"))
        self.assertEqual([], bot.extract_cards("S07304-KVTE-JZGW-JVB4"))
        self.assertEqual([], bot.extract_cards("S07304-KVTE-JZGW-JVB41J"))

    def test_pubg_card_after_label_digit_is_extracted(self):
        self.assertEqual(
            ["S07304-MBY6-MEF9-G7TFE"],
            bot.extract_cards("密码1S07304-MBY6-MEF9-G7TFE"),
        )
        self.assertEqual(
            ["S07304-MBY6-MEF9-G7TFE"],
            bot.extract_cards("密码1:S07304-MBY6-MEF9-G7TFE"),
        )

    def test_compact_pubg_card_after_label_is_extracted(self):
        self.assertEqual(
            ["S07304-MBY6-MEF9-G7TFE"],
            bot.extract_cards("密码1S07304MBY6MEF9G7TFE"),
        )
        self.assertEqual([], bot.extract_cards("密码1S07304MBY6MEF9G7TFEX"))

    def test_pubg_card_split_inside_groups_is_extracted(self):
        self.assertEqual(
            ["S07292-HV8Z-VH24-XEB4N"],
            bot.extract_cards("S07292-HV8\nZ-VH24-XEB4\nN"),
        )

    def test_handwritten_pubg_font_samples_are_extracted(self):
        samples = [
            "S07304-M5RX-Y2HN-2P8WH",
            "S07304-3SDA-2RWS-7LKE9",
            "S07304-7KLW-C58B-VZVSY",
            "S07304-WJB9-VPEZ-MUFWK",
            "S07304-RC96-Z437-QTWC9",
            "S07304-9M8Q-Y7UW-78Z2U",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual([sample], bot.extract_cards(sample))

    def test_pubg_prefix_s_read_as_9_is_repaired(self):
        self.assertEqual(
            ["S07304-M5RX-Y2HN-2P8WH"],
            bot.extract_cards("907304-M5RX-Y2HN-2P8WH"),
        )

    def test_pubg_card_stuck_after_numeric_prefix_is_extracted(self):
        self.assertEqual(
            ["S07304-S2RP-EE6E-VRE8S"],
            bot.extract_cards("2931SO7304-S2RP-EE6E-VRE8S sc"),
        )

    def test_pubg_card_split_with_ocr_pipe_is_extracted(self):
        self.assertEqual(
            ["S07304-4U6Q-U5LL-GLXUV"],
            bot.extract_cards("$07304-4U60-U5L1- | GLXUV"),
        )

    def test_pubg_card_with_trailing_ocr_noise_is_extracted(self):
        self.assertEqual(
            ["S07304-ZD2V-YN3E-WUT6R"],
            bot.extract_cards("g---S07304-ZD2V- | YN3E-WUT6REBRAB"),
        )

    def test_confirmed_handwritten_ocr_misreads_are_corrected(self):
        self.assertEqual(
            ["S07304-9M8Q-Y7UW-78Z2U"],
            bot.extract_cards("S07304-9M8Q-Y7UW-78220"),
        )
        self.assertEqual(
            ["S07304-8MP5-4TYS-VDVR6"],
            bot.extract_cards("S07304-8MP5-4TY9-VDVR6"),
        )

    def test_resize_for_ocr_upscales_small_images(self):
        image = Image.new("RGB", (500, 180), "white")
        resized = bot.resize_for_ocr(image, max_side_limit=2200, min_side_target=1400)

        self.assertEqual(1400, max(resized.size))

    def test_prepare_ocrspace_image_compresses_large_uploads(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "large.jpg"
            image = Image.effect_noise((2200, 2200), 90).convert("RGB")
            image.save(path, format="JPEG", quality=95)

            old_limit = bot.OCR_SPACE_MAX_UPLOAD_BYTES
            try:
                bot.OCR_SPACE_MAX_UPLOAD_BYTES = 300_000
                prepared = bot.prepare_ocrspace_image(path)
                self.assertLessEqual(prepared.stat().st_size, bot.OCR_SPACE_MAX_UPLOAD_BYTES)
                self.assertIn(prepared.suffix.lower(), {".jpg", ".png"})
            finally:
                bot.OCR_SPACE_MAX_UPLOAD_BYTES = old_limit

    def test_card_history_duplicate_is_reported_for_same_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                first = self.make_update_stub(user_id=111, chat_id=-1001, chat_type="group", username="first")
                second = self.make_update_stub(user_id=222, chat_id=-1001, chat_type="group", username="second")
                first.message = type("Message", (), {"message_id": 10})()
                second.message = type("Message", (), {"message_id": 11})()
                results = [bot.OcrResult(cards=("S07304-KVTE-JZGW-JVB4U",))]

                first_duplicates = bot.register_card_history([first], results)
                second_duplicates = bot.register_card_history([second], results)
                reply = bot.append_history_duplicates(bot.format_reply(results), second_duplicates)

                self.assertEqual([], first_duplicates)
                self.assertEqual(1, len(second_duplicates))
                self.assertIn("今日重复出现卡密", reply)
                self.assertIn("PUBG：<u>S07304-KVTE-JZGW-JVB4U</u>", reply)
                self.assertIn("已出现过", reply)
                self.assertIn("首次 ", reply)
                self.assertIn("首次 ", reply)
                self.assertIn("来自 | @first |", reply)
                self.assertNotIn("Test User", reply)
            finally:
                bot.ledger_store = old_store
                store.close()

    def test_card_history_old_day_is_cleared(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                update = self.make_update_stub(user_id=111, chat_id=-1001, chat_type="group", username="first")
                update.message = type("Message", (), {"message_id": 10})()
                current_day = bot.card_history_day_key(-1001)
                store.record_recognized_card(
                    -1001,
                    "PUBG",
                    "S07304-KVTE-JZGW-JVB4U",
                    "2000-01-01",
                    "@old",
                    1,
                )

                duplicates = bot.register_card_history(
                    [update],
                    [bot.OcrResult(cards=("S07304-KVTE-JZGW-JVB4U",))],
                )

                self.assertEqual([], duplicates)
                row = store.conn.execute("SELECT day_key FROM recognized_cards").fetchone()
                self.assertEqual(current_day, row["day_key"])
            finally:
                bot.ledger_store = old_store
                store.close()

    def test_card_correction_learning_persists_and_applies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            old_owner = bot.OWNER_CHAT_ID
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                bot.OWNER_CHAT_ID = "111"
                update = self.make_update_stub(user_id=111, chat_id=-1001, chat_type="group", username="teacher")
                reply_message = type(
                    "ReplyMessage",
                    (),
                    {"text": "PUBG卡密\nS07304-KVTE-JZGW-JVB4U", "caption": None},
                )()
                update.message = type(
                    "Message",
                    (),
                    {
                        "message_id": 20,
                        "text": "S07304-KVTE-JZGW-JVB4V",
                        "reply_to_message": reply_message,
                    },
                )()

                learned = bot.learn_card_corrections_from_reply(update)
                corrected = bot.apply_card_corrections(
                    -1001,
                    bot.OcrResult(cards=("S07304-KVTE-JZGW-JVB4U",)),
                )

                self.assertIsNotNone(learned)
                self.assertIn("已学习纠错", learned)
                self.assertEqual(("S07304-KVTE-JZGW-JVB4V",), corrected.cards)
                self.assertEqual(
                    "S07304-KVTE-JZGW-JVB4V",
                    store.get_card_correction(-1001, "PUBG", "S07304-KVTE-JZGW-JVB4U"),
                )
            finally:
                bot.ledger_store = old_store
                bot.OWNER_CHAT_ID = old_owner
                store.close()

    def test_non_owner_cannot_learn_card_correction_from_reply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            old_owner = bot.OWNER_CHAT_ID
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                bot.OWNER_CHAT_ID = "999"
                update = self.make_update_stub(user_id=111, chat_id=-1001, chat_type="group", username="teacher")
                reply_message = type(
                    "ReplyMessage",
                    (),
                    {"text": "PSN卡密\nRJTR-PTMQ-2H1C", "caption": None},
                )()
                update.message = type(
                    "Message",
                    (),
                    {
                        "message_id": 20,
                        "text": "FK4L-D7MP-2GQX",
                        "reply_to_message": reply_message,
                    },
                )()

                learned = bot.learn_card_corrections_from_reply(update)

                self.assertIsNone(learned)
                self.assertIsNone(store.get_card_correction(-1001, "PSN", "RJTR-PTMQ-2H1C"))
            finally:
                bot.ledger_store = old_store
                bot.OWNER_CHAT_ID = old_owner
                store.close()

    def test_ocr_sample_learning_persists_and_applies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            old_owner = bot.OWNER_CHAT_ID
            old_download = bot.download_message_photo
            old_run_ocr = bot.run_ocr
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store

            async def fake_download(message, context):
                image_path = Path(temp_dir) / "sample.jpg"
                image_path.write_text("image", encoding="utf-8")
                return image_path

            def fake_run_ocr(image_path, *args, **kwargs):
                return bot.OcrResult(cards=tuple(), raw_text="密码1 S0730XMBY6MEF9G7TFE")

            bot.download_message_photo = fake_download
            bot.run_ocr = fake_run_ocr
            try:
                bot.OWNER_CHAT_ID = "111"
                update = self.make_update_stub(user_id=111, chat_id=-1001, chat_type="group", username="teacher")
                photo = type("Photo", (), {"file_id": "file", "file_unique_id": "unique"})()
                reply_message = type("ReplyMessage", (), {"photo": [photo]})()
                update.message = type(
                    "Message",
                    (),
                    {
                        "message_id": 20,
                        "text": "S07304-MBY6-MEF9-G7TFE",
                        "reply_to_message": reply_message,
                    },
                )()

                learned = asyncio.run(bot.learn_ocr_sample_from_replied_photo(update, object()))
                corrected = bot.apply_card_corrections(
                    -1001,
                    bot.OcrResult(cards=tuple(), raw_text="密码1 S0730XMBY6MEF9G7TFE"),
                )

                self.assertIsNotNone(learned)
                self.assertIn("已学习这张图片的OCR特征", learned)
                self.assertEqual(("S07304-MBY6-MEF9-G7TFE",), corrected.cards)
            finally:
                bot.ledger_store = old_store
                bot.OWNER_CHAT_ID = old_owner
                bot.download_message_photo = old_download
                bot.run_ocr = old_run_ocr
                store.close()

    def test_learned_ocr_sample_hides_uncertain_conflict(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                store.set_ocr_text_correction(
                    -1001,
                    "PUBG",
                    "S0730XMBY6MEF9G7TFE",
                    "S07304-MBY6-MEF9-G7TFE",
                    "@teacher",
                )

                corrected = bot.apply_card_corrections(
                    -1001,
                    bot.OcrResult(
                        cards=("S07300-MBYG-MEF9-GAITE",),
                        raw_text="密码1 S0730XMBY6MEF9G7TFE",
                        uncertain_count=2,
                    ),
                )

                self.assertEqual(("S07304-MBY6-MEF9-G7TFE",), corrected.cards)
                self.assertEqual(0, corrected.uncertain_count)
            finally:
                bot.ledger_store = old_store
                store.close()

    def test_learned_correct_card_fixes_similar_ocr_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                store.set_ocr_text_correction(
                    -1001,
                    "PUBG",
                    "S0730XMBY6MEF9G7TFE",
                    "S07304-MBY6-MEF9-G7TFE",
                    "@teacher",
                )

                corrected = bot.apply_card_corrections(
                    -1001,
                    bot.OcrResult(cards=("S07300-MBY6-MET9-G7ITE",), uncertain_count=1),
                )

                self.assertEqual(("S07304-MBY6-MEF9-G7TFE",), corrected.cards)
                self.assertEqual(0, corrected.uncertain_count)
            finally:
                bot.ledger_store = old_store
                store.close()

    def test_learned_correction_applies_across_private_and_group_chats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_store = bot.ledger_store
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            bot.ledger_store = store
            try:
                store.set_ocr_text_correction(
                    -1001,
                    "PUBG",
                    "S0730XMBY6MEF9G7TFE",
                    "S07304-MBY6-MEF9-G7TFE",
                    "@teacher",
                )

                private_corrected = bot.apply_card_corrections(
                    8064848352,
                    bot.OcrResult(cards=("S07300-MBYG-MEF9-GAITE",), uncertain_count=2),
                )
                group_corrected = bot.apply_card_corrections(
                    -1001,
                    bot.OcrResult(cards=("S07300-MBYG-MEP9-GAITE",), uncertain_count=2),
                )

                self.assertEqual(("S07304-MBY6-MEF9-G7TFE",), private_corrected.cards)
                self.assertEqual(0, private_corrected.uncertain_count)
                self.assertEqual(("S07304-MBY6-MEF9-G7TFE",), group_corrected.cards)
                self.assertEqual(0, group_corrected.uncertain_count)
            finally:
                bot.ledger_store = old_store
                store.close()

    def test_no_card_results_are_silent(self):
        self.assertFalse(bot.has_card_results([bot.OcrResult(cards=tuple(), raw_text="hello")]))

    def test_text_card_result_with_pubg_suppresses_psn(self):
        result = bot.card_text_result("S07304-MBY6-MEF9-G7TFE\nMELG-BTF8-JCJN")

        self.assertIsNotNone(result)
        self.assertEqual(("S07304-MBY6-MEF9-G7TFE",), result.cards)
        self.assertEqual(tuple(), result.psn_ordered)

    def test_text_card_result_extracts_independent_psn(self):
        result = bot.card_text_result("MELG-BTF8-JCJN")

        self.assertIsNotNone(result)
        self.assertEqual(tuple(), result.cards)
        self.assertEqual(("MELG-BTF8-JCJN",), result.psn_ordered)

    def test_unlearnable_correction_feedback_when_reply_has_no_wrong_card(self):
        update = self.make_update_stub(user_id=111, chat_id=-1001, chat_type="group", username="teacher")
        reply_message = type("ReplyMessage", (), {"text": "未识别到卡密", "caption": None})()
        update.message = type(
            "Message",
            (),
            {
                "message_id": 20,
                "text": "S07304-MBY6-MEF9-G7TFE",
                "reply_to_message": reply_message,
            },
        )()

        feedback = bot.unlearnable_correction_feedback(update)

        self.assertIsNotNone(feedback)
        self.assertIn("原回复里没有错误卡密", feedback)

    def test_duplicate_psn_cards_are_reported_by_image(self):
        reply = bot.format_reply(
            [
                bot.OcrResult(cards=tuple(), psn_ordered=("MELG-BTF8-JCJN",)),
                bot.OcrResult(cards=tuple(), psn_ordered=("MELG-BTF8-JCJN",)),
            ]
        )

        self.assertEqual(reply.count("MELG-BTF8-JCJN"), 1)
        self.assertIn("\u672c\u6b21\u8bc6\u522b\u6210\u529fPSN\u5361\u5bc6\uff1a1\u4e2a\uff08\u70b9\u51fb\u5361\u5bc6\u590d\u5236\uff09", reply)
        self.assertIn("\u672c\u6b21\u8bc6\u522bPSN\u56fe\u7247\uff1a2\u5f20", reply)
        self.assertIn("\u91cd\u590d\u5361\u5bc6\uff1a\u7b2c2\u5f20\u4e0e\u7b2c1\u5f20\u91cd\u590d", reply)

    def test_cleanup_removes_only_old_server_file_records(self):
        old_tempfile = bot.tempfile
        old_outputs_dir = bot.CLEANUP_OUTPUTS_DIR
        old_after_seconds = bot.CLEANUP_AFTER_SECONDS
        try:
            with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as work_dir:
                temp_root = Path(temp_dir)
                output_root = Path(work_dir) / "outputs"
                output_root.mkdir()
                old_temp = temp_root / "s07_card_old"
                new_temp = temp_root / "s07_card_new"
                old_output = output_root / "old.jpg"
                new_output = output_root / "new.jpg"
                old_temp.mkdir()
                new_temp.mkdir()
                old_output.write_text("old", encoding="utf-8")
                new_output.write_text("new", encoding="utf-8")

                old_time = time.time() - 25 * 3600
                for path in (old_temp, old_output):
                    os_time = (old_time, old_time)
                    if path.is_dir():
                        path.joinpath("image.jpg").write_text("old", encoding="utf-8")
                        path.joinpath("image.jpg").touch()
                    path.touch()
                    os.utime(path, os_time)

                class TempfileStub:
                    @staticmethod
                    def gettempdir():
                        return str(temp_root)

                bot.tempfile = TempfileStub
                bot.CLEANUP_OUTPUTS_DIR = output_root
                bot.CLEANUP_AFTER_SECONDS = 24 * 3600

                removed = bot.cleanup_server_files()

                self.assertEqual(2, removed)
                self.assertFalse(old_temp.exists())
                self.assertFalse(old_output.exists())
                self.assertTrue(new_temp.exists())
                self.assertTrue(new_output.exists())
        finally:
            bot.tempfile = old_tempfile
            bot.CLEANUP_OUTPUTS_DIR = old_outputs_dir
            bot.CLEANUP_AFTER_SECONDS = old_after_seconds

    def test_photo_rate_limit_protects_chat_and_user(self):
        old_chat_limit = bot.PHOTO_RATE_LIMIT_PER_CHAT
        old_user_limit = bot.PHOTO_RATE_LIMIT_PER_USER
        old_window = bot.PHOTO_RATE_WINDOW_SECONDS
        try:
            bot.PHOTO_RATE_LIMIT_PER_CHAT = 2
            bot.PHOTO_RATE_LIMIT_PER_USER = 2
            bot.PHOTO_RATE_WINDOW_SECONDS = 60
            bot.photo_rate_chat.clear()
            bot.photo_rate_user.clear()

            User = type("User", (), {"id": 123})
            Chat = type("Chat", (), {"id": -1001})
            Message = type("Message", (), {"chat_id": -1001})
            UpdateStub = type(
                "UpdateStub",
                (),
                {"message": Message(), "effective_chat": Chat(), "effective_user": User()},
            )
            update = UpdateStub()

            self.assertIsNone(bot.photo_rate_limit_reason(update, now=1000))
            self.assertIsNone(bot.photo_rate_limit_reason(update, now=1001))
            self.assertIn("当前群图片发送太快", bot.photo_rate_limit_reason(update, now=1002))
            self.assertIsNone(bot.photo_rate_limit_reason(update, now=1062))
        finally:
            bot.PHOTO_RATE_LIMIT_PER_CHAT = old_chat_limit
            bot.PHOTO_RATE_LIMIT_PER_USER = old_user_limit
            bot.PHOTO_RATE_WINDOW_SECONDS = old_window
            bot.photo_rate_chat.clear()
            bot.photo_rate_user.clear()

    def test_owner_photo_rate_limit_is_bypassed(self):
        old_owner = bot.OWNER_CHAT_ID
        old_chat_limit = bot.PHOTO_RATE_LIMIT_PER_CHAT
        old_user_limit = bot.PHOTO_RATE_LIMIT_PER_USER
        try:
            bot.OWNER_CHAT_ID = "123"
            bot.PHOTO_RATE_LIMIT_PER_CHAT = 1
            bot.PHOTO_RATE_LIMIT_PER_USER = 1
            bot.photo_rate_chat.clear()
            bot.photo_rate_user.clear()
            User = type("User", (), {"id": 123})
            Chat = type("Chat", (), {"id": -1001})
            Message = type("Message", (), {"chat_id": -1001})
            UpdateStub = type(
                "UpdateStub",
                (),
                {"message": Message(), "effective_chat": Chat(), "effective_user": User()},
            )
            update = UpdateStub()

            self.assertIsNone(bot.photo_rate_limit_reason(update, now=1000))
            self.assertIsNone(bot.photo_rate_limit_reason(update, now=1001))
        finally:
            bot.OWNER_CHAT_ID = old_owner
            bot.PHOTO_RATE_LIMIT_PER_CHAT = old_chat_limit
            bot.PHOTO_RATE_LIMIT_PER_USER = old_user_limit
            bot.photo_rate_chat.clear()
            bot.photo_rate_user.clear()

    def test_ledger_commands_are_available_in_card_bot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")

                income = ledger_commands.handle_text(store, -1001, actor, "+100", {12345}, message_id=10)
                payout = ledger_commands.handle_text(store, -1001, actor, "-40", {12345}, message_id=11)
                bill = ledger_commands.handle_text(store, -1001, actor, "完整账单", {12345})

                self.assertIsNotNone(income)
                self.assertIsNotNone(payout)
                self.assertIsNotNone(bill)
                self.assertIn("已入款(1笔)", bill.text)
                self.assertIn("已下发(1笔)", bill.text)
                self.assertIn("应下发：100.00 | 100U", bill.text)
                self.assertIn("已下发：40U", bill.text)
                self.assertIn('未下发：【<a href="https://t.me/">60U</a>】', bill.text)
            finally:
                store.close()

    def test_ledger_zero_amount_shows_current_bill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")

                ledger_commands.handle_text(store, -1001, actor, "+100", {12345}, message_id=10)
                result = ledger_commands.handle_text(store, -1001, actor, "+0", {12345}, message_id=11)

                self.assertIsNotNone(result)
                self.assertIn("今日账单", result.text)
                self.assertIn("总入款金额：100.00", result.text)
            finally:
                store.close()

    def test_ledger_rate_divides_amount(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")

                rate_result = ledger_commands.handle_text(store, -1001, actor, "设置汇率10", {12345})
                income = ledger_commands.handle_text(store, -1001, actor, "+1000", {12345}, message_id=10)
                bill = ledger_commands.handle_text(store, -1001, actor, "账单", {12345})

                self.assertIsNotNone(rate_result)
                self.assertIn("汇率已设置为 10.0000", rate_result.text)
                self.assertIsNotNone(income)
                self.assertIsNotNone(bill)
                self.assertIn("1000.00/10=100.00U", bill.text)
                self.assertIn("汇率：10.0", bill.text)
                self.assertIn("总入款金额：1000.00", bill.text)
                self.assertIn("应下发：1000.00 | 100U", bill.text)
                self.assertIn("已下发：0U", bill.text)
                self.assertIn('未下发：【<a href="https://t.me/">100U</a>】', bill.text)
                self.assertLess(bill.text.index("总入款金额："), bill.text.index("汇率："))
                self.assertLess(bill.text.index("汇率："), bill.text.index("应下发："))
                self.assertLess(bill.text.index("应下发："), bill.text.index("已下发："))
                self.assertLess(bill.text.index("已下发："), bill.text.index("未下发："))
                self.assertIn("未下发：【<a", bill.text)
                self.assertIn("#1 加分", bill.text)
                self.assertIn("：+100.00 U", bill.text)
                self.assertNotIn("：+1000.00 U", bill.text)
            finally:
                store.close()

    def test_ledger_balance_uses_rmb_and_shows_usdt_side_by_side(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")

                ledger_commands.handle_text(store, -1001, actor, "设置汇率10", {12345})
                ledger_commands.handle_text(store, -1001, actor, "+1000", {12345}, message_id=10)
                ledger_commands.handle_text(store, -1001, actor, "-1500", {12345}, message_id=11)
                bill = ledger_commands.handle_text(store, -1001, actor, "账单", {12345})

                self.assertIsNotNone(bill)
                self.assertIn("总入款金额：1000.00", bill.text)
                self.assertIn("应下发：1000.00 | 100U", bill.text)
                self.assertIn("已下发：1500U", bill.text)
                self.assertIn('未下发：【<a href="https://t.me/">0U</a>】', bill.text)
            finally:
                store.close()

    def test_ledger_can_be_disabled_and_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                store.set_chat_owner(-1001, actor.user_id)

                disabled = ledger_commands.handle_text(store, -1001, actor, "关闭记账", {12345})
                ignored = ledger_commands.handle_text(store, -1001, actor, "+100", {12345}, message_id=10)
                enabled = ledger_commands.handle_text(store, -1001, actor, "开启记账", {12345})
                income = ledger_commands.handle_text(store, -1001, actor, "+100", {12345}, message_id=11)
                bill = ledger_commands.handle_text(store, -1001, actor, "账单", {12345})

                self.assertIsNotNone(disabled)
                self.assertIn("记账功能已关闭", disabled.text)
                self.assertIsNone(ignored)
                self.assertIsNotNone(enabled)
                self.assertIn("记账功能已开启", enabled.text)
                self.assertIsNotNone(income)
                self.assertIsNotNone(bill)
                self.assertIn("总入款金额：100.00", bill.text)
                self.assertNotIn("笔数：", bill.text)
            finally:
                store.close()

    def test_ledger_can_be_paused_and_opened_with_short_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                store.set_chat_owner(-1001, actor.user_id)

                paused = ledger_commands.handle_text(store, -1001, actor, "暂停", {12345})
                ignored = ledger_commands.handle_text(store, -1001, actor, "+100", {12345}, message_id=10)
                opened = ledger_commands.handle_text(store, -1001, actor, "开启", {12345})
                income = ledger_commands.handle_text(store, -1001, actor, "+100", {12345}, message_id=11)

                self.assertIsNotNone(paused)
                self.assertIn("暂停记账", paused.text)
                self.assertIsNone(ignored)
                self.assertIsNotNone(opened)
                self.assertIn("记账功能已开启", opened.text)
                self.assertIsNotNone(income)
            finally:
                store.close()

    def test_ledger_clears_previous_days_before_handling_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                old_entry = store.add_entry(-1001, "income", "100", "USDT", "", actor.user_id, actor.label, 10)
                today_entry = store.add_entry(-1001, "income", "200", "USDT", "", actor.user_id, actor.label, 11)
                yesterday_start, _ = ledger_commands._day_range_utc(-1)
                store.conn.execute("UPDATE entries SET created_at = ? WHERE id = ?", (yesterday_start, old_entry.id))
                store.conn.commit()

                result = ledger_commands.handle_text(store, -1001, actor, "完整账单", {12345})
                remaining = store.entries(-1001)

                self.assertIsNotNone(result)
                self.assertEqual([today_entry.id], [entry.id for entry in remaining])
                self.assertIn("总入款金额：200.00", result.text)
                self.assertNotIn("总入款金额：300.00", result.text)
            finally:
                store.close()

    def test_ledger_reset_hour_command_changes_daily_cutoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                store.set_chat_owner(-1001, actor.user_id)

                result = ledger_commands.handle_text(store, -1001, actor, "日切5", {12345})

                self.assertIsNotNone(result)
                self.assertIn("每天5点", result.text)
                self.assertEqual(5, store.get_ledger_reset_hour(-1001))
            finally:
                store.close()

    def test_ledger_reset_hour_requires_owner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                owner = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                guest = ledger_commands.Actor(user_id=67890, username="guest", display_name="Guest")
                store.set_chat_owner(-1001, owner.user_id)

                result = ledger_commands.handle_text(store, -1001, guest, "日切5", {owner.user_id})

                self.assertIsNotNone(result)
                self.assertIn("只有拉机器人进群的人可以设置日切时间", result.text)
                self.assertEqual(0, store.get_ledger_reset_hour(-1001))
            finally:
                store.close()

    def test_ledger_clears_before_configured_reset_hour(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                actor = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                store.set_ledger_reset_hour(-1001, 5)
                old_entry = store.add_entry(-1001, "income", "100", "USDT", "", actor.user_id, actor.label, 10)
                current_entry = store.add_entry(-1001, "income", "200", "USDT", "", actor.user_id, actor.label, 11)
                current_start, _ = ledger_commands._ledger_day_range_utc(store, -1001, 0)
                old_time = (datetime.fromisoformat(current_start) - timedelta(seconds=1)).isoformat(timespec="seconds")
                store.conn.execute("UPDATE entries SET created_at = ? WHERE id = ?", (old_time, old_entry.id))
                store.conn.execute("UPDATE entries SET created_at = ? WHERE id = ?", (current_start, current_entry.id))
                store.conn.commit()

                result = ledger_commands.handle_text(store, -1001, actor, "账单", {12345})
                remaining = store.entries(-1001)

                self.assertIsNotNone(result)
                self.assertEqual([current_entry.id], [entry.id for entry in remaining])
                self.assertIn("总入款金额：200.00", result.text)
                self.assertNotIn("总入款金额：300.00", result.text)
            finally:
                store.close()

    def test_ledger_all_users_can_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                guest = ledger_commands.Actor(user_id=67890, username="guest", display_name="Guest")

                result = ledger_commands.handle_text(store, -1001, guest, "+100", {12345})

                self.assertIsNotNone(result)
                self.assertIn("总入款金额：100.00", result.text)
            finally:
                store.close()

    def test_ledger_management_requires_chat_owner(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ledger_storage.LedgerStore(Path(temp_dir) / "ledger.sqlite3")
            try:
                owner = ledger_commands.Actor(user_id=12345, username="boss", display_name="Boss")
                guest = ledger_commands.Actor(user_id=67890, username="guest", display_name="Guest")
                store.set_chat_owner(-1001, owner.user_id)

                denied_close = ledger_commands.handle_text(store, -1001, guest, "关闭记账", {owner.user_id})
                denied_clear = ledger_commands.handle_text(store, -1001, guest, "清账", {owner.user_id})
                allowed_close = ledger_commands.handle_text(store, -1001, owner, "关闭记账", {owner.user_id})

                self.assertIsNotNone(denied_close)
                self.assertIn("只有拉机器人进群的人可以关闭记账", denied_close.text)
                self.assertIsNotNone(denied_clear)
                self.assertIn("只有拉机器人进群的人可以清账", denied_clear.text)
                self.assertIsNotNone(allowed_close)
                self.assertIn("记账功能已关闭", allowed_close.text)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

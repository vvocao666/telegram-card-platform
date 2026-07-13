from __future__ import annotations

import re


CLASS_ON_NOTICE = "✅本群已上课，开始接收卡密。"
CLASS_OFF_NOTICE = "❌本群已下课，已经停止接收卡密；\n\n请您【勿发卡密以及撤回卡密】，如卡密丢失概不负责，谢谢。"
CLASS_COMMAND_RE = re.compile(r"^/(上课|下课)(?:@\w+)?\s*$")


def parse_class_mode_command(text: str) -> str | None:
    match = CLASS_COMMAND_RE.match((text or "").strip())
    if not match:
        return None
    return "on" if match.group(1) == "上课" else "off"


def group_welcome_message() -> str:
    return (
        "🎉 记账与卡密识别机器人已加入本群\n\n"
        "主要功能：\n"
        "• 发送图片可自动识别 PUBG / PSN 卡密\n"
        "• 群记账功能\n"
        "• 查看实时汇率：采用欧意 USDT/CNY 最新 1 档价格更新本群汇率\n"
        "• 设置日切：设置每日账务日切时间\n"
        "• 使用说明：查看完整功能说明\n\n"
        "当前默认设置：\n"
        "汇率：1\n"
        "费率：0%\n"
        "日切：每天 00:00（北京时间）"
    )

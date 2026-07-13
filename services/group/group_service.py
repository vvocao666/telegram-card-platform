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
        "• 发送图片可识别 PUBG / PSN 卡密\n"
        "• <code>+10000</code>：新增入款\n"
        "• <code>-100 备注</code>：新增下发\n"
        "• <code>账单</code>：查看当前账单\n"
        "• <code>设置汇率 10</code>：设置群汇率\n"
        "• <code>设置费率 10</code>：设置群费率\n"
        "• <code>设置实时汇率</code>：采用欧意 USDT/CNY 最新 1 档价格更新本群汇率\n"
        "• <code>设置日切 1点</code>：设置每日账务日切时间\n"
        "• <code>使用说明</code>：查看完整功能说明\n\n"
        "当前默认设置：\n"
        "汇率：1\n"
        "费率：0%\n"
        "日切：每天 00:00（北京时间）"
    )

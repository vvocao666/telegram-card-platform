from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Callable, MutableMapping

from telegram import Update
from telegram.ext import ContextTypes


OwnerCheck = Callable[[Update], bool]


def debug_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if context.args:
        return " ".join(context.args)
    if update.message and update.message.reply_to_message:
        return update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    return ""


async def debug_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    is_owner: OwnerCheck,
    formatter: Callable[..., str],
) -> None:
    if not update.message or not is_owner(update):
        return
    raw_text = debug_input(update, context)
    if not raw_text:
        await update.message.reply_text("Usage: /ocr_debug raw_ocr_text")
        return
    await update.message.reply_text(formatter(raw_text, card_type="PUBG"))


async def candidates_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    is_owner: OwnerCheck,
    formatter: Callable[..., str],
) -> None:
    if not update.message or not is_owner(update):
        return
    raw_text = debug_input(update, context)
    if not raw_text:
        await update.message.reply_text("Usage: /ocr_candidates raw_ocr_text")
        return
    await update.message.reply_text(formatter(raw_text, card_type="PUBG"))


async def text_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    build_text: Callable[[], str],
) -> None:
    if not update.message or not is_owner(update):
        return
    await update.message.reply_text(build_text())


async def export_fonts_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    export_templates: Callable[[Path], Path],
    templates_path: Path,
) -> None:
    if not update.message or not is_owner(update):
        return
    path = export_templates(templates_path)
    if not path.exists():
        await update.message.reply_text("font_templates.json not found")
        return
    with path.open("rb") as template_file:
        await update.message.reply_document(document=template_file, filename="font_templates.json")


def command_body(update: Update, command: str) -> str:
    if not update.message or not update.message.text:
        return ""
    text = update.message.text
    first_line, _, rest = text.partition("\n")
    if first_line.strip().split(maxsplit=1)[0].split("@", 1)[0] != f"/{command}":
        return text
    inline = first_line.strip().split(maxsplit=1)
    values = []
    if len(inline) > 1:
        values.append(inline[1])
    if rest:
        values.append(rest)
    return "\n".join(values).strip()


async def import_fonts_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    is_owner: OwnerCheck,
    import_templates: Callable[[str, Path], int],
    templates_path: Path,
) -> None:
    if not update.message or not is_owner(update):
        return
    payload = command_body(update, "ocr_import_fonts")
    if not payload and update.message.reply_to_message and update.message.reply_to_message.document:
        document = update.message.reply_to_message.document
        tg_file = await context.bot.get_file(document.file_id)
        temp_dir = Path(tempfile.mkdtemp(prefix="ocr_font_import_"))
        temp_path = temp_dir / (document.file_name or "font_templates.json")
        try:
            await tg_file.download_to_drive(custom_path=temp_path)
            payload = temp_path.read_text(encoding="utf-8")
        finally:
            try:
                temp_path.unlink(missing_ok=True)
                temp_dir.rmdir()
            except OSError:
                pass
    if not payload:
        await update.message.reply_text("Usage: /ocr_import_fonts JSON 或回复 font_templates.json 文件")
        return
    try:
        count = import_templates(payload, templates_path)
    except Exception as exc:
        await update.message.reply_text(f"OCR font import failed: {exc}")
        return
    await update.message.reply_text(f"OCR font templates imported: {count}")


async def cache_today_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    cache_path: Path,
    summary_reader: Callable[[Path], object],
) -> None:
    if not update.message or not is_owner(update):
        return
    summary = summary_reader(cache_path)
    lines = [
        "OCR Cache Today",
        f"Date: {summary.date}",
        f"Images: {summary.images}",
        f"OCR cards: {summary.ocr_count}",
        f"Path: {summary.path}",
        "First 10:",
        *(summary.first_cards or ("-",)),
    ]
    await update.message.reply_text("\n".join(lines))


async def health_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    provider: str,
    ocrspace_key_count: int,
    local_fallback: bool,
    cache_path: Path,
    summary_reader: Callable[[Path], object],
) -> None:
    if not update.message or not is_owner(update):
        return
    summary = summary_reader(cache_path)
    lines = [
        "OCR Health",
        f"Provider: {provider}",
        f"OCRSpace keys: {ocrspace_key_count}",
        f"Local fallback: {local_fallback}",
        f"Today cache: {'ready' if summary.exists else 'missing'}",
        f"Today images: {summary.images}",
        f"Today OCR cards: {summary.ocr_count}",
    ]
    await update.message.reply_text("\n".join(lines))


async def remote_status_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    remote_available: Callable[[], tuple[bool, str]],
    remote_enabled: bool,
    remote_url: str,
    status: MutableMapping[str, object],
    average_latency: Callable[[], int],
    percent: Callable[[int, int], str],
    current_provider: Callable[[], str],
) -> None:
    if not update.message or not is_owner(update):
        return
    available, reason = await asyncio.to_thread(remote_available)
    remote_calls = int(status["today_remote_calls"])
    lines = [
        "Remote OCR Status",
        f"remote_enabled: {remote_enabled}",
        f"remote_url: {remote_url or '-'}",
        f"remote_health: {available}",
        f"health_reason: {reason}",
        f"last_success_at: {status['last_success_at'] or '-'}",
        f"last_failed_at: {status['last_failed_at'] or '-'}",
        f"last_error: {status['last_error'] or '-'}",
        f"today_remote_calls: {status['today_remote_calls']}",
        f"today_remote_success: {status['today_remote_success']}",
        f"today_remote_failed: {status['today_remote_failed']}",
        f"today_fallback_count: {status['today_fallback_count']}",
        f"avg_remote_latency_ms: {average_latency()}",
        f"enhanced_rate: {percent(int(status['today_enhanced_used']), remote_calls)}",
        f"cache_hit_rate: {percent(int(status['today_cache_hits']), remote_calls)}",
        f"current_provider: {current_provider()}",
    ]
    await update.message.reply_text("\n".join(lines))


def learn_cards_body(update: Update) -> str:
    text = command_body(update, "learn_cards")
    stripped = text.strip()
    chinese_command = stripped[1:] if stripped.startswith("/") else stripped
    if chinese_command == "学习卡密":
        return ""
    if chinese_command.startswith("学习卡密"):
        return chinese_command[len("学习卡密") :].lstrip(" \t\r\n")
    return text


async def learn_cards_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    preview_builder: Callable[[str], object],
    pending_texts: MutableMapping[int, str],
) -> None:
    if not update.message or not is_owner(update):
        return
    text = learn_cards_body(update)
    if not text:
        await update.message.reply_text("请在“学习卡密”后粘贴人工确认的卡密列表。")
        return
    preview = preview_builder(text)
    if not preview.ocr_cache_found:
        await update.message.reply_text(preview.message)
        return
    if preview.card_count < 5:
        await update.message.reply_text(f"仅检测到 {preview.card_count} 条合法卡密，至少需要 5 条才进入批量学习确认。")
        return
    if update.effective_user:
        pending_texts[update.effective_user.id] = text
    await update.message.reply_text(preview.message)


async def learn_confirm_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    pending_texts: MutableMapping[int, str],
    execute: Callable[[str], str],
) -> None:
    if not update.message or not is_owner(update) or not update.effective_user:
        return
    text = pending_texts.pop(update.effective_user.id, "")
    if not text:
        await update.message.reply_text("没有待确认的OCR学习任务。")
        return
    await update.message.reply_text(execute(text))


async def learn_cancel_command(
    update: Update,
    *,
    is_owner: OwnerCheck,
    pending_texts: MutableMapping[int, str],
) -> None:
    if not update.message or not is_owner(update) or not update.effective_user:
        return
    pending_texts.pop(update.effective_user.id, None)
    await update.message.reply_text("已取消今日OCR学习。")

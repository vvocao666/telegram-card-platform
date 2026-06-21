from __future__ import annotations

import asyncio
import ast
import html
import json
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, DivisionByZero, InvalidOperation
from io import BytesIO
from pathlib import Path

import httpx
import pytesseract
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

import ledger_commands
from ledger_commands import Actor as LedgerActor
from ledger_commands import handle_text as handle_ledger_command_text
from ledger_storage import LedgerStore
from trx_energy_bot.bot.admin import build_admin_handlers as build_trx_admin_handlers
from trx_energy_bot.bot.handlers import build_trx_conversation_handler
from trx_energy_bot.bot.keyboards import (
    TEXT_ADD_GROUP,
    TEXT_LEDGER,
    TEXT_LEDGER_ADD_GROUP,
    main_menu_keyboard as trx_main_menu_keyboard,
)
from trx_energy_bot.database.db import init_db as init_trx_db


load_dotenv()

BOT_VERSION = "strict-v104-trx-button-compat"
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "").strip()
AUDIT_BOT_TOKEN = os.getenv("AUDIT_BOT_TOKEN", "").strip()
AUDIT_CHAT_ID = os.getenv("AUDIT_CHAT_ID", "").strip()
SINGLE_WAIT_SECONDS = float(os.getenv("SINGLE_WAIT_SECONDS", os.getenv("BATCH_WAIT_SECONDS", "0.6")))
MULTI_BATCH_WAIT_SECONDS = max(
    float(os.getenv("MULTI_BATCH_WAIT_SECONDS", os.getenv("BATCH_WAIT_SECONDS", "3.0"))),
    2.0,
)
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "ocrspace").strip().lower()
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "").strip()
OCR_SPACE_MAX_SIDE = int(os.getenv("OCR_SPACE_MAX_SIDE", "3000"))
OCR_SPACE_MIN_SIDE = int(os.getenv("OCR_SPACE_MIN_SIDE", "2600"))
OCR_SPACE_TIMEOUT = float(os.getenv("OCR_SPACE_TIMEOUT", "18"))
OCR_SPACE_ENGINES = [engine.strip() for engine in os.getenv("OCR_SPACE_ENGINES", "2,1").split(",") if engine.strip()]
OCR_CONCURRENCY = int(os.getenv("OCR_CONCURRENCY", "5" if OCR_PROVIDER == "ocrspace" else "1"))
LOCAL_FALLBACK = os.getenv("LOCAL_FALLBACK", "1").strip() == "1"
LOCAL_COMPLEMENT = os.getenv("LOCAL_COMPLEMENT", "0").strip() == "1"
VERIFY_WITH_LOCAL = os.getenv("VERIFY_WITH_LOCAL", "0").strip() == "1"
OCR_MAX_SIDE = int(os.getenv("OCR_MAX_SIDE", "3000"))
OCR_MIN_SIDE = int(os.getenv("OCR_MIN_SIDE", "2600"))
MAX_PSN_PER_IMAGE = int(os.getenv("MAX_PSN_PER_IMAGE", "2"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()
PROXY_URL = os.getenv("PROXY_URL", "").strip()
TELEGRAM_TIMEOUT = float(os.getenv("TELEGRAM_TIMEOUT", "60"))
DEBUG_OCR = os.getenv("DEBUG_OCR", "").strip() == "1"
CLEANUP_ENABLED = os.getenv("CLEANUP_ENABLED", "1").strip() == "1"
CLEANUP_AFTER_SECONDS = max(60, int(float(os.getenv("CLEANUP_AFTER_HOURS", "24")) * 3600))
CLEANUP_CHECK_SECONDS = max(60, int(os.getenv("CLEANUP_CHECK_SECONDS", "300")))
CLEANUP_OUTPUTS_DIR = Path(os.getenv("CLEANUP_OUTPUTS_DIR", "outputs")).expanduser()
LEDGER_DB_PATH = Path(os.getenv("LEDGER_DB_PATH", "outputs/ledger.sqlite3")).expanduser()
OKX_C2C_USDT_CNY_URL = (
    "https://www.okx.com/v3/c2c/tradingOrders/books"
    "?quoteCurrency=cny&baseCurrency=usdt&side=sell&paymentMethod=all&userType=all&showTrade=false"
)
OKX_EXCHANGE_RATE_URL = "https://www.okx.com/api/v5/market/exchange-rate"
OKX_HTTP_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

SUCCESS_PREFIX = "\u672c\u6b21\u8bc6\u522b\u6210\u529f"
COUNT_SUFFIX = "\u4e2a"
UNCERTAIN_PREFIX = "\u7591\u4f3c\u51b2\u7a81"
UNCERTAIN_SUFFIX = "\u4e2a\u672a\u8f93\u51fa"
MANUAL_REVIEW_TEXT = "\u8bc6\u522b\u6a21\u7cca\uff0c\u8bf7\u4eba\u5de5\u6838\u5b9e"
MANUAL_REVIEW_SUMMARY = "\u9700\u4eba\u5de5\u6838\u5b9e"
PUBG_LABEL = "PUBG\u5361\u5bc6"
PSN_LABEL = "PSN\u5361\u5bc6"
FUZZY_SUFFIX = "\uff08\u8bc6\u522b\u6a21\u7cca\uff09"

if not TESSERACT_CMD:
    win_tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if win_tesseract.exists():
        TESSERACT_CMD = str(win_tesseract)

if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("s07-card-bot")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass(frozen=True)
class OcrResult:
    cards: tuple[str, ...]
    psn_cards: tuple[str, ...] = tuple()
    psn_uncertain: tuple[str, ...] = tuple()
    psn_ordered: tuple[str, ...] = tuple()
    pubg_expected_count: int | None = None
    psn_expected_count: int | None = None
    raw_text: str = ""
    uncertain_count: int = 0
    source_caption: str = ""


@dataclass(frozen=True)
class CardHistoryDuplicate:
    card_type: str
    card: str
    first_seen_at: str
    first_source_user: str


chat_buffers: dict[int, list[Update]] = defaultdict(list)
chat_tasks: dict[int, asyncio.Task] = {}
ocr_semaphore = asyncio.Semaphore(max(1, OCR_CONCURRENCY))
ledger_store = LedgerStore(LEDGER_DB_PATH)
LEDGER_TZ = timezone(timedelta(hours=8))
LEDGER_CALLBACK_TEXT = {
    "ledger:yesterday": "昨日账单",
    "ledger:today": "今日账单",
    "ledger:full": "完整账单",
    "ledger:help": "帮助",
}


FULLWIDTH_MAP = str.maketrans(
    {
        "\uff33": "S",
        "\uff2f": "O",
        "\uff31": "Q",
        "\uff24": "D",
        "\uff29": "I",
        "\uff2c": "L",
        "\uff34": "T",
        "\uff3a": "Z",
        "\uff22": "B",
        "\uff27": "G",
        "\uff10": "0",
        "\uff11": "1",
        "\uff12": "2",
        "\uff13": "3",
        "\uff14": "4",
        "\uff15": "5",
        "\uff16": "6",
        "\uff17": "7",
        "\uff18": "8",
        "\uff19": "9",
        "\u2014": "-",
        "\u2013": "-",
        "\uff0d": "-",
        "\u30fc": "-",
        "\uff3f": "_",
        "\uff1a": ":",
        "\uff1b": ";",
    }
)


def normalize_text(text: str) -> str:
    text = text.upper().translate(FULLWIDTH_MAP)
    return re.sub(r"((?:密码|卡号|CDK|CDKEY)\s*\d*[:：]?)\s*([SP5$][0ODQU][7TIL/?])", r"\1 \2", text)


def is_within_cleanup_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def remove_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink(missing_ok=True)
        return
    if path.is_dir():
        for child in path.iterdir():
            remove_path(child)
        path.rmdir()
    else:
        path.unlink(missing_ok=True)


def cleanup_server_files(now: float | None = None) -> int:
    if not CLEANUP_ENABLED:
        return 0
    cutoff = (now if now is not None else time.time()) - CLEANUP_AFTER_SECONDS
    removed = 0

    temp_root = Path(tempfile.gettempdir())
    for path in temp_root.glob("s07_card_*"):
        try:
            if path.stat().st_mtime <= cutoff and is_within_cleanup_root(path, temp_root):
                remove_path(path)
                removed += 1
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("Failed to clean temp path: %s", path)

    output_root = CLEANUP_OUTPUTS_DIR
    if not output_root.is_absolute():
        output_root = Path.cwd() / output_root
    if output_root.exists() and output_root.is_dir():
        for path in output_root.iterdir():
            try:
                if path.stat().st_mtime <= cutoff and is_within_cleanup_root(path, output_root):
                    remove_path(path)
                    removed += 1
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("Failed to clean output path: %s", path)
    if removed:
        logger.info("Cleaned %s old server file record(s).", removed)
    return removed


async def server_file_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(CLEANUP_CHECK_SECONDS)
        await asyncio.to_thread(cleanup_server_files)


async def start_background_tasks(app: Application) -> None:
    if CLEANUP_ENABLED:
        await asyncio.to_thread(cleanup_server_files)
        app.bot_data["server_file_cleanup_task"] = asyncio.create_task(server_file_cleanup_loop())


async def stop_background_tasks(app: Application) -> None:
    task = app.bot_data.get("server_file_cleanup_task")
    if isinstance(task, asyncio.Task):
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def repair_digit(char: str) -> str:
    # Only used inside S07xxx, where xxx must be digits.
    return {
        "O": "0",
        "D": "0",
        "Q": "0",
        "U": "0",
        "I": "1",
        "L": "1",
        "T": "1",
        "Z": "2",
        "E": "3",
        "A": "4",
        "S": "5",
        "$": "5",
        "G": "6",
        "B": "8",
    }.get(char, char)


def repair_first_group(group: str) -> str:
    chars = list(group)
    if len(chars) >= 1 and chars[0] in {"5", "$", "P"}:
        chars[0] = "S"
    if len(chars) >= 2 and chars[1] in {"O", "D", "Q", "U"}:
        chars[1] = "0"
    if len(chars) >= 3 and chars[2] in {"T", "I", "L", "/", "?"}:
        chars[2] = "7"
    for index in range(3, min(6, len(chars))):
        chars[index] = repair_digit(chars[index])
    return "".join(chars)


def valid_card(card: str) -> bool:
    return bool(re.fullmatch(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}", card))


def valid_psn_card(card: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", card))


def extract_cards(text: str) -> list[str]:
    text = normalize_text(text)
    sep = r"[\s\-_]+"
    shaped_pattern = (
        r"(?<![A-Z0-9])"
        r"([SP5$][0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{5})"
        + r"(?![A-Z0-9])"
    )

    cards: list[str] = []
    seen: set[str] = set()
    for first, second, third, fourth in re.findall(shaped_pattern, text):
        card = f"{repair_first_group(first)}-{second}-{third}-{fourth}"
        if valid_card(card) and card not in seen:
            seen.add(card)
            cards.append(card)

    compact_pattern = (
        r"(?<![A-Z0-9])"
        r"([SP5$][0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})"
        r"([A-Z0-9]{4})"
        r"([A-Z0-9]{4})"
        r"([A-Z0-9]{5})"
        r"(?![A-Z0-9])"
    )
    for first, second, third, fourth in re.findall(compact_pattern, text):
        card = f"{repair_first_group(first)}-{second}-{third}-{fourth}"
        if valid_card(card) and card not in seen:
            seen.add(card)
            cards.append(card)

    return cards


def repair_psn_group(group: str, index: int) -> tuple[str, bool]:
    return group, False


def scan_psn_candidates(text: str, force: bool = False) -> list[tuple[str, bool]]:
    text = normalize_text(text)
    pattern = (
        r"(?<![A-Z0-9-])"
        r"([A-Z0-9]{4})[\s_]*-[\s_]*([A-Z0-9]{4})[\s_]*-[\s_]*([A-Z0-9]{4})"
        r"(?![\s_]*-[\s_]*[A-Z0-9])"
        r"(?![A-Z0-9-])"
    )
    results: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for match in re.finditer(pattern, text):
        if match.start() > 0 and text[match.start() - 1] == "-":
            continue
        candidate = "-".join(match.groups())
        if not candidate.startswith("S07") and candidate not in seen:
            seen.add(candidate)
            results.append((candidate, False))
    return results


def scan_labeled_psn_candidates(text: str) -> list[tuple[str, bool]]:
    text = normalize_text(text)
    label_pattern = re.compile(r"(\u5361\s*\u53f7|\u5bc6\s*\u7801)")
    code_pattern = re.compile(
        r"([A-Z0-9]{4})[\s_]*-[\s_]*([A-Z0-9]{4})[\s_]*-[\s_]*([A-Z0-9]{4})"
        r"(?![\s_]*-[\s_]*[A-Z0-9])"
    )
    results: list[tuple[str, bool]] = []
    seen: set[str] = set()
    labels = list(label_pattern.finditer(text))
    for index, label_match in enumerate(labels):
        next_label_start = labels[index + 1].start() if index + 1 < len(labels) else len(text)
        after_label = text[label_match.end() : next_label_start]
        lines = after_label.splitlines()
        same_line = lines[0] if lines else after_label
        matches = list(code_pattern.finditer(same_line))
        if not matches:
            next_line = "\n".join(lines[1:2])
            matches = list(code_pattern.finditer(next_line))
        for match in matches[:1]:
            candidate = "-".join(match.groups())
            if candidate.startswith("S07") or candidate in seen:
                continue
            seen.add(candidate)
            results.append((candidate, False))
    return results


def extract_psn_ordered(text: str, force: bool = False) -> list[str]:
    labeled = scan_labeled_psn_candidates(text)
    if labeled:
        return psn_matches_to_lines(labeled)
    return [
        f"{card}{FUZZY_SUFFIX}" if fuzzy and not card.endswith(FUZZY_SUFFIX) else card
        for card, fuzzy in scan_psn_candidates(text, force=force)
    ]


def extract_psn_cards(text: str, force: bool = False) -> list[str]:
    return [card for card, fuzzy in scan_psn_candidates(text, force=force) if not fuzzy and valid_psn_card(card)]


def psn_matches_to_lines(matches: list[tuple[str, bool]]) -> list[str]:
    return [
        f"{card}{FUZZY_SUFFIX}" if fuzzy and not card.endswith(FUZZY_SUFFIX) else card
        for card, fuzzy in matches
    ]


def prefer_labeled_psn_ordered(raw_chunks: list[str], fallback_ordered: list[str]) -> list[str]:
    labeled = scan_labeled_psn_candidates("\n".join(raw_chunks))
    if labeled:
        return exact_unique_text(psn_matches_to_lines(labeled))
    return exact_unique_text(fallback_ordered)


def extract_uncertain_psn_cards(text: str, known_cards: list[str] | None = None, force: bool = False) -> list[str]:
    return []


def parse_psn_expected_count(caption: str) -> int | None:
    return None


def parse_pubg_expected_count(caption: str) -> int | None:
    return None


def limit_psn_ordered(cards: list[str], expected_count: int | None) -> list[str]:
    cards = unique_psn_lines(cards)
    if expected_count is None and MAX_PSN_PER_IMAGE > 0:
        expected_count = MAX_PSN_PER_IMAGE
    if expected_count is None or len(cards) <= expected_count:
        return cards
    exact = [card for card in cards if not card.endswith(FUZZY_SUFFIX)]
    if len(exact) >= expected_count:
        result: list[str] = []
        for card in cards:
            if not card.endswith(FUZZY_SUFFIX):
                result.append(card)
                if len(result) == expected_count:
                    return result
    return cards[:expected_count]


def exact_unique(cards: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if valid_card(card) and card not in seen:
            seen.add(card)
            result.append(card)
    return result


def exact_unique_psn(cards: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if valid_psn_card(card) and card not in seen:
            seen.add(card)
            result.append(card)
    return result


def exact_unique_text(cards: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for card in cards:
        if card and card not in seen:
            seen.add(card)
            result.append(card)
    return result


def psn_key(line: str) -> str | None:
    fuzzy = line.endswith(FUZZY_SUFFIX)
    card = line[: -len(FUZZY_SUFFIX)] if fuzzy else line
    card = normalize_text(card).strip()
    return card if valid_psn_card(card) else None


def unique_psn_lines(cards: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for line in cards:
        key = psn_key(line)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(f"{key}{FUZZY_SUFFIX}" if line.endswith(FUZZY_SUFFIX) else key)
    return result


def hamming_distance(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right))


def edit_distance_at_most(left: str, right: str, limit: int) -> bool:
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        row_min = current[0]
        for right_index, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            value = min(
                previous[right_index] + 1,
                current[right_index - 1] + 1,
                previous[right_index - 1] + cost,
            )
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return False
        previous = current
    return previous[-1] <= limit


def almost_same(left: str, right: str) -> bool:
    left_compact = left.replace("-", "")
    right_compact = right.replace("-", "")
    return len(left_compact) == len(right_compact) and hamming_distance(left_compact, right_compact) <= 1


def likely_same_card(left: str, right: str) -> bool:
    left_compact = left.replace("-", "")
    right_compact = right.replace("-", "")
    if len(left_compact) == len(right_compact):
        return hamming_distance(left_compact, right_compact) <= 3
    if abs(len(left_compact) - len(right_compact)) == 1:
        return edit_distance_at_most(left_compact, right_compact, 2)
    return False


def likely_learned_variant(left: str, right: str) -> bool:
    left_compact = left.replace("-", "")
    right_compact = right.replace("-", "")
    if len(left_compact) != len(right_compact):
        return False
    return edit_distance_at_most(left_compact, right_compact, 6)


def merge_card_variants(cards: list[str]) -> tuple[list[str], int]:
    merged: list[str] = []
    suppressed = 0
    for card in exact_unique(cards):
        if any(likely_same_card(card, existing) for existing in merged):
            suppressed += 1
            continue
        merged.append(card)
    return merged, suppressed


def merge_without_guessing(primary: list[str], secondary: list[str]) -> tuple[list[str], int]:
    merged = exact_unique(primary)
    uncertain = 0
    for card in exact_unique(secondary):
        if card in merged:
            continue
        if any(likely_same_card(card, existing) for existing in merged):
            uncertain += 1
            continue
        merged.append(card)
    return merged, uncertain


def settle_image_cards(cards: list[str]) -> tuple[list[str], int]:
    return merge_card_variants(cards)


def resize_for_ocr(image: Image.Image, max_side_limit: int, min_side_target: int) -> Image.Image:
    max_side = max(image.size)
    if max_side > max_side_limit:
        scale = max_side_limit / max_side
    elif max_side < min_side_target:
        scale = min_side_target / max_side
    else:
        return image
    return image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)


def prepare_ocrspace_image(image_path: Path) -> Path:
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")

    image = resize_for_ocr(image, OCR_SPACE_MAX_SIDE, OCR_SPACE_MIN_SIDE)

    output_path = image_path.with_suffix(".ocrspace.jpg")
    image.save(output_path, format="JPEG", quality=92, optimize=True)
    return output_path


def run_ocrspace(
    image_path: Path,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> OcrResult:
    upload_path: Path | None = None
    raw_chunks: list[str] = []
    all_cards: list[str] = []
    all_psn_ordered: list[str] = []
    uncertain_total = 0
    try:
        upload_path = prepare_ocrspace_image(image_path)
        with httpx.Client(timeout=OCR_SPACE_TIMEOUT) as client:
            for engine in OCR_SPACE_ENGINES:
                with upload_path.open("rb") as image_file:
                    response = client.post(
                        "https://api.ocr.space/parse/image",
                        data={
                            "apikey": OCR_SPACE_API_KEY,
                            "language": "eng",
                            "OCREngine": engine,
                            "scale": "true",
                            "detectOrientation": "true",
                            "isTable": "false",
                        },
                        files={"file": (upload_path.name, image_file, "image/jpeg")},
                    )
                response.raise_for_status()
                payload = response.json()
                if payload.get("IsErroredOnProcessing"):
                    logger.warning("OCR.space engine %s error: %s", engine, payload.get("ErrorMessage"))
                    continue

                chunks = [parsed.get("ParsedText", "") for parsed in payload.get("ParsedResults", []) or []]
                raw_text = "\n".join(chunk for chunk in chunks if chunk)
                if raw_text:
                    raw_chunks.append(raw_text)

                cards, uncertain = settle_image_cards(extract_cards(raw_text))
                psn_ordered = exact_unique_text(extract_psn_ordered(raw_text, force=psn_hint or not cards))
                all_cards.extend(cards)
                all_psn_ordered.extend(psn_ordered)
                uncertain_total += uncertain
        merged_cards, conflict_count = merge_card_variants(all_cards)
        psn_ordered = limit_psn_ordered(prefer_labeled_psn_ordered(raw_chunks, all_psn_ordered), psn_expected_count)
        psn_cards = exact_unique_psn([card for card in psn_ordered if not card.endswith(FUZZY_SUFFIX)])
        psn_uncertain = exact_unique_text([card for card in psn_ordered if card.endswith(FUZZY_SUFFIX)])
        uncertain_total += conflict_count
        if merged_cards or psn_cards or psn_uncertain:
            return OcrResult(
                        cards=tuple(merged_cards),
                        psn_cards=tuple(psn_cards),
                        psn_uncertain=tuple(psn_uncertain),
                        psn_ordered=tuple(psn_ordered),
                        pubg_expected_count=pubg_expected_count,
                        psn_expected_count=psn_expected_count,
                        raw_text="\n".join(raw_chunks),
                        uncertain_count=uncertain_total,
                    )
    except Exception:
        logger.exception("OCR.space request failed")
        return OcrResult(cards=tuple())
    finally:
        if upload_path:
            upload_path.unlink(missing_ok=True)

    return OcrResult(
        cards=tuple(),
        psn_cards=tuple(),
        pubg_expected_count=pubg_expected_count,
        psn_expected_count=psn_expected_count,
        raw_text="\n".join(raw_chunks),
        uncertain_count=uncertain_total,
    )


def rotations_for(image: Image.Image) -> list[Image.Image]:
    return [image, image.rotate(90, expand=True), image.rotate(270, expand=True)]


def crop_regions(image: Image.Image) -> list[Image.Image]:
    width, height = image.size
    boxes = [
        (0, 0, width, height),
        (int(width * 0.03), int(height * 0.18), int(width * 0.97), int(height * 0.90)),
        (0, int(height * 0.25), int(width * 0.86), int(height * 0.78)),
        (0, int(height * 0.35), int(width * 0.82), int(height * 0.65)),
        (int(width * 0.02), int(height * 0.30), int(width * 0.72), int(height * 0.72)),
    ]
    return [image.crop(box) for box in boxes]


def enhance(region: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(region)
    contrast = ImageEnhance.Contrast(gray).enhance(1.9)
    return contrast.filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))


def enhance_variants(region: Image.Image) -> list[Image.Image]:
    enhanced = enhance(region)
    threshold = enhanced.point(lambda pixel: 255 if pixel > 178 else 0)
    return [enhanced, threshold]


def iter_local_ocr_images(image_path: Path):
    with Image.open(image_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGB")

    source = resize_for_ocr(source, OCR_MAX_SIDE, OCR_MIN_SIDE)

    for rotated in rotations_for(source):
        for region in crop_regions(rotated):
            yield from enhance_variants(region)


def run_local_ocr(
    image_path: Path,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> OcrResult:
    configs = [
        "--oem 3 --psm 6 --dpi 300 "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-$",
        "--oem 3 --psm 7 --dpi 300 "
        "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-$",
    ]
    raw_chunks: list[str] = []
    cards: list[str] = []
    psn_cards: list[str] = []
    psn_uncertain: list[str] = []
    psn_ordered: list[str] = []

    for image in iter_local_ocr_images(image_path):
        for config in configs:
            try:
                text = pytesseract.image_to_string(image, lang="eng", config=config)
            except Exception:
                logger.exception("Local OCR failed")
                continue
            if text.strip():
                raw_chunks.append(text)
                if DEBUG_OCR:
                    logger.info("Local OCR text: %s", text.strip().replace("\n", " | ")[:500])
            text_cards = extract_cards(text)
            cards.extend(text_cards)
            ordered = extract_psn_ordered(text, force=psn_hint or not text_cards)
            psn_ordered.extend(ordered)
            psn_cards.extend(card for card in ordered if not card.endswith(FUZZY_SUFFIX))
            psn_uncertain.extend(card for card in ordered if card.endswith(FUZZY_SUFFIX))

    settled_cards, uncertain = settle_image_cards(cards)
    return OcrResult(
        cards=tuple(settled_cards),
        psn_cards=tuple(exact_unique_psn(psn_cards)),
        psn_uncertain=tuple(exact_unique_text(psn_uncertain)),
        psn_ordered=tuple(limit_psn_ordered(prefer_labeled_psn_ordered(raw_chunks, psn_ordered), psn_expected_count)),
        pubg_expected_count=pubg_expected_count,
        psn_expected_count=psn_expected_count,
        raw_text="\n".join(raw_chunks),
        uncertain_count=uncertain,
    )


def run_ocr(
    image_path: Path,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> OcrResult:
    if OCR_PROVIDER == "ocrspace" and OCR_SPACE_API_KEY:
        remote = run_ocrspace(
            image_path,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )
        if (remote.cards or remote.psn_cards or remote.psn_uncertain) and not VERIFY_WITH_LOCAL and not LOCAL_COMPLEMENT:
            return remote
        if not LOCAL_FALLBACK and not VERIFY_WITH_LOCAL:
            return remote

        local = run_local_ocr(
            image_path,
            psn_hint=psn_hint,
            psn_expected_count=psn_expected_count,
            pubg_expected_count=pubg_expected_count,
        )
        merged, uncertain = merge_without_guessing(list(remote.cards), list(local.cards))
        merged_psn = exact_unique_psn(list(remote.psn_cards) + list(local.psn_cards))
        merged_psn_uncertain = exact_unique_text(list(remote.psn_uncertain) + list(local.psn_uncertain))
        merged_psn_ordered = limit_psn_ordered(list(remote.psn_ordered) + list(local.psn_ordered), psn_expected_count)
        settled_cards, conflict_count = settle_image_cards(merged)
        uncertain += remote.uncertain_count + local.uncertain_count + conflict_count
        if settled_cards or merged_psn or merged_psn_uncertain:
            return OcrResult(
                cards=tuple(settled_cards),
                psn_cards=tuple(merged_psn),
                psn_uncertain=tuple(merged_psn_uncertain),
                psn_ordered=tuple(merged_psn_ordered),
                pubg_expected_count=pubg_expected_count,
                psn_expected_count=psn_expected_count,
                raw_text=remote.raw_text + "\n" + local.raw_text,
                uncertain_count=uncertain,
            )
        return OcrResult(
            cards=tuple(),
            psn_cards=tuple(),
            psn_uncertain=tuple(merged_psn_uncertain),
            psn_ordered=tuple(merged_psn_ordered),
            pubg_expected_count=pubg_expected_count,
            psn_expected_count=psn_expected_count,
            raw_text=local.raw_text,
            uncertain_count=uncertain,
        )

    return run_local_ocr(
        image_path,
        psn_hint=psn_hint,
        psn_expected_count=psn_expected_count,
        pubg_expected_count=pubg_expected_count,
    )


async def download_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Path:
    if not update.message or not update.message.photo:
        raise ValueError("No photo received")
    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    temp_dir = Path(tempfile.mkdtemp(prefix="s07_card_"))
    image_path = temp_dir / f"{photo.file_unique_id}.jpg"
    await tg_file.download_to_drive(custom_path=image_path)
    return image_path


async def download_message_photo(message, context: ContextTypes.DEFAULT_TYPE) -> Path:
    photo_sizes = getattr(message, "photo", None)
    if not photo_sizes:
        raise ValueError("No photo received")
    photo = photo_sizes[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    temp_dir = Path(tempfile.mkdtemp(prefix="s07_learn_"))
    image_path = temp_dir / f"{photo.file_unique_id}.jpg"
    await tg_file.download_to_drive(custom_path=image_path)
    return image_path


async def recognize_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> OcrResult:
    image_path = await download_photo(update, context)
    caption = update.message.caption if update.message and update.message.caption else ""
    psn_hint = "PSN" in normalize_text(caption)
    psn_expected_count = parse_psn_expected_count(caption)
    pubg_expected_count = parse_pubg_expected_count(caption)
    try:
        async with ocr_semaphore:
            result = await asyncio.to_thread(run_ocr, image_path, psn_hint, psn_expected_count, pubg_expected_count)
            return replace(result, source_caption=caption.strip())
    finally:
        try:
            image_path.unlink(missing_ok=True)
            image_path.parent.rmdir()
        except OSError:
            pass


def result_location(index: int, result: OcrResult) -> str:
    return f"第{index}张"


def format_duplicate_lines(groups: list[tuple[int, list[int]]]) -> list[str]:
    lines: list[str] = []
    for first_index, duplicate_indexes in groups:
        unique_duplicates = sorted(dict.fromkeys(index for index in duplicate_indexes if index != first_index))
        if not unique_duplicates:
            continue
        duplicate_text = "".join(f"第{index}张" for index in unique_duplicates)
        lines.append(f"重复卡密：{duplicate_text}与第{first_index}张重复")
    return lines


def format_card_code(card: str) -> str:
    return f"<code>{html.escape(card)}</code>"


def format_card_codes(cards: list[str]) -> str:
    if len(cards) == 1:
        return format_card_code(cards[0])
    return f"<pre>{html.escape(chr(10).join(cards))}</pre>"


def format_underlined_card_code(card: str) -> str:
    return f"<u>{html.escape(card)}</u>"


def source_username_only(source_user: str) -> str:
    match = re.search(r"@[A-Za-z0-9_]+", source_user)
    if match:
        return match.group(0)
    parts = [part.strip() for part in source_user.split("|") if part.strip()]
    return parts[0] if parts else source_user.strip() or "Unknown"


def format_reply(results: list[OcrResult]) -> str:
    pubg_occurrences: list[tuple[str, int]] = []
    psn_occurrences: list[tuple[str, str, int]] = []
    conflict_lines: list[str] = []
    expected_pubg_total = 0
    expected_psn_total = 0
    pubg_image_count = 0
    psn_image_count = 0
    uncertain_count = 0
    for index, result in enumerate(results, start=1):
        cards = exact_unique(list(result.cards))
        if result.psn_ordered:
            psn = [card for card in result.psn_ordered if not card.endswith(FUZZY_SUFFIX)]
            fuzzy_psn = [card for card in result.psn_ordered if card.endswith(FUZZY_SUFFIX)]
            ordered_psn = list(result.psn_ordered)
        else:
            psn = exact_unique_psn(list(result.psn_cards))
            fuzzy_psn = exact_unique_text(list(result.psn_uncertain))
            ordered_psn = psn + fuzzy_psn
        ordered_psn = limit_psn_ordered(ordered_psn, result.psn_expected_count)
        psn = [card for card in ordered_psn if not card.endswith(FUZZY_SUFFIX)]
        fuzzy_psn = [card for card in ordered_psn if card.endswith(FUZZY_SUFFIX)]
        if cards:
            pubg_image_count += 1
        if psn or fuzzy_psn:
            psn_image_count += 1
        pubg_occurrences.extend((card, index) for card in cards)
        for line in ordered_psn:
            key = psn_key(line)
            if not key:
                continue
            display = f"{key}{FUZZY_SUFFIX}" if line.endswith(FUZZY_SUFFIX) else key
            psn_occurrences.append((display, key, index))
        if result.pubg_expected_count:
            expected_pubg_total += result.pubg_expected_count
        if result.psn_expected_count:
            expected_psn_total += result.psn_expected_count
        if result.uncertain_count:
            conflict_lines.append(f"{result_location(index, result)}：{UNCERTAIN_PREFIX}{result.uncertain_count}{UNCERTAIN_SUFFIX}")
        uncertain_count += result.uncertain_count

    pubg_cards: list[str] = []
    seen_pubg: dict[str, int] = {}
    pubg_duplicate_groups: dict[int, list[int]] = {}
    for card, index in pubg_occurrences:
        if not valid_card(card):
            continue
        if card not in seen_pubg:
            seen_pubg[card] = index
            pubg_cards.append(card)
            continue
        pubg_duplicate_groups.setdefault(seen_pubg[card], []).append(index)

    psn_lines: list[str] = []
    seen_psn: dict[str, int] = {}
    psn_duplicate_groups: dict[int, list[int]] = {}
    for display, key, index in psn_occurrences:
        if key not in seen_psn:
            seen_psn[key] = index
            psn_lines.append(display)
            continue
        psn_duplicate_groups.setdefault(seen_psn[key], []).append(index)
    psn_cards = exact_unique_psn([card for card in psn_lines if not card.endswith(FUZZY_SUFFIX)])
    psn_uncertain = exact_unique_text([card for card in psn_lines if card.endswith(FUZZY_SUFFIX)])
    pubg_duplicate_lines = format_duplicate_lines(list(pubg_duplicate_groups.items()))
    psn_duplicate_lines = format_duplicate_lines(list(psn_duplicate_groups.items()))

    sections: list[str] = []
    if pubg_cards:
        pubg_summary = (
            f"<b>{SUCCESS_PREFIX}{PUBG_LABEL}：{len(pubg_cards)}{COUNT_SUFFIX}（点击卡密复制）</b>\n"
            f"\u672c\u6b21\u8bc6\u522bPUBG\u56fe\u7247\uff1a{pubg_image_count}\u5f20"
        )
        if expected_pubg_total and len(pubg_cards) < expected_pubg_total:
            pubg_summary += f"\n{MANUAL_REVIEW_SUMMARY}{PUBG_LABEL}{expected_pubg_total - len(pubg_cards)}{COUNT_SUFFIX}"
        if pubg_duplicate_lines:
            pubg_summary += "\n" + "\n".join(pubg_duplicate_lines)
        sections.append(f"<b>【{PUBG_LABEL}】</b>\n\n{format_card_codes(pubg_cards)}\n\n{pubg_summary}")

    if psn_lines:
        psn_summary = (
            f"<b>{SUCCESS_PREFIX}{PSN_LABEL}：{len(psn_cards)}{COUNT_SUFFIX}（点击卡密复制）</b>\n"
            f"\u672c\u6b21\u8bc6\u522bPSN\u56fe\u7247\uff1a{psn_image_count}\u5f20"
        )
        if psn_uncertain:
            psn_summary += f"\n{MANUAL_REVIEW_SUMMARY}{PSN_LABEL}{len(psn_uncertain)}{COUNT_SUFFIX}"
        if expected_psn_total and len(psn_lines) < expected_psn_total:
            psn_summary += f"\n{MANUAL_REVIEW_SUMMARY}{PSN_LABEL}{expected_psn_total - len(psn_lines)}{COUNT_SUFFIX}"
        if psn_duplicate_lines:
            psn_summary += "\n" + "\n".join(psn_duplicate_lines)
        sections.append(f"<b>【{PSN_LABEL}】</b>\n\n{format_card_codes(psn_lines)}\n\n{psn_summary}")

    if uncertain_count:
        if conflict_lines:
            sections.append(f"{UNCERTAIN_PREFIX}\n<pre>{html.escape(chr(10).join(conflict_lines))}</pre>\n{UNCERTAIN_PREFIX}{uncertain_count}{UNCERTAIN_SUFFIX}")
        else:
            sections.append(f"{UNCERTAIN_PREFIX}{uncertain_count}{UNCERTAIN_SUFFIX}")
    if not sections:
        sections.append("\u672a\u8bc6\u522b\u5230\u5361\u5bc6")
    return "\n\n".join(sections)


def result_card_lines(results: list[OcrResult]) -> tuple[list[str], list[str]]:
    pubg_cards: list[str] = []
    psn_lines: list[str] = []
    for result in results:
        pubg_cards.extend(card for card in exact_unique(list(result.cards)) if valid_card(card))
        if result.psn_ordered:
            ordered_psn = list(result.psn_ordered)
        else:
            ordered_psn = exact_unique_psn(list(result.psn_cards)) + exact_unique_text(list(result.psn_uncertain))
        ordered_psn = limit_psn_ordered(ordered_psn, result.psn_expected_count)
        for line in ordered_psn:
            key = psn_key(line)
            if not key:
                continue
            psn_lines.append(f"{key}{FUZZY_SUFFIX}" if line.endswith(FUZZY_SUFFIX) else key)
    return exact_unique(pubg_cards), unique_psn_lines(psn_lines)


def has_card_results(results: list[OcrResult]) -> bool:
    pubg_cards, psn_lines = result_card_lines(results)
    return bool(pubg_cards or psn_lines)


def extract_card_lines_from_text(text: str) -> tuple[list[str], list[str]]:
    pubg_cards = exact_unique(extract_cards(text))
    psn_lines = unique_psn_lines(extract_psn_ordered(text, force=True))
    return pubg_cards, [line for line in psn_lines if not line.endswith(FUZZY_SUFFIX)]


def ocr_text_keys(text: str) -> list[str]:
    normalized = normalize_text(text)
    compact = re.sub(r"[^A-Z0-9$]", "", normalized)
    keys: list[str] = []
    for match in re.finditer(r"[SP5$][A-Z0-9$]{10,25}", compact):
        keys.append(match.group(0))
    if len(compact) >= 10:
        keys.append(compact)
    return exact_unique_text(keys)


def card_type_for(card: str) -> str | None:
    if valid_card(card):
        return "PUBG"
    if valid_psn_card(card):
        return "PSN"
    return None


def apply_card_corrections(chat_id: int, result: OcrResult) -> OcrResult:
    corrected_cards: list[str] = []
    learned_pubg_cards: list[str] = []
    correction_applied = False
    learned_pubg_targets = exact_unique_text(
        [correction.correct_card for correction in ledger_store.list_ocr_text_corrections(chat_id) if correction.card_type == "PUBG"]
        + [correction.correct_card for correction in ledger_store.list_card_corrections(chat_id) if correction.card_type == "PUBG"]
    )
    for card in result.cards:
        corrected = ledger_store.get_card_correction(chat_id, "PUBG", card)
        if corrected and corrected != card:
            correction_applied = True
        if not corrected:
            learned_match = next((target for target in learned_pubg_targets if likely_learned_variant(card, target)), None)
            if learned_match and learned_match != card:
                corrected = learned_match
                correction_applied = True
                learned_pubg_cards.append(learned_match)
        corrected_cards.append(corrected or card)

    def correct_psn(line: str) -> str:
        nonlocal correction_applied
        key = psn_key(line)
        if not key:
            return line
        corrected = ledger_store.get_card_correction(chat_id, "PSN", key)
        if corrected and corrected != key:
            correction_applied = True
        return corrected or line

    corrected_psn_cards: list[str] = []
    for card in result.psn_cards:
        corrected = ledger_store.get_card_correction(chat_id, "PSN", card)
        if corrected and corrected != card:
            correction_applied = True
        corrected_psn_cards.append(corrected or card)
    corrected_psn_ordered = [correct_psn(line) for line in result.psn_ordered]
    corrected_psn_uncertain = [correct_psn(line) for line in result.psn_uncertain]
    raw_keys = set(ocr_text_keys(result.raw_text))
    for correction in ledger_store.list_ocr_text_corrections(chat_id):
        if correction.wrong_text not in raw_keys:
            continue
        correction_applied = True
        if correction.card_type == "PUBG":
            corrected_cards.append(correction.correct_card)
            learned_pubg_cards.append(correction.correct_card)
        elif correction.card_type == "PSN":
            corrected_psn_ordered.append(correction.correct_card)
    if learned_pubg_cards:
        corrected_cards = [
            card
            for card in corrected_cards
            if card in learned_pubg_cards
        ]
    return replace(
        result,
        cards=tuple(exact_unique(corrected_cards)),
        psn_cards=tuple(exact_unique_psn(corrected_psn_cards)),
        psn_ordered=tuple(unique_psn_lines(corrected_psn_ordered)),
        psn_uncertain=tuple(exact_unique_text(corrected_psn_uncertain)),
        uncertain_count=0 if correction_applied else result.uncertain_count,
    )


def learn_card_corrections_from_reply(update: Update) -> str | None:
    if not update.message or not update.effective_chat:
        return None
    reply_message = update.message.reply_to_message
    if not reply_message:
        return None
    correction_text = update.message.text or ""
    replied_text = reply_message.text or reply_message.caption or ""
    if not correction_text or not replied_text:
        return None
    wrong_pubg, wrong_psn = extract_card_lines_from_text(replied_text)
    correct_pubg, correct_psn = extract_card_lines_from_text(correction_text)
    source_user = user_label(update)
    learned_lines: list[str] = []

    def learn_pairs(card_type: str, wrong_cards: list[str], correct_cards: list[str]) -> None:
        if not wrong_cards or not correct_cards or len(wrong_cards) != len(correct_cards):
            return
        for wrong_card, correct_card in zip(wrong_cards, correct_cards):
            if wrong_card == correct_card:
                continue
            ledger_store.set_card_correction(
                update.effective_chat.id,
                card_type,
                wrong_card,
                correct_card,
                source_user,
            )
            learned_lines.append(f"{card_type} {wrong_card} -> {correct_card}")

    learn_pairs("PUBG", wrong_pubg, correct_pubg)
    learn_pairs("PSN", wrong_psn, correct_psn)
    if not learned_lines:
        return None
    return "已学习纠错\n" + "\n".join(learned_lines)


def card_text_result(text: str) -> OcrResult | None:
    pubg_cards, psn_lines = extract_card_lines_from_text(text)
    if not pubg_cards and not psn_lines:
        return None
    return OcrResult(cards=tuple(pubg_cards), psn_ordered=tuple(psn_lines))


def unlearnable_correction_feedback(update: Update) -> str | None:
    if not update.message:
        return None
    reply_message = update.message.reply_to_message
    if not reply_message:
        return None
    correction_result = card_text_result(update.message.text or "")
    if correction_result is None:
        return None
    replied_text = reply_message.text or reply_message.caption or ""
    wrong_pubg, wrong_psn = extract_card_lines_from_text(replied_text)
    if wrong_pubg or wrong_psn:
        return None
    return (
        "已收到正确卡密，但原回复里没有错误卡密，不能建立纠错映射。\n"
        "以后如果机器人把卡密识别错了，请回复那条包含错误卡密的结果，再发送正确卡密。"
    )


async def learn_ocr_sample_from_replied_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not update.message or not update.effective_chat:
        return None
    reply_message = update.message.reply_to_message
    if not reply_message or not getattr(reply_message, "photo", None):
        return None
    correct_result = card_text_result(update.message.text or "")
    if correct_result is None:
        return None
    correct_pubg, correct_psn = result_card_lines([correct_result])
    correct_cards = [("PUBG", card) for card in correct_pubg] + [("PSN", card) for card in correct_psn]
    if not correct_cards:
        return None

    image_path = await download_message_photo(reply_message, context)
    try:
        result = await asyncio.to_thread(run_ocr, image_path)
    finally:
        try:
            image_path.unlink(missing_ok=True)
            image_path.parent.rmdir()
        except OSError:
            pass

    keys = ocr_text_keys(result.raw_text)
    if not keys:
        return "没有从这张图读到可学习的文字特征，请换更清晰的原图再回复正确卡密。"

    source_user = user_label(update)
    learned_lines: list[str] = []
    for card_type, correct_card in correct_cards:
        for key in keys[:8]:
            ledger_store.set_ocr_text_correction(
                update.effective_chat.id,
                card_type,
                key,
                correct_card,
                source_user,
            )
        learned_lines.append(f"{card_type} {correct_card}")
    return "已学习这张图片的OCR特征\n" + "\n".join(learned_lines)


def card_history_day_key(chat_id: int, now: datetime | None = None) -> str:
    reset_hour = ledger_store.get_ledger_reset_hour(chat_id)
    local_now = (now or datetime.now(LEDGER_TZ)).astimezone(LEDGER_TZ)
    day = local_now.date()
    if local_now.hour < reset_hour:
        day -= timedelta(days=1)
    return day.isoformat()


def format_history_time(created_at: str) -> str:
    parsed = datetime.fromisoformat(created_at)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LEDGER_TZ).strftime("%H:%M:%S")


def register_card_history(updates: list[Update], results: list[OcrResult]) -> list[CardHistoryDuplicate]:
    if not updates:
        return []
    chat = updates[-1].effective_chat
    if not chat:
        return []
    chat_id = chat.id
    day_key = card_history_day_key(chat_id)
    ledger_store.clear_recognized_cards_before(day_key)
    duplicates: list[CardHistoryDuplicate] = []
    seen_reported: set[tuple[str, str]] = set()
    for update, result in zip(updates, results):
        source_user = user_label(update)
        source_message_id = update.message.message_id if update.message else None
        pubg_cards, psn_lines = result_card_lines([result])
        for card_type, cards in (("PUBG", pubg_cards), ("PSN", [card for card in psn_lines if not card.endswith(FUZZY_SUFFIX)])):
            for card in cards:
                record = ledger_store.record_recognized_card(
                    chat_id=chat_id,
                    card_type=card_type,
                    card=card,
                    day_key=day_key,
                    source_user=source_user,
                    source_message_id=source_message_id,
                )
                key = (card_type, card)
                if record is None or key in seen_reported:
                    continue
                seen_reported.add(key)
                duplicates.append(
                    CardHistoryDuplicate(
                        card_type=card_type,
                        card=card,
                        first_seen_at=record.created_at,
                        first_source_user=record.source_user,
                    )
                )
    return duplicates


def append_history_duplicates(reply: str, duplicates: list[CardHistoryDuplicate]) -> str:
    if not duplicates:
        return reply
    lines = ["<b>今日重复出现卡密</b>"]
    for duplicate in duplicates:
        source_user = html.escape(source_username_only(duplicate.first_source_user))
        lines.extend(
            [
                f"{duplicate.card_type}：{format_underlined_card_code(duplicate.card)}",
                "已出现过",
                f"首次 {format_history_time(duplicate.first_seen_at)} 来自 | {source_user} |",
            ]
        )
    return reply + "\n\n" + "\n".join(lines)


def format_cards_only(results: list[OcrResult]) -> str:
    pubg_cards, psn_lines = result_card_lines(results)
    sections: list[str] = []
    if pubg_cards:
        sections.append(f"<b>【{PUBG_LABEL}】</b>\n\n{format_card_codes(pubg_cards)}")
    if psn_lines:
        sections.append(f"<b>【{PSN_LABEL}】</b>\n\n{format_card_codes(psn_lines)}")
    if not sections:
        sections.append("\u672a\u8bc6\u522b\u5230\u5361\u5bc6")
    return "\n\n".join(sections)


CALC_RE = re.compile(r"^[\d\s+\-*/().xX×÷]+$")
CALC_HAS_OPERATOR_RE = re.compile(r"[\d)]\s*[+\-*/xX×÷]\s*[\d(]")


def calculate_expression(text: str) -> str | None:
    expression = normalize_calc_expression(text)
    if not expression or not CALC_RE.fullmatch(expression) or not CALC_HAS_OPERATOR_RE.search(expression):
        return None
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval_calc_node(tree.body)
    except (SyntaxError, ValueError, InvalidOperation, DivisionByZero, OverflowError):
        return None
    return _format_calc_result(value)


def normalize_calc_expression(text: str) -> str:
    return (
        text.strip()
        .translate(FULLWIDTH_MAP)
        .replace("＋", "+")
        .replace("－", "-")
        .replace("＊", "*")
        .replace("／", "/")
        .replace("（", "(")
        .replace("）", ")")
        .replace("×", "*")
        .replace("x", "*")
        .replace("X", "*")
        .replace("÷", "/")
    )


def _eval_calc_node(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_calc_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _eval_calc_node(node.left)
        right = _eval_calc_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise DivisionByZero
        return left / right
    raise ValueError("unsupported expression")


def _format_calc_result(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized.quantize(Decimal("1")), "f")
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".")


TRC20_ADDRESS_RE = re.compile(r"(?<![A-Za-z0-9])T[1-9A-HJ-NP-Za-km-z]{33}(?![A-Za-z0-9])")


def extract_trc20_address(text: str) -> str | None:
    match = TRC20_ADDRESS_RE.search(text.strip())
    return match.group(0) if match else None


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _center_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.ImageFont, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2 - 2
    draw.text((x, y), text, font=font, fill=fill)


def make_trc20_verify_image(address: str, created_at: datetime | None = None) -> BytesIO:
    created_at = created_at or datetime.now(LEDGER_TZ)
    timestamp = created_at.astimezone(LEDGER_TZ).strftime("%Y-%m-%d %H:%M:%S")
    width, height = 860, 300
    image = Image.new("RGB", (width, height), "#0aa77c")
    draw = ImageDraw.Draw(image)

    title_font = _font(40, bold=True)
    subtitle_font = _font(20)
    address_font = _font(34, bold=True)
    time_font = _font(20)

    _center_text(draw, (0, 34, width, 80), "USDT防篡改验证核对", title_font, "#fff238")
    _center_text(draw, (0, 78, width, 112), "（请双方谨慎核对地址是否与图中一致，如有误停止付款）", subtitle_font, "#003b30")

    bar = (34, 128, width - 34, 200)
    draw.rounded_rectangle(bar, radius=4, fill="#e87700")
    _center_text(draw, bar, address, address_font, "#ffffff")

    draw.rounded_rectangle((34, 222, width - 34, 268), radius=4, fill="#08936e")
    _center_text(draw, (34, 222, width - 34, 268), f"生成时间：{timestamp}", time_font, "#ffffff")

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    output.name = "trc20-verify.png"
    return output


async def reply_trc20_verify_image(message, address: str) -> None:
    image = make_trc20_verify_image(address)
    await message.reply_photo(photo=image, caption=address)


def parse_okx_c2c_usdt_cny_prices(payload: dict, limit: int = 5) -> list[Decimal]:
    sell_orders = payload.get("data", {}).get("sell", [])
    if not sell_orders:
        raise ValueError("empty OKX C2C sell order book")
    prices: list[Decimal] = []
    for order in sell_orders:
        price = order.get("price")
        if price is None:
            continue
        prices.append(Decimal(str(price)))
        if len(prices) >= limit:
            break
    if not prices:
        raise ValueError("missing OKX C2C prices")
    return prices


def parse_okx_exchange_rate_price(payload: dict) -> Decimal:
    data = payload.get("data", [])
    if not data:
        raise ValueError("empty OKX exchange-rate data")
    price = data[0].get("usdCny")
    if price is None:
        raise ValueError("missing OKX usdCny")
    return Decimal(str(price))


def format_okx_prices(prices: list[Decimal], source: str) -> str:
    lines = ["欧意USDT/CNY 最新5档"]
    lines.extend(f"{index}. {_format_calc_result(price)}" for index, price in enumerate(prices, start=1))
    lines.append(f"来源：{source}")
    return "\n".join(lines)


def is_price_command(text: str) -> bool:
    normalized = text.strip()
    lowered = normalized.lower()
    return normalized == "币价" or lowered in {"bj", "z0"} or normalized == "/price"


async def fetch_okx_usdt_cny_prices() -> tuple[list[Decimal], str]:
    async with httpx.AsyncClient(timeout=15, headers=OKX_HTTP_HEADERS) as client:
        try:
            response = await client.get(OKX_C2C_USDT_CNY_URL)
            response.raise_for_status()
            return parse_okx_c2c_usdt_cny_prices(response.json(), limit=5), "OKX C2C卖单"
        except Exception:
            logger.exception("OKX C2C USDT/CNY price fetch failed, falling back to exchange-rate")
        response = await client.get(OKX_EXCHANGE_RATE_URL)
        response.raise_for_status()
        return [parse_okx_exchange_rate_price(response.json())], "OKX官方USD/CNY汇率"


async def reply_okx_price(message) -> None:
    try:
        prices, source = await fetch_okx_usdt_cny_prices()
    except Exception:
        logger.exception("OKX USDT/CNY price fetch failed")
        await message.reply_text("币价获取失败，请稍后再试。")
        return
    await message.reply_text(format_okx_prices(prices, source))


def start_help_text() -> str:
    return (
        "<b>卡密识别记账助手</b>\n\n"
        "<b>卡密识别</b>\n"
        "发送 PUBG/PSN 卡密图片，机器人会自动识别并输出卡密；重复卡密会提示首次出现时间和来源。\n\n"
        "<b>记账功能</b>\n"
        "发送 <code>+100</code>、<code>-100</code> 记账；支持账单、清账、暂停/开启、日切、设置汇率、计算表达式。\n\n"
        "<b>价格查询</b>\n"
        "发送 <code>币价</code>、<code>bj</code> 或 <code>z0</code> 查看 OKX USDT/CNY 最新 5 档价格。\n\n"
        "<b>地址防篡改</b>\n"
        "发送 USDT-TRC20 地址，会生成带时间的防篡改核对图片。\n\n"
        "<b>TRX 能量租赁</b>\n"
        "点击下方 <b>能量租赁</b> 查看下单地址；点击 <b>笔数套餐</b> 按地址和笔数生成订单。\n\n"
        "把机器人拉进群后，群里可以直接使用卡密识别、记账和能量租赁功能。"
    )


def add_group_keyboard(bot_username: str) -> InlineKeyboardMarkup:
    add_group_url = f"https://t.me/{bot_username}?startgroup=true" if bot_username else "https://t.me/"
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("➕ 拉机器人进群", url=add_group_url)]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            start_help_text(),
            reply_markup=trx_main_menu_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )


async def handle_add_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    bot_user = await context.bot.get_me()
    await update.message.reply_text(
        "🤖 点击下方按钮拉机器人进群。",
        reply_markup=add_group_keyboard(bot_user.username or ""),
    )


async def handle_ledger_add_group_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    remember_ledger_user(update)
    ensure_private_ledger_owner(update)
    bot_user = await context.bot.get_me()
    await update.message.reply_text(
        "🤖 点击下方按钮拉机器人进群，群里可直接记账。",
        reply_markup=add_group_keyboard(bot_user.username or ""),
    )


async def handle_ledger_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    remember_ledger_user(update)
    ensure_private_ledger_owner(update)
    await reply_ledger(update.message, ledger_commands.HELP_TEXT)


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(str(update.message.chat_id))


async def show_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(BOT_VERSION)


def ledger_owner_ids(chat_id: int | None = None) -> set[int]:
    if chat_id is not None:
        chat_owner_id = ledger_store.get_chat_owner_id(chat_id)
        if chat_owner_id is not None:
            return {chat_owner_id}
    owner_id = parse_chat_id(OWNER_CHAT_ID)
    return {owner_id} if owner_id is not None else set()


def ledger_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("昨日账单", callback_data="ledger:yesterday"),
                InlineKeyboardButton("今日账单", callback_data="ledger:today"),
            ],
            [
                InlineKeyboardButton("完整账单", callback_data="ledger:full"),
                InlineKeyboardButton("使用说明", callback_data="ledger:help"),
            ],
        ]
    )


def ledger_actor(update: Update) -> LedgerActor:
    user = update.effective_user
    if not user:
        return LedgerActor(user_id=0, username="", display_name="")
    display_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return LedgerActor(user_id=user.id, username=user.username or "", display_name=display_name)


def remember_ledger_user(update: Update) -> None:
    if not update.effective_chat or not update.effective_user:
        return
    actor = ledger_actor(update)
    ledger_store.remember_user(
        update.effective_chat.id,
        actor.user_id,
        actor.username,
        actor.display_name,
    )


def ensure_private_ledger_owner(update: Update) -> None:
    if not update.effective_chat or not update.effective_user:
        return
    if getattr(update.effective_chat, "type", "") == "private":
        ledger_store.set_chat_owner(update.effective_chat.id, update.effective_user.id)


def ledger_actor_from_message(message) -> LedgerActor | None:
    user = getattr(message, "from_user", None)
    if not user:
        return None
    display_name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return LedgerActor(user_id=user.id, username=user.username or "", display_name=display_name)


async def reply_ledger(message, text: str) -> None:
    await message.reply_text(
        text,
        reply_markup=ledger_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def handle_ledger_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    remember_ledger_user(update)
    ensure_private_ledger_owner(update)
    learned = learn_card_corrections_from_reply(update)
    if learned:
        await update.message.reply_text(learned)
        return
    learned_sample = await learn_ocr_sample_from_replied_photo(update, context)
    if learned_sample:
        await update.message.reply_text(learned_sample)
        return
    correction_feedback = unlearnable_correction_feedback(update)
    if correction_feedback:
        await update.message.reply_text(correction_feedback)
        return
    trc20_address = extract_trc20_address(update.message.text or "")
    if trc20_address:
        await reply_trc20_verify_image(update.message, trc20_address)
        return
    if is_price_command(update.message.text or ""):
        await reply_okx_price(update.message)
        return
    calculation = calculate_expression(update.message.text or "")
    if calculation is not None:
        await update.message.reply_text(calculation)
        return
    text_result = card_text_result(update.message.text or "")
    if text_result is not None:
        corrected_result = apply_card_corrections(update.effective_chat.id, text_result)
        history_duplicates = register_card_history([update], [corrected_result])
        await update.message.reply_text(
            append_history_duplicates(format_reply([corrected_result]), history_duplicates),
            parse_mode=ParseMode.HTML,
        )
        return
    reply_message = update.message.reply_to_message
    reply_user = ledger_actor_from_message(reply_message) if reply_message else None
    reply_text = None
    reply_message_id = None
    if reply_message:
        reply_text = reply_message.text or reply_message.caption
        reply_message_id = reply_message.message_id

    result = handle_ledger_command_text(
        store=ledger_store,
        chat_id=update.effective_chat.id,
        actor=ledger_actor(update),
        text=update.message.text or "",
        owner_ids=ledger_owner_ids(update.effective_chat.id),
        reply_user=reply_user,
        reply_text=reply_text,
        message_id=update.message.message_id,
        reply_message_id=reply_message_id,
    )
    if result:
        await reply_ledger(update.message, result.text)


async def handle_ledger_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    text = LEDGER_CALLBACK_TEXT.get(query.data or "")
    await query.answer()
    if not text:
        return
    result = handle_ledger_command_text(
        store=ledger_store,
        chat_id=query.message.chat_id,
        actor=LedgerActor(
            user_id=query.from_user.id,
            username=query.from_user.username or "",
            display_name=" ".join(part for part in [query.from_user.first_name, query.from_user.last_name] if part),
        ),
        text=text,
        owner_ids=ledger_owner_ids(query.message.chat_id),
    )
    if result:
        await reply_ledger(query.message, result.text)


async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    bot_user = await context.bot.get_me()
    for member in update.message.new_chat_members or []:
        if member.id == bot_user.id:
            ledger_store.set_chat_owner(update.effective_chat.id, update.effective_user.id)
            logger.info(
                "Set ledger owner for chat %s to inviter %s.",
                update.effective_chat.id,
                update.effective_user.id,
            )
            break


def user_label(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Unknown user"
    parts = [str(user.id)]
    if user.username:
        parts.append(f"@{user.username}")
    name = " ".join(part for part in [user.first_name, user.last_name] if part)
    if name:
        parts.append(name)
    return " | ".join(parts)


def chat_label(update: Update | None) -> str:
    chat = update.effective_chat if update else None
    if not chat:
        return "未知"
    chat_type = getattr(chat, "type", "")
    if chat_type == "private":
        return "私聊"
    title = getattr(chat, "title", "") or getattr(chat, "full_name", "") or "未命名群组"
    return f"群组（{title}）"


def audit_source_text(update: Update | None) -> str:
    if not update:
        return "来源: Unknown\n发送用户: Unknown"
    return f"来源: {html.escape(chat_label(update))}\n发送用户: {html.escape(user_label(update))}"


def parse_chat_id(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def update_is_from_owner(update: Update | None) -> bool:
    owner_id = parse_chat_id(OWNER_CHAT_ID)
    if owner_id is None or not update:
        return False
    if update.effective_user and update.effective_user.id == owner_id:
        return True
    return bool(update.effective_chat and update.effective_chat.id == owner_id)


def update_is_private_chat(update: Update | None) -> bool:
    if not update or not update.effective_chat:
        return False
    return getattr(update.effective_chat, "type", "") == "private"


def should_send_audit(updates: list[Update]) -> bool:
    first = updates[0] if updates else None
    if update_is_from_owner(first) and update_is_private_chat(first):
        return False
    return bool(AUDIT_BOT_TOKEN or AUDIT_CHAT_ID or OWNER_CHAT_ID)


def should_reply_to_source(updates: list[Update]) -> bool:
    return True


def format_source_reply(
    updates: list[Update],
    results: list[OcrResult],
    history_duplicates: list[CardHistoryDuplicate] | None = None,
) -> str:
    return append_history_duplicates(format_reply(results), history_duplicates or [])


async def notify_owner(
    updates: list[Update],
    results: list[OcrResult],
    context: ContextTypes.DEFAULT_TYPE,
    history_duplicates: list[CardHistoryDuplicate] | None = None,
) -> None:
    if not should_send_audit(updates):
        return
    first = updates[0] if updates else None
    target_chat_id = AUDIT_CHAT_ID or OWNER_CHAT_ID
    if not target_chat_id:
        return
    target_chat_id_int = parse_chat_id(target_chat_id)
    if target_chat_id_int is None:
        return
    if not AUDIT_BOT_TOKEN and first and first.effective_chat and first.effective_chat.id == target_chat_id_int:
        return
    text = audit_source_text(first) + "\n\n" + append_history_duplicates(format_reply(results), history_duplicates or [])
    if AUDIT_BOT_TOKEN:
        try:
            await send_audit_bot_message(target_chat_id_int, text)
        except Exception:
            logger.exception("Audit bot forwarding failed")
        return
    await context.bot.send_message(chat_id=target_chat_id_int, text=text, parse_mode=ParseMode.HTML)


async def send_audit_bot_message(chat_id: int, text: str) -> None:
    url = f"https://api.telegram.org/bot{AUDIT_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=TELEGRAM_TIMEOUT) as client:
        response = await client.post(
            url,
            data={
                "chat_id": str(chat_id),
                "text": text,
                "parse_mode": ParseMode.HTML,
                "disable_web_page_preview": "true",
            },
        )
        response.raise_for_status()


async def flush_chat_batch(chat_id: int, context: ContextTypes.DEFAULT_TYPE, wait_seconds: float) -> None:
    await asyncio.sleep(wait_seconds)
    updates = chat_buffers.pop(chat_id, [])
    chat_tasks.pop(chat_id, None)
    if not updates:
        return
    message = updates[-1].message
    if not message:
        return

    await message.chat.send_action("typing")
    results: list[OcrResult] = []
    for update in updates:
        try:
            result = await recognize_update(update, context)
            corrected = apply_card_corrections(chat_id, result)
            corrected_pubg, corrected_psn = result_card_lines([corrected])
            if not corrected_pubg and not corrected_psn and result.raw_text.strip():
                logger.info("Unrecognized OCR raw text: %s", result.raw_text.strip().replace("\n", " | ")[:1000])
            results.append(corrected)
        except Exception:
            logger.exception("Batch image OCR failed")
            results.append(OcrResult(cards=tuple()))

    if not has_card_results(results):
        return

    history_duplicates = register_card_history(updates, results)
    if should_reply_to_source(updates):
        await message.reply_text(
            format_source_reply(updates, results, history_duplicates),
            parse_mode=ParseMode.HTML,
        )
    await notify_owner(updates, results, context, history_duplicates)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    remember_ledger_user(update)
    chat_id = update.message.chat_id
    chat_buffers[chat_id].append(update)
    old_task = chat_tasks.get(chat_id)
    if old_task and not old_task.done():
        old_task.cancel()
    wait_seconds = MULTI_BATCH_WAIT_SECONDS if len(chat_buffers[chat_id]) > 1 else SINGLE_WAIT_SECONDS
    chat_tasks[chat_id] = asyncio.create_task(flush_chat_batch(chat_id, context, wait_seconds))


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("Please set BOT_TOKEN in .env first")
    init_trx_db()

    request_kwargs = {
        "connect_timeout": TELEGRAM_TIMEOUT,
        "read_timeout": TELEGRAM_TIMEOUT,
        "write_timeout": TELEGRAM_TIMEOUT,
        "pool_timeout": TELEGRAM_TIMEOUT,
    }
    if PROXY_URL:
        request_kwargs["proxy_url"] = PROXY_URL

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(HTTPXRequest(**request_kwargs))
        .get_updates_request(HTTPXRequest(**request_kwargs))
        .post_init(start_background_tasks)
        .post_shutdown(stop_background_tasks)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", show_id))
    app.add_handler(CommandHandler("version", show_version))
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({re.escape(TEXT_LEDGER_ADD_GROUP)}|记账拉机器人进群)$"),
            handle_ledger_add_group_menu,
        )
    )
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(TEXT_LEDGER)}$"), handle_ledger_menu))
    app.add_handler(MessageHandler(filters.Regex(f"^{re.escape(TEXT_ADD_GROUP)}$"), handle_add_group_menu))
    app.add_handler(build_trx_conversation_handler())
    for handler in build_trx_admin_handlers():
        app.add_handler(handler)
    app.add_handler(
        CommandHandler(
            ["help", "bill", "fullbill", "yesterday", "undo", "clear", "in", "income", "out", "payout"],
            handle_ledger_text,
        )
    )
    app.add_handler(CallbackQueryHandler(handle_ledger_callback, pattern=r"^ledger:"))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_chat_members))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ledger_text))
    logger.info("Bot is starting. Version=%s.", BOT_VERSION)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

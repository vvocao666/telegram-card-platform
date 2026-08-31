from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal  # noqa: F401 - compatibility export
from pathlib import Path

import httpx  # noqa: F401 - compatibility export for provider client injection
import pytesseract
from dotenv import load_dotenv
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationHandlerStop, ContextTypes, filters  # noqa: F401 - compatibility export

from config.constants import BOT_VERSION, TEXT_ADD_GROUP, TEXT_LEDGER, TEXT_LEDGER_ADD_GROUP  # noqa: F401 - compatibility exports
from handlers.start_handler import (
    add_group_keyboard,
    handle_add_group_menu,  # noqa: F401 - compatibility export
    main_menu_keyboard,  # noqa: F401 - compatibility export
    start,  # noqa: F401 - compatibility export
    start_help_text,  # noqa: F401 - compatibility export
)
from services.calculator import (
    calculate_expression,
    format_calc_result as _format_calc_result,
    normalize_calc_expression,  # noqa: F401 - compatibility export
)
from services.ledger import ledger_commands
from services.ledger.ledger_commands import Actor as LedgerActor
from services.ledger.ledger_commands import handle_text as handle_ledger_command_text
from services.ledger.message_identity import actor_from_message as ledger_actor_from_message
from services.price.price_service import (
    fetch_okx_usdt_cny_prices,
    format_okx_prices,
    is_price_command,
    is_realtime_rate_command,
    parse_okx_c2c_usdt_cny_prices,  # noqa: F401 - compatibility export
    parse_okx_exchange_rate_price,  # noqa: F401 - compatibility export
)
from services.ocr.candidate_audit import append_candidate_audit, build_candidate_audit
from services.ocr import command_service as ocr_command_service
from services.ocr.batch_processor import (
    LiveOcrBatchProgress as BaseLiveOcrBatchProgress,
    OcrBatchProgress as BaseOcrBatchProgress,
    OcrBatchJobPool,
    batch_debounce_seconds,
    order_batch_results,
    order_batch_updates,
)
from services.ocr.pubg_prefix_consensus import recover_single_prefix_digit_error  # noqa: F401 - provider compatibility export
from services.ocr.prefix_recovery_policy import requires_cloud_confirmation
from services.ocr.remote_variant_policy import (  # noqa: F401 - provider compatibility export
    remote_variant_evidence,
    remote_variants_conflict,
)
from services.ocr.thin_strip_policy import choose_thin_strip_result, is_thin_strip_image  # noqa: F401 - provider compatibility exports
from services.ocr.correction_engine import apply_corrections
from services.ocr.admin_commands import (
    export_font_templates,
    format_font_stats as format_ocr_font_stats_plus,
    format_ocr_review,
    format_ocr_version,
    import_font_templates,
)
from services.ocr.debug_commands import ocr_candidates as format_ocr_candidates_debug
from services.ocr.debug_commands import ocr_debug as format_ocr_debug
from services.ocr.font_repository import FontRepository
from services.ocr.http_client_pool import (
    close_ocrspace_http_client,
    close_remote_http_client,
    get_ocrspace_http_client,  # noqa: F401 - provider compatibility export
    get_remote_http_client,
)
from services.ocr.ocrspace_provider import recognize_ocrspace
from services.ocr.learning_commands import build_learning_preview, execute_learning, format_learning_stats
from services.ocr.manual_review import ManualReviewNotifier
from services.ocr.enhancement_flags import load_local_hybrid_flags
from services.ocr.remote_execution_gate import RemoteExecutionGate
from services.ocr.correction_service import (
    apply_card_corrections as preserve_one_time_card_result,
    learn_card_corrections_from_reply,  # noqa: F401 - compatibility export
    learn_ocr_sample_from_replied_photo,  # noqa: F401 - compatibility export
)
from services.ocr.pubg_char_correction import apply_pubg_char_corrections
from services.ocr.pubg_candidate_merge import incomplete_pubg_prefix_keys, merge_text_and_worker_pubg_cards
from services.ocr.provider_router import (
    average_latency_ms as provider_average_latency_ms,
    circuit_is_open as provider_circuit_is_open,
    circuit_reason as provider_circuit_reason,
    current_provider as provider_current_provider,
    ensure_daily_counters,
    fallback_reason as provider_fallback_reason,
    percent_rate as provider_percent_rate,
    safe_remote_url as provider_safe_remote_url,
)
from services.ocr.provider_orchestration import route_ocr
from services.ocr.remote_provider import recognize_remote
from services.ocr.result_pipeline import (
    ResultPipelineHooks,
    count_unique_pubg_markers,
    format_reply as pipeline_format_reply,
    ordered_psn_occurrences as pipeline_ordered_psn_occurrences,
    ordered_pubg_occurrences as pipeline_ordered_pubg_occurrences,
    result_card_lines as pipeline_result_card_lines,
)
from services.ocr.today_cache import append_today_ocr_cache, today_ocr_cache_summary
from services.ocr.daily_stats_report import daily_ocr_stats_loop
from services.ocr.history_service import (
    CardHistoryDuplicate,
    CardHistoryHooks,
    append_history_duplicates as append_history_duplicates_service,
    card_history_day_key as card_history_day_key_service,
    format_history_time as format_history_time_service,
    register_card_history as register_card_history_service,
    source_username_only as source_username_only_service,
)
from services.background_tasks import (
    periodic_cleanup_loop,
    start_managed_background_tasks,
    stop_managed_background_tasks,
)
from services.broadcast.broadcast_service import BroadcastController
from services.file_cleanup import cleanup_server_file_records
from services.forward.audit_service import (
    audit_photo_file_ids,  # noqa: F401 - compatibility export
    audit_source_text,
    resolve_audit_source_text,
    chat_label,  # noqa: F401 - compatibility export
    cleanup_audit_photo_paths,
    download_audit_photo_paths,
    send_audit_bot_message as _send_audit_bot_message,
    send_audit_bot_photos as _send_audit_bot_photos,
    update_is_private_chat,
    user_label,
)
from services.group.group_service import (
    CLASS_OFF_NOTICE,
    CLASS_ON_NOTICE,
    group_welcome_message,
    parse_class_mode_command as _class_mode_command,
)
from services.group.lifecycle_service import (
    GroupLifecycleHooks,
    handle_bot_chat_member as handle_bot_chat_member_service,
    handle_left_chat_member as handle_left_chat_member_service,
    handle_new_chat_members as handle_new_chat_members_service,
)
from services.notify.notify_service import (
    NotifyController,
    chunked as notify_chunked,
    extract_notify_all_text as notify_extract_all_text,
    html_mention_for_member as notify_html_mention,
)
from services.trc20.verify_service import (
    extract_trc20_address,
    make_trc20_verify_image,  # noqa: F401 - compatibility export
    reply_trc20_verify_image,
)
from services.status.system_info import (
    git_output,
    process_memory_mb,
    process_uptime_text as _process_uptime_text,
    service_active_state,
)
from services.status.status_service import StatusPanelSnapshot, render_status_panel  # noqa: F401 - compatibility exports
from services.status.panel_builder import StatusPanelHooks, build_status_panel as build_status_panel_service
from services.status.remote_metrics import record_remote_ocr_status as record_remote_ocr_status_service
from services.ledger.telegram_service import LedgerTextHooks, handle_ledger_text as handle_ledger_text_service
from utils.text_utils import split_html_message  # noqa: F401 - compatibility export
from utils.permission_utils import parse_chat_id, update_user_is_owner, update_user_or_chat_is_owner
from utils.telegram_utils import reply_html_chunks, send_html_chunks
from services.ocr.audit_cache import (
    DEFAULT_AUDIT_ROOT,
    cleanup_expired_audits,
    finalize_ocr_audit,
    mark_ocr_audit_failed,
    stage_ocr_audit_image,
)
from services.ocr.validator import validate_candidate
from services.ocr.duplicate_detector import canonical_card
from services.ocr.photo_rate_limiter import (
    batch_capacity_reached,
    check_photo_rate_limit,
    photo_rate_chat,  # noqa: F401 - compatibility export
    photo_rate_user,  # noqa: F401 - compatibility export
    photo_rate_warned_at,  # noqa: F401 - compatibility export
    warn_photo_rate_limited as _warn_photo_rate_limited,
)
from services.ocr.photo_sequence import (
    assign_photo_sequence,
    forget_photo_sequences,
    photo_display_order,
    photo_sequence,  # noqa: F401 - compatibility export
    photo_sequence_by_update,  # noqa: F401 - compatibility export used by ordering tests
)
from services.card_manager.collector import persist_ocr_batch
from services.card_manager.image_cache import CachedOriginalImage, cache_original_image, cleanup_expired_card_images
from storage.repositories.card_manager_storage import CardManagerStore
from storage.repositories.ledger_storage import LedgerStore


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID", "").strip()
AUDIT_BOT_TOKEN = os.getenv("AUDIT_BOT_TOKEN", "").strip()
AUDIT_CHAT_ID = os.getenv("AUDIT_CHAT_ID", "").strip()
SINGLE_WAIT_SECONDS = float(os.getenv("SINGLE_WAIT_SECONDS", os.getenv("BATCH_WAIT_SECONDS", "0.6")))
MULTI_BATCH_WAIT_SECONDS = max(
    float(os.getenv("MULTI_BATCH_WAIT_SECONDS", os.getenv("BATCH_WAIT_SECONDS", "3.0"))),
    2.0,
)
OWNER_FORWARD_BATCH_WAIT_SECONDS = max(float(os.getenv("OWNER_FORWARD_BATCH_WAIT_SECONDS", "12.0")), 3.0)
OCR_PROVIDER = os.getenv("OCR_PROVIDER", "ocrspace").strip().lower()
REMOTE_OCR_ENABLED = os.getenv("REMOTE_OCR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
REMOTE_OCR_URL = os.getenv("REMOTE_OCR_URL", "").strip().rstrip("/")
REMOTE_OCR_LABEL = os.getenv("REMOTE_OCR_LABEL", "本地 GPU OCR").strip() or "本地 GPU OCR"
REMOTE_OCR_TRUST_CARDS = os.getenv("REMOTE_OCR_TRUST_CARDS", "false").strip().lower() in {"1", "true", "yes", "on"}
REMOTE_OCR_USE_CARDS_FALLBACK = os.getenv("REMOTE_OCR_USE_CARDS_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}
REMOTE_OCR_COMPLEMENT = os.getenv("REMOTE_OCR_COMPLEMENT", "false").strip().lower() in {"1", "true", "yes", "on"}
REMOTE_OCR_TIMEOUT = float(os.getenv("REMOTE_OCR_TIMEOUT", "45"))
REMOTE_OCR_CONNECT_TIMEOUT = float(os.getenv("REMOTE_OCR_CONNECT_TIMEOUT", "1.5"))
REMOTE_OCR_HEALTH_CACHE_SECONDS = float(os.getenv("REMOTE_OCR_HEALTH_CACHE_SECONDS", "10"))
REMOTE_OCR_OFFLINE_SECONDS = max(5, int(float(os.getenv("REMOTE_OCR_OFFLINE_SECONDS", "180"))))
REMOTE_OCR_PROBE_SECONDS = max(5, int(float(os.getenv("REMOTE_OCR_PROBE_SECONDS", "60"))))
LOCAL_HYBRID_FLAGS = load_local_hybrid_flags()
REMOTE_OCR_MAX_IN_FLIGHT = max(1, int(os.getenv("REMOTE_OCR_MAX_IN_FLIGHT", "20")))
REMOTE_OCR_BUSY_WAIT_SECONDS = max(0.0, float(os.getenv("REMOTE_OCR_BUSY_WAIT_SECONDS", "45")))
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "").strip()
OCR_SPACE_API_KEYS_RAW = os.getenv("OCR_SPACE_API_KEYS", "").strip()
OCR_SPACE_MAX_SIDE = int(os.getenv("OCR_SPACE_MAX_SIDE", "3000"))
OCR_SPACE_MIN_SIDE = int(os.getenv("OCR_SPACE_MIN_SIDE", "2600"))
OCR_SPACE_MAX_UPLOAD_BYTES = max(300_000, int(os.getenv("OCR_SPACE_MAX_UPLOAD_BYTES", "950000")))
OCR_SPACE_TIMEOUT = float(os.getenv("OCR_SPACE_TIMEOUT", "8"))
OCR_SPACE_TOTAL_TIMEOUT = float(os.getenv("OCR_SPACE_TOTAL_TIMEOUT", "8"))
OCR_SPACE_ENGINES = [engine.strip() for engine in os.getenv("OCR_SPACE_ENGINES", "2,1").split(",") if engine.strip()]
OCR_CONCURRENCY = int(os.getenv("OCR_CONCURRENCY", "20"))
OCR_SPACE_429_COOLDOWN_SECONDS = max(30, int(os.getenv("OCR_SPACE_429_COOLDOWN_SECONDS", "180")))
LOCAL_FALLBACK = os.getenv("LOCAL_FALLBACK", "1").strip() == "1"
LOCAL_COMPLEMENT = os.getenv("LOCAL_COMPLEMENT", "0").strip() == "1"
VERIFY_WITH_LOCAL = os.getenv("VERIFY_WITH_LOCAL", "0").strip() == "1"
OCR_MAX_SIDE = int(os.getenv("OCR_MAX_SIDE", "3000"))
OCR_MIN_SIDE = int(os.getenv("OCR_MIN_SIDE", "2600"))
LOCAL_OCR_MIN_CARD_VOTES = max(1, int(os.getenv("LOCAL_OCR_MIN_CARD_VOTES", "2")))
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
CARD_MANAGER_DB_PATH = Path(os.getenv("CARD_MANAGER_DB_PATH", str(LEDGER_DB_PATH))).expanduser()
CARD_IMAGE_CACHE_DIR = Path(os.getenv("CARD_IMAGE_CACHE_DIR", "outputs/card_image_cache")).expanduser()
OCR_CANDIDATES_PATH = Path(os.getenv("OCR_CANDIDATES_PATH", "outputs/ocr_candidates.json")).expanduser()
TODAY_OCR_CACHE_PATH = Path(os.getenv("TODAY_OCR_CACHE_PATH", "outputs/today_ocr_cache.json")).expanduser()
PHOTO_BATCH_MAX_IMAGES = max(0, int(os.getenv("PHOTO_BATCH_MAX_IMAGES", "0")))
PHOTO_RATE_WINDOW_SECONDS = max(10, int(os.getenv("PHOTO_RATE_WINDOW_SECONDS", "60")))
PHOTO_RATE_LIMIT_PER_CHAT = max(1, int(os.getenv("PHOTO_RATE_LIMIT_PER_CHAT", "80")))
PHOTO_RATE_LIMIT_PER_USER = max(1, int(os.getenv("PHOTO_RATE_LIMIT_PER_USER", "50")))
OCR_PROGRESS_ENABLED = os.getenv("OCR_PROGRESS_ENABLED", "1").strip() == "1"
OCR_PROGRESS_MIN_IMAGES = max(1, int(os.getenv("OCR_PROGRESS_MIN_IMAGES", "3")))
OCR_PROGRESS_UPDATE_SECONDS = max(0.5, float(os.getenv("OCR_PROGRESS_UPDATE_SECONDS", "1.5")))
PROCESS_STARTED_AT = time.time()

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
logger = logging.getLogger("telegram-card-platform")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass(frozen=True)
class OcrResult:
    cards: tuple[str, ...]
    psn_cards: tuple[str, ...] = tuple()
    psn_uncertain: tuple[str, ...] = tuple()
    psn_ordered: tuple[str, ...] = tuple()
    card_locations: tuple[tuple[str, int, int], ...] = tuple()
    psn_locations: tuple[tuple[str, int, int], ...] = tuple()
    sequence_index: int = 0
    pubg_expected_count: int | None = None
    psn_expected_count: int | None = None
    raw_text: str = ""
    uncertain_count: int = 0
    source_caption: str = ""
    ocr_fixed_count: int = 0
    ocr_missing_count: int = 0
    ocr_false_negative: int = 0
    ocr_character_confusion: int = 0
    corrections_applied: tuple[dict[str, str], ...] = tuple()
    remote_variant_conflict: bool = False
    remote_original_card_scores: tuple[tuple[str, float], ...] = tuple()
    remote_enhanced_card_scores: tuple[tuple[str, float], ...] = tuple()
    remote_original_rebuilt_card_scores: tuple[tuple[str, float], ...] = tuple()
    remote_enhanced_rebuilt_card_scores: tuple[tuple[str, float], ...] = tuple()
    remote_cpu_candidates: tuple[str, ...] = tuple()
    remote_cpu_candidate_scores: tuple[tuple[str, float], ...] = tuple()
    remote_cpu_review_required: bool = False
    remote_cpu_review_reasons: tuple[str, ...] = tuple()
    has_unresolved_pubg_fragment: bool = False


@dataclass(frozen=True)
class OrderedCardOccurrence:
    card: str
    image_index: int
    y: int
    x: int
    duplicate_key: str
    display: str = ""


chat_buffers: dict[int, list[Update]] = defaultdict(list)
manual_review_notifier = ManualReviewNotifier()
chat_tasks: dict[int, asyncio.Task] = {}
chat_flush_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
ocrspace_cooldown_until = 0.0
ocrspace_key_cooldowns: dict[str, float] = {}
remote_ocr_status = {
    "last_ok": False,
    "last_error": "",
    "last_latency_ms": 0,
    "last_card_count": 0,
    "last_checked_at": "",
    "remote_health": False,
    "last_success_at": "",
    "last_failed_at": "",
    "today_date": "",
    "today_remote_calls": 0,
    "today_remote_success": 0,
    "today_remote_failed": 0,
    "today_fallback_count": 0,
    "today_remote_latency_total_ms": 0,
    "today_enhanced_used": 0,
    "today_cache_hits": 0,
    "today_remote_busy": 0,
}
remote_ocr_health_cache: dict[str, object] = {"checked_at": 0.0, "result": None}
remote_ocr_offline_until = 0.0
remote_ocr_execution_gate = RemoteExecutionGate(REMOTE_OCR_MAX_IN_FLIGHT)
ocr_semaphore = asyncio.Semaphore(max(1, OCR_CONCURRENCY))
ocr_batch_jobs = OcrBatchJobPool()
ocr_live_progresses: dict[int, "LiveOcrBatchProgress"] = {}
ledger_store = LedgerStore(LEDGER_DB_PATH)
card_manager_store = CardManagerStore(CARD_MANAGER_DB_PATH)
card_manager_images_by_update: dict[int, CachedOriginalImage] = {}
font_repository = FontRepository()
pending_learning_texts: dict[int, str] = {}
welcome_sent_at: dict[int, float] = {}


class OcrBatchProgress(BaseOcrBatchProgress):
    def __init__(self, message, total: int) -> None:
        super().__init__(
            message,
            total,
            enabled=lambda: OCR_PROGRESS_ENABLED,
            minimum_images=lambda: OCR_PROGRESS_MIN_IMAGES,
            update_seconds=lambda: OCR_PROGRESS_UPDATE_SECONDS,
            clock=lambda: time.time(),
            logger=logger,
        )


class LiveOcrBatchProgress(BaseLiveOcrBatchProgress):
    def __init__(self, message) -> None:
        super().__init__(
            message,
            enabled=lambda: OCR_PROGRESS_ENABLED,
            update_seconds=lambda: OCR_PROGRESS_UPDATE_SECONDS,
            clock=lambda: time.time(),
            logger=logger,
        )


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
    text = re.sub(r"(?<![A-Z0-9])9([0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})", r"S\1", text)
    return re.sub(r"((?:密码|卡号|CDK|CDKEY)\s*\d*[:：]?)\s*([SP5$][0ODQU][7TIL/?])", r"\1 \2", text)


def parse_ocrspace_api_keys(raw_keys: str, fallback_key: str = "") -> list[str]:
    keys: list[str] = []
    for value in [*raw_keys.replace(";", ",").split(","), fallback_key]:
        key = value.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


OCR_SPACE_API_KEYS = parse_ocrspace_api_keys(OCR_SPACE_API_KEYS_RAW, OCR_SPACE_API_KEY)


def ocr_confusion_count(source_cards: list[str], selected_cards: list[str]) -> int:
    count = 0
    for selected in selected_cards:
        selected_compact = selected.replace("-", "")
        for source in source_cards:
            source_compact = source.replace("-", "")
            if source == selected or len(source_compact) != len(selected_compact):
                continue
            if hamming_distance(source_compact, selected_compact) == 1:
                count += 1
                break
    return count


def enhanced_ocrspace_pubg_cards(raw_text: str, legacy_cards: list[str]) -> tuple[list[str], dict[str, int]]:
    stats = {
        "ocr_fixed_count": 0,
        "ocr_missing_count": 0,
        "ocr_false_negative": 0,
        "ocr_character_confusion": 0,
    }
    if not raw_text.strip():
        return [], stats

    try:
        correction_result = apply_corrections(raw_text, card_type="PUBG")
        audit = build_candidate_audit(raw_text, card_type="PUBG")
        append_candidate_audit(raw_text, card_type="PUBG", output_path=OCR_CANDIDATES_PATH)
        font_repository.learn_sample(raw_text, card_type="PUBG")
    except Exception:
        logger.exception("OCR candidate audit failed")
        return [], stats

    scored_items = []
    for item in audit.candidate_list:
        value = str(item.get("value", ""))
        if not validate_candidate(value, card_type="PUBG"):
            continue
        score = item.get("score")
        scored_items.append((float(score or 0.0), value))
    if correction_result.best_candidate:
        value = correction_result.best_candidate.candidate.corrected_text
        if validate_candidate(value, card_type="PUBG"):
            scored_items.append((float(correction_result.best_candidate.score), value))

    score_by_value = {value: score for score, value in scored_items}
    selected: list[str] = []
    for item in audit.candidate_list:
        value = str(item.get("value", ""))
        if value not in score_by_value:
            continue
        same_index = next((index for index, existing in enumerate(selected) if likely_same_card(value, existing)), None)
        if same_index is None:
            selected.append(value)
            continue
        existing = selected[same_index]
        if score_by_value[value] > score_by_value.get(existing, 0.0):
            selected[same_index] = value
    if correction_result.best_candidate:
        value = correction_result.best_candidate.candidate.corrected_text
        if validate_candidate(value, card_type="PUBG") and value not in selected:
            selected.append(value)

    legacy_set = set(legacy_cards)
    selected_set = set(selected)
    stats["ocr_fixed_count"] = len([card for card in selected if card not in legacy_set])
    stats["ocr_missing_count"] = max(0, len(selected_set - legacy_set))
    stats["ocr_false_negative"] = stats["ocr_missing_count"]
    stats["ocr_character_confusion"] = ocr_confusion_count(legacy_cards, selected)
    return selected, stats


def merge_ocr_stats(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    return {
        "ocr_fixed_count": left.get("ocr_fixed_count", 0) + right.get("ocr_fixed_count", 0),
        "ocr_missing_count": left.get("ocr_missing_count", 0) + right.get("ocr_missing_count", 0),
        "ocr_false_negative": left.get("ocr_false_negative", 0) + right.get("ocr_false_negative", 0),
        "ocr_character_confusion": left.get("ocr_character_confusion", 0) + right.get("ocr_character_confusion", 0),
    }


BUILTIN_PUBG_CARD_CORRECTIONS = {
    "S07304-9M8Q-Y7UW-78220": "S07304-9M8Q-Y7UW-78Z2U",
    "S07304-8MP5-4TY9-VDVR6": "S07304-8MP5-4TYS-VDVR6",
    "S07304-4U60-U5L1-GLXUV": "S07304-4U6Q-U5LL-GLXUV",
}

PUBG_PREFIXES = {
    "S07304",
    "S07234",
    "S07303",
    "S07240",
    "S07292",
    "S07298",
    "S07213",
    "S07291",
    "S07205",
    "S07239",
    "S07228",
    "S07286",
}
PUBG_PREFIX_RE = re.compile(r"S07[0-9]{3}")
PUBG_PREFIX_TAIL_RE = re.compile(r"7[0-9]{3}")


def cleanup_server_files(now: float | None = None) -> int:
    removed = cleanup_server_file_records(
        enabled=CLEANUP_ENABLED,
        after_seconds=CLEANUP_AFTER_SECONDS,
        outputs_dir=CLEANUP_OUTPUTS_DIR,
        audit_root=DEFAULT_AUDIT_ROOT,
        cleanup_audits=cleanup_expired_audits,
        logger=logger,
        now=now,
        temp_root=Path(tempfile.gettempdir()),
    )
    # 管理端核对图固定留存 24 小时；仅清理图片，从不删除卡密记录。
    try:
        removed += cleanup_expired_card_images(CARD_IMAGE_CACHE_DIR)
    except Exception:
        logger.exception("Failed to clean card manager image cache")
    return removed


async def server_file_cleanup_loop() -> None:
    await periodic_cleanup_loop(CLEANUP_CHECK_SECONDS, cleanup_server_files)


async def start_background_tasks(app: Application) -> None:
    await start_managed_background_tasks(
        app,
        cleanup_enabled=CLEANUP_ENABLED,
        cleanup=cleanup_server_files,
        cleanup_loop=server_file_cleanup_loop,
        remote_enabled=REMOTE_OCR_ENABLED,
        remote_url=REMOTE_OCR_URL,
        remote_probe_loop=remote_ocr_probe_loop,
        daily_stats_loop=lambda: daily_ocr_stats_loop(
            app.bot,
            parse_chat_id(OWNER_CHAT_ID),
            audit_root=DEFAULT_AUDIT_ROOT,
            logger=logger,
        ),
    )


async def stop_background_tasks(app: Application) -> None:
    await stop_managed_background_tasks(
        app,
        close_callbacks=(close_remote_http_client, close_ocrspace_http_client),
    )


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
    if len(chars) >= 1 and chars[0] in {"5", "$", "P", "9"}:
        chars[0] = "S"
    if len(chars) >= 2 and chars[1] in {"O", "D", "Q", "U"}:
        chars[1] = "0"
    if len(chars) >= 3 and chars[2] in {"T", "I", "L", "/", "?"}:
        chars[2] = "7"
    for index in range(3, min(6, len(chars))):
        chars[index] = repair_digit(chars[index])
    return "".join(chars)


def valid_card(card: str) -> bool:
    return bool(
        re.fullmatch(r"S07[0-9]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}", card)
    )


def pubg_has_forbidden_body_chars(card: str) -> bool:
    if not valid_card(card):
        return False
    body = card.split("-", 1)[1].replace("-", "")
    return any(char in "01OI" for char in body)


def apply_builtin_pubg_correction(card: str) -> str:
    corrected = BUILTIN_PUBG_CARD_CORRECTIONS.get(card, card)
    if corrected != card:
        logger.info("Applied built-in PUBG OCR correction: %s -> %s", card, corrected)
    return corrected


def valid_psn_card(card: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", card))


def psn_is_pubg_substring(psn: str, pubg_cards: list[str] | tuple[str, ...]) -> bool:
    key = psn_key(psn) or normalize_text(psn).strip()
    if not key:
        return False
    compact_key = key.replace("-", "")
    for pubg in pubg_cards:
        normalized_pubg = normalize_text(pubg).strip()
        if not valid_card(normalized_pubg):
            continue
        if key in normalized_pubg or compact_key in normalized_pubg.replace("-", ""):
            return True
    return False


def filter_psn_pubg_substrings(psn_lines: list[str], pubg_cards: list[str] | tuple[str, ...]) -> list[str]:
    if not pubg_cards:
        return psn_lines
    filtered: list[str] = []
    for line in psn_lines:
        if psn_is_pubg_substring(line, pubg_cards):
            continue
        filtered.append(line)
    return filtered


def psn_is_embedded_in_long_token(candidate: str, text: str) -> bool:
    key = psn_key(candidate) or normalize_text(candidate).strip()
    if not key:
        return False
    compact_key = key.replace("-", "")
    normalized = normalize_text(text)
    for token_match in re.finditer(r"[A-Z0-9][A-Z0-9-]{14,}[A-Z0-9]", normalized):
        token = token_match.group(0).strip("-")
        if token == key:
            continue
        compact_token = token.replace("-", "")
        if key in token or compact_key in compact_token:
            return True
    return False


def add_card_candidate(cards: list[str], seen: set[str], first: str, second: str, third: str, fourth: str) -> None:
    card = apply_builtin_pubg_correction(f"{repair_first_group(first)}-{second}-{third}-{fourth}")
    if valid_card(card) and card not in seen:
        seen.add(card)
        cards.append(card)


@dataclass(frozen=True)
class OcrTextLine:
    text: str
    y: float
    x: float
    index: int


def text_without_s07_lines(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if "S07" not in normalize_text(line))


def is_pubg_image_text(text: str) -> bool:
    normalized = normalize_text(text)
    compact = re.sub(r"[^A-Z0-9$]", "", normalized)
    if PUBG_PREFIX_RE.search(normalized):
        return True
    # 中文说明：缺失 S0 的 PUBG 前缀只允许 7 + 三位数字，避免 PSN 尾段如 7LML 被误判成 PUBG 图。
    if not re.search(r"(?<![A-Z0-9])7[0-9]{3}", normalized):
        normalized = re.sub(r"(?<![A-Z0-9])7[A-Z0-9]{3}", "XXXX", normalized)
    if re.search(r"(?<![A-Z0-9])7[A-Z0-9]{3}[\s\-_|:：；;,.，。/\\]+[A-Z0-9]{4}[\s\-_|:：；;,.，。/\\]+[A-Z0-9]{4}", normalized):
        return True
    if "S07" in normalized:
        return True
    pubg_traces = ["S07", "507304", "907304", "SO7304", "$07304"]
    for prefix in PUBG_PREFIXES:
        suffix = prefix[1:]
        pubg_traces.extend((prefix, f"5{suffix}", f"9{suffix}", f"${suffix}", f"SO{suffix[1:]}"))
    if any(trace in compact for trace in pubg_traces):
        return True
    return bool(re.search(r"S0[A-Z0-9]304", compact))


def line_has_pubg_prefix(text: str) -> bool:
    return bool(PUBG_PREFIX_RE.search(normalize_text(text)))


def clean_pubg_fragment(text: str, *, from_prefix: bool) -> str:
    normalized = normalize_text(text)
    if from_prefix:
        match = PUBG_PREFIX_RE.search(normalized)
        if not match:
            return ""
        normalized = normalized[match.start() :]
    return re.sub(r"[^A-Z0-9-]", "", normalized)


def join_pubg_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if left.endswith("-") or right.startswith("-"):
        return left + right
    return left + right


def compact_pubg_fragment(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(text))


def strict_join_pubg_fragment(current: str, next_fragment: str) -> tuple[str, str | None]:
    current_compact = compact_pubg_fragment(current)
    next_compact = compact_pubg_fragment(next_fragment)
    if not current_compact.startswith("S07"):
        return current, "missing_s07_prefix"
    missing = 19 - len(current_compact)
    if missing <= 0:
        return current, None
    if not next_compact:
        return current, None
    if len(next_compact) > missing:
        return current, "tail_too_long"
    return join_pubg_fragments(current, next_fragment), None


def rebuild_pubg_card_from_fragments(text: str) -> str:
    compact = re.sub(r"[^A-Z0-9]", "", normalize_text(text))
    match = PUBG_PREFIX_RE.search(compact)
    if not match:
        return ""
    compact = compact[match.start() :]
    if len(compact) < 19:
        return ""
    card = f"{compact[:6]}-{compact[6:10]}-{compact[10:14]}-{compact[14:19]}"
    card = apply_builtin_pubg_correction(card)
    return card if valid_card(card) else ""


def rebuild_split_pubg_prefix_card(prefix_line: str, tail_line: str) -> str:
    prefix_match = re.search(r"S073\s*$", clean_pubg_fragment(prefix_line, from_prefix=False))
    if not prefix_match:
        return ""
    tail_match = re.match(r"^\s*([0-9]{2})[\s\-_|:：；;,.，。/\\]+([A-Z0-9]{4})[\s\-_|:：；;,.，。/\\]+([A-Z0-9]{4})[\s\-_|:：；;,.，。/\\]+([A-Z0-9]{5})(?![A-Z0-9])", normalize_text(tail_line))
    if not tail_match:
        return ""
    card = f"S073{tail_match.group(1)}-{tail_match.group(2)}-{tail_match.group(3)}-{tail_match.group(4)}"
    card = apply_builtin_pubg_correction(card)
    return card if valid_card(card) else ""


def extract_cards(text: str) -> list[str]:
    text = normalize_text(text)
    sep = r"[\s\-_|:：；;,.，。|]+"
    shaped_pattern = (
        r"(?<![A-Z])"
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
        add_card_candidate(cards, seen, first, second, third, fourth)

    missing_s0_pattern = (
        r"(?<![A-Z0-9])"
        r"(7[0-9]{3})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{5})"
        + r"(?![A-Z0-9])"
    )
    for tail, second, third, fourth in re.findall(missing_s0_pattern, text):
        add_card_candidate(cards, seen, f"S0{tail}", second, third, fourth)

    noisy_shaped_pattern = (
        r"(?<![A-Z])"
        r"([SP5$][0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{5})"
    )
    for match in re.finditer(noisy_shaped_pattern, text):
        matched_text = match.group(0)
        if "|" not in matched_text:
            continue
        add_card_candidate(cards, seen, *match.groups())

    compact_pattern = (
        r"(?<![A-Z])"
        r"([SP5$][0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})"
        r"([A-Z0-9]{4})"
        r"([A-Z0-9]{4})"
        r"([A-Z0-9]{5})"
        r"(?![A-Z0-9])"
    )
    for first, second, third, fourth in re.findall(compact_pattern, text):
        add_card_candidate(cards, seen, first, second, third, fourth)

    compact_third_fourth_pattern = (
        r"(?<![A-Z])"
        r"([SP5$][0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})"
        + sep
        + r"([A-Z0-9]{4})"
        + sep
        + r"([A-Z0-9]{9})"
        r"(?![A-Z0-9])"
    )
    for first, second, tail in re.findall(compact_third_fourth_pattern, text):
        add_card_candidate(cards, seen, first, second, tail[:4], tail[4:])

    loose_pattern = (
        r"(?<![A-Z])"
        r"([SP5$][0ODQU][7TIL/?][0-9ODQUILTZEA$SGB]{3})"
        r"((?:[\s\-_|:：；;,.，。|]*[A-Z0-9]){13})"
    )
    for first, rest in re.findall(loose_pattern, text):
        if "\n" not in rest and "|" not in rest:
            continue
        compact = re.sub(r"[^A-Z0-9]", "", rest)
        if len(compact) not in {12, 13}:
            continue
        add_card_candidate(cards, seen, first, compact[:4], compact[4:8], compact[8:])

    return cards


def ocr_item_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text", "")).strip()
    return str(item).strip()


def ocr_item_xy(item) -> tuple[float, float]:
    if not isinstance(item, dict):
        return 0.0, 0.0
    box = (
        item.get("rec_box")
        or item.get("rec_boxes")
        or item.get("box")
        or item.get("bbox")
        or item.get("rect")
    )
    poly = item.get("rec_poly") or item.get("rec_polys") or item.get("poly") or item.get("points")
    if isinstance(box, (list, tuple)) and len(box) >= 4:
        try:
            return float(box[1]), float(box[0])
        except (TypeError, ValueError):
            pass
    if isinstance(poly, (list, tuple)) and poly:
        points = poly
        if len(points) == 1 and isinstance(points[0], (list, tuple)):
            points = points[0]
        xs: list[float] = []
        ys: list[float] = []
        for point in points:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                try:
                    xs.append(float(point[0]))
                    ys.append(float(point[1]))
                except (TypeError, ValueError):
                    continue
        if xs and ys:
            return min(ys), min(xs)
    return 0.0, 0.0


def ordered_ocr_text_lines(items: list | tuple) -> list[OcrTextLine]:
    lines: list[OcrTextLine] = []
    for index, item in enumerate(items or []):
        text = ocr_item_text(item)
        if not text:
            continue
        y, x = ocr_item_xy(item)
        lines.append(OcrTextLine(text=text, y=y, x=x, index=index))
    return sorted(lines, key=lambda line: (line.y, line.x, line.index))


def ocr_lines_have_coordinates(lines: list[OcrTextLine]) -> bool:
    return any(line.y != 0.0 or line.x != 0.0 for line in lines)


def allow_previous_pubg_tail_fallback(lines: list[OcrTextLine]) -> bool:
    if ocr_lines_have_coordinates(lines):
        return False
    return sum(1 for line in lines if line_has_pubg_prefix(line.text)) == 1


def extract_cards_from_ordered_lines(lines: list[OcrTextLine]) -> tuple[list[str], bool]:
    cards: list[str] = []
    seen: set[str] = set()
    unresolved = False
    previous_tail_fallback_allowed = allow_previous_pubg_tail_fallback(lines)
    for index, line in enumerate(lines):
        line_cards = extract_cards(line.text)
        for card in line_cards:
            if card not in seen:
                seen.add(card)
                cards.append(card)
        if not is_pubg_image_text(line.text):
            continue
        if line_cards:
            continue
        for end in range(index + 1, min(index + 3, len(lines))):
            split_card = rebuild_split_pubg_prefix_card(line.text, lines[end].text)
            if split_card:
                if split_card not in seen:
                    seen.add(split_card)
                    cards.append(split_card)
                    logger.info("PUBG LINE WRAP MERGED: %s + %s => %s", line.text, lines[end].text, split_card)
                break
            if line_has_pubg_prefix(lines[end].text) or is_pubg_image_text(lines[end].text):
                break
        current = clean_pubg_fragment(line.text, from_prefix=True)
        if not current:
            continue
        merged = False
        pending_unresolved: tuple[str, str] | None = None
        for end in range(index + 1, min(index + 4, len(lines))):
            next_line = lines[end]
            if line_has_pubg_prefix(next_line.text):
                pending_unresolved = (" + ".join(part.text for part in lines[index:end]), "next_pubg_prefix")
                break
            next_fragment = clean_pubg_fragment(next_line.text, from_prefix=False)
            current, reject_reason = strict_join_pubg_fragment(current, next_fragment)
            if reject_reason:
                pending_unresolved = (" + ".join(part.text for part in lines[index : end + 1]), reject_reason)
                break
            card = rebuild_pubg_card_from_fragments(current)
            if not card:
                continue
            if card not in seen:
                seen.add(card)
                cards.append(card)
                merged = True
                logger.info(
                    "PUBG LINE WRAP MERGED: %s => %s",
                    " + ".join(part.text for part in lines[index : end + 1]),
                    card,
                )
            break
        if not merged and previous_tail_fallback_allowed and index > 0:
            # 中文说明：无坐标且整图只有一个 PUBG 前缀时，才允许上一行尾段兜底，避免多卡场景跨卡乱拼。
            prev_line = lines[index - 1]
            if not line_has_pubg_prefix(prev_line.text):
                prev_fragment = clean_pubg_fragment(prev_line.text, from_prefix=False)
                previous_current, reject_reason = strict_join_pubg_fragment(
                    clean_pubg_fragment(line.text, from_prefix=True),
                    prev_fragment,
                )
                card = "" if reject_reason else rebuild_pubg_card_from_fragments(previous_current)
                if card and card not in seen:
                    seen.add(card)
                    cards.append(card)
                    merged = True
                    logger.info("PUBG LINE WRAP MERGED: %s + %s => %s", line.text, prev_line.text, card)
        if pending_unresolved and not merged:
            unresolved = True
            logger.info("PUBG LINE WRAP UNRESOLVED: %s reason=%s", pending_unresolved[0], pending_unresolved[1])
    return cards, unresolved
def extract_source_anchored_pubg_cards(raw_text: str) -> tuple[list[str], bool]:
    """Keep PUBG candidates tied to one OCR line or an adjacent line wrap."""
    return extract_cards_from_ordered_lines(ordered_ocr_text_lines(raw_text.splitlines()))


def pubg_card_prefix_key(card: str) -> tuple[str, str, str] | None:
    parts = card.split("-")
    if len(parts) != 4 or not valid_card(card):
        return None
    return parts[0], parts[1], parts[2]


def merge_text_rebuilt_and_worker_cards(
    text_cards: list[str],
    worker_cards: list[str],
    text_lines: list[str] | None = None,
) -> list[str]:
    blocked_prefix_keys = incomplete_pubg_prefix_keys(text_lines or [])
    merged = merge_text_and_worker_pubg_cards(text_cards, worker_cards, blocked_prefix_keys=blocked_prefix_keys)
    for dropped in merged.dropped:
        logger.info("PUBG WORKER CARD DROPPED: %s reason=%s", dropped.card, dropped.reason)
    return list(merged.cards)


def repair_psn_group(group: str, index: int) -> tuple[str, bool]:
    return group, False


def scan_psn_candidates(text: str, force: bool = False) -> list[tuple[str, bool]]:
    text = normalize_text(text)
    pubg_cards = extract_cards(text)
    text = text_without_s07_lines(text)
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
        if psn_is_embedded_in_long_token(candidate, text):
            continue
        if psn_is_pubg_substring(candidate, pubg_cards):
            continue
        if not candidate.startswith("S07") and candidate not in seen:
            seen.add(candidate)
            results.append((candidate, False))
    return results


def scan_labeled_psn_candidates(text: str) -> list[tuple[str, bool]]:
    text = normalize_text(text)
    pubg_cards = extract_cards(text)
    text = text_without_s07_lines(text)
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
            if psn_is_embedded_in_long_token(candidate, text):
                continue
            if psn_is_pubg_substring(candidate, pubg_cards):
                continue
            if candidate.startswith("S07") or candidate in seen:
                continue
            seen.add(candidate)
            results.append((candidate, False))
    return results


def extract_psn_ordered(text: str, force: bool = False) -> list[str]:
    if is_pubg_image_text(text):
        return []
    pubg_cards = extract_cards(text)
    labeled = scan_labeled_psn_candidates(text)
    if labeled:
        return filter_psn_pubg_substrings(psn_matches_to_lines(labeled), pubg_cards)
    return filter_psn_pubg_substrings(
        [
            f"{card}{FUZZY_SUFFIX}" if fuzzy and not card.endswith(FUZZY_SUFFIX) else card
            for card, fuzzy in scan_psn_candidates(text, force=force)
        ],
        pubg_cards,
    )


def extract_psn_cards(text: str, force: bool = False) -> list[str]:
    if is_pubg_image_text(text):
        return []
    pubg_cards = extract_cards(text)
    return filter_psn_pubg_substrings(
        [card for card, fuzzy in scan_psn_candidates(text, force=force) if not fuzzy and valid_psn_card(card)],
        pubg_cards,
    )


def psn_matches_to_lines(matches: list[tuple[str, bool]]) -> list[str]:
    return [
        f"{card}{FUZZY_SUFFIX}" if fuzzy and not card.endswith(FUZZY_SUFFIX) else card
        for card, fuzzy in matches
    ]


def prefer_labeled_psn_ordered(raw_chunks: list[str], fallback_ordered: list[str]) -> list[str]:
    raw_text = "\n".join(raw_chunks)
    if is_pubg_image_text(raw_text):
        return []
    pubg_cards = extract_cards(raw_text)
    labeled = scan_labeled_psn_candidates(raw_text)
    if labeled:
        return exact_unique_text(filter_psn_pubg_substrings(psn_matches_to_lines(labeled), pubg_cards))
    return exact_unique_text(filter_psn_pubg_substrings(fallback_ordered, pubg_cards))


def extract_uncertain_psn_cards(text: str, known_cards: list[str] | None = None, force: bool = False) -> list[str]:
    return []


def psn_ordered_for_image(raw_text: str, cards: list[str], psn_hint: bool = False) -> list[str]:
    if cards or is_pubg_image_text(raw_text):
        return []
    return exact_unique_text(extract_psn_ordered(raw_text, force=psn_hint))


def parse_psn_expected_count(caption: str) -> int | None:
    return None


def parse_pubg_expected_count(caption: str) -> int | None:
    return None


def count_pubg_markers(text: str) -> int | None:
    return count_unique_pubg_markers(
        text,
        normalize_text=normalize_text,
        prefix_pattern=PUBG_PREFIX_RE,
    )


def merge_pubg_expected_count(configured: int | None, raw_text: str) -> int | None:
    detected = count_pubg_markers(raw_text)
    if configured and detected:
        return max(configured, detected)
    return configured or detected


def remote_needs_ocrspace_complement(remote: OcrResult) -> tuple[bool, str]:
    if REMOTE_OCR_COMPLEMENT:
        return True, "remote complement"
    if remote.has_unresolved_pubg_fragment:
        return True, "remote unresolved pubg fragment"
    if requires_cloud_confirmation(remote.raw_text):
        return True, "recovered pubg prefix requires cloud confirmation"
    detected = max(count_pubg_markers(remote.raw_text) or 0, remote.pubg_expected_count or 0)
    if detected > len(remote.cards):
        return True, "remote pubg marker count mismatch"
    return False, ""


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


def settle_and_correct_pubg_cards(cards: list[str]) -> tuple[list[str], int, tuple[dict[str, str], ...]]:
    settled, uncertain = settle_image_cards(cards)
    accepted: list[str] = []
    for card in settled:
        if pubg_has_forbidden_body_chars(card):
            uncertain += 1
            logger.warning("OCR RESULT DROPPED reason=pubg_forbidden_body_chars card=%s", card)
            continue
        accepted.append(card)
    correction = apply_pubg_char_corrections(accepted, font_repository=font_repository)
    return list(correction.cards), uncertain, tuple(item.as_dict() for item in correction.corrections)


def filter_local_ocr_cards(cards: list[str], min_votes: int = LOCAL_OCR_MIN_CARD_VOTES) -> list[str]:
    if min_votes <= 1:
        return exact_unique(cards)
    counts = Counter(card for card in cards if valid_card(card))
    return [card for card in exact_unique(cards) if counts[card] >= min_votes]


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

    output_path = image_path.with_suffix(".ocrspace.png")
    image.save(output_path, format="PNG", optimize=True)
    if output_path.stat().st_size <= OCR_SPACE_MAX_UPLOAD_BYTES:
        return output_path

    output_path.unlink(missing_ok=True)
    jpeg_path = image_path.with_suffix(".ocrspace.jpg")
    working = image
    for max_side_target in (2600, 2200, 1800, 1500, 1200, 1000, 850):
        max_side = max(working.size)
        if max_side > max_side_target:
            scale = max_side_target / max_side
            working = working.resize(
                (max(1, int(working.width * scale)), max(1, int(working.height * scale))),
                Image.Resampling.LANCZOS,
            )
        for quality in (88, 78, 68, 58, 48):
            working.save(jpeg_path, format="JPEG", quality=quality, optimize=True)
            if jpeg_path.stat().st_size <= OCR_SPACE_MAX_UPLOAD_BYTES:
                return jpeg_path

    return jpeg_path


def run_ocrspace(
    image_path: Path,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> OcrResult:
    return recognize_ocrspace(
        sys.modules[__name__],
        image_path,
        psn_hint=psn_hint,
        psn_expected_count=psn_expected_count,
        pubg_expected_count=pubg_expected_count,
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
            ordered = psn_ordered_for_image(text, text_cards, psn_hint=psn_hint)
            psn_ordered.extend(ordered)
            psn_cards.extend(card for card in ordered if not card.endswith(FUZZY_SUFFIX))
            psn_uncertain.extend(card for card in ordered if card.endswith(FUZZY_SUFFIX))

    settled_cards, uncertain, card_corrections = settle_and_correct_pubg_cards(filter_local_ocr_cards(cards))
    merged_raw_text = "\n".join(raw_chunks)
    return OcrResult(
        cards=tuple(settled_cards),
        psn_cards=tuple(exact_unique_psn(psn_cards)),
        psn_uncertain=tuple(exact_unique_text(psn_uncertain)),
        psn_ordered=tuple(limit_psn_ordered(prefer_labeled_psn_ordered(raw_chunks, psn_ordered), psn_expected_count)),
        pubg_expected_count=merge_pubg_expected_count(pubg_expected_count, merged_raw_text),
        psn_expected_count=psn_expected_count,
        raw_text=merged_raw_text,
        uncertain_count=uncertain,
        corrections_applied=card_corrections,
    )


def remote_ocr_now() -> datetime:
    return datetime.now(LEDGER_TZ)


def ensure_remote_ocr_today(now: datetime | None = None) -> None:
    ensure_daily_counters(remote_ocr_status, now or remote_ocr_now())


def record_remote_ocr_start() -> None:
    ensure_remote_ocr_today()
    remote_ocr_status["today_remote_calls"] += 1


def record_remote_ocr_fallback(reason: str) -> None:
    ensure_remote_ocr_today()
    remote_ocr_status["today_fallback_count"] += 1
    logger.info("OCRSPACE FALLBACK reason=%s", reason)


def record_remote_ocr_busy(reason: str) -> None:
    """Worker 忙不等同于离线：保留健康线路，不触发 180 秒冷却。"""
    ensure_remote_ocr_today()
    remote_ocr_status["today_remote_busy"] += 1
    remote_ocr_status["last_error"] = f"busy:{reason}"
    logger.info("REMOTE OCR BUSY reason=%s", reason)


def remote_ocr_execution_slot():
    return remote_ocr_execution_gate.slot(REMOTE_OCR_BUSY_WAIT_SECONDS)


def remote_ocr_is_circuit_open(now: float | None = None) -> bool:
    current = time.time() if now is None else now
    return provider_circuit_is_open(remote_ocr_offline_until, current)


def remote_ocr_circuit_reason(now: float | None = None) -> str:
    current = time.time() if now is None else now
    return provider_circuit_reason(remote_ocr_offline_until, current)


def mark_remote_ocr_offline(reason: str) -> None:
    global remote_ocr_offline_until
    remote_ocr_offline_until = max(remote_ocr_offline_until, time.time() + REMOTE_OCR_OFFLINE_SECONDS)
    remote_ocr_health_cache.update({"checked_at": time.time(), "result": (False, {}, reason)})
    logger.info("REMOTE OCR OFFLINE reason=%s retry_after=%ss", reason, REMOTE_OCR_OFFLINE_SECONDS)


def mark_remote_ocr_online() -> None:
    global remote_ocr_offline_until
    if remote_ocr_offline_until > 0:
        logger.info("REMOTE OCR ONLINE")
    remote_ocr_offline_until = 0.0


async def remote_ocr_probe_loop() -> None:
    while True:
        await asyncio.sleep(REMOTE_OCR_PROBE_SECONDS)
        if not REMOTE_OCR_ENABLED or not REMOTE_OCR_URL:
            continue
        if not remote_ocr_is_circuit_open():
            continue
        await asyncio.to_thread(remote_ocr_available, True)


def remote_ocr_fallback_reason() -> str:
    return provider_fallback_reason(
        enabled=REMOTE_OCR_ENABLED,
        url=REMOTE_OCR_URL,
        offline_until=remote_ocr_offline_until,
        now=time.time(),
        last_error=str(remote_ocr_status.get("last_error") or ""),
    )


def avg_remote_latency_ms() -> int:
    ensure_remote_ocr_today()
    return provider_average_latency_ms(remote_ocr_status)


def percent_rate(part: int, total: int) -> str:
    return provider_percent_rate(part, total)


def current_ocr_provider() -> str:
    return provider_current_provider(remote_ocr_status, REMOTE_OCR_LABEL)


def safe_remote_url() -> str:
    return provider_safe_remote_url(REMOTE_OCR_URL).rstrip("/")


def format_time_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "无"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed.astimezone(LEDGER_TZ).strftime("%H:%M:%S")


def process_uptime_text() -> str:
    return _process_uptime_text(PROCESS_STARTED_AT)


def remote_worker_health() -> tuple[bool, dict[str, object], str]:
    if not REMOTE_OCR_ENABLED or not REMOTE_OCR_URL:
        return False, {}, "disabled"
    now = time.time()
    cached = remote_ocr_health_cache.get("result")
    if (
        cached is not None
        and REMOTE_OCR_HEALTH_CACHE_SECONDS > 0
        and now - float(remote_ocr_health_cache.get("checked_at", 0.0)) <= REMOTE_OCR_HEALTH_CACHE_SECONDS
    ):
        return cached  # type: ignore[return-value]
    try:
        client = get_remote_http_client(1.5)
        response = client.get(f"{REMOTE_OCR_URL}/health")
        if response.status_code != 200:
            result = (False, {}, f"status={response.status_code}")
            remote_ocr_health_cache.update({"checked_at": now, "result": result})
            return result
        payload = response.json()
    except Exception as exc:
        result = (False, {}, exc.__class__.__name__)
        remote_ocr_health_cache.update({"checked_at": now, "result": result})
        return result
    if not isinstance(payload, dict):
        result = (False, {}, "invalid_json")
        remote_ocr_health_cache.update({"checked_at": now, "result": result})
        return result
    result = (True, payload, "ok")
    remote_ocr_health_cache.update({"checked_at": now, "result": result})
    return result


def today_cache_counts() -> dict[str, int]:
    summary = today_ocr_cache_summary(TODAY_OCR_CACHE_PATH)
    cards = list(summary.first_cards)
    raw_candidates: list[str] = []
    try:
        data = json.loads(TODAY_OCR_CACHE_PATH.read_text(encoding="utf-8")) if summary.exists else {}
        if isinstance(data, dict):
            cards = [str(card) for card in data.get("ocr_cards", []) if isinstance(card, str)]
            raw_candidates = [str(card) for card in data.get("raw_candidates", []) if isinstance(card, str)]
    except Exception:
        raw_candidates = []
    pubg_count = sum(1 for card in cards if valid_card(card))
    psn_count = sum(1 for card in cards if re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", card))
    seen: set[str] = set()
    duplicate_count = 0
    for card in raw_candidates:
        key = canonical_card(card)
        if not key:
            continue
        if key in seen:
            duplicate_count += 1
        seen.add(key)
    return {
        "images": summary.images,
        "cards": len(cards),
        "pubg": pubg_count,
        "psn": psn_count,
        "duplicates": duplicate_count,
    }


def build_status_panel() -> str:
    return build_status_panel_service(
        StatusPanelHooks(
            ensure_today=ensure_remote_ocr_today,
            worker_health=remote_worker_health,
            cache_counts=today_cache_counts,
            service_state=service_active_state,
            git_output=git_output,
            process_memory_mb=process_memory_mb,
            process_uptime_text=process_uptime_text,
            average_remote_latency_ms=avg_remote_latency_ms,
            format_time_value=format_time_value,
            percent_rate=percent_rate,
            status=remote_ocr_status,
            ledger_path=LEDGER_DB_PATH,
            remote_label=REMOTE_OCR_LABEL,
            remote_enabled=REMOTE_OCR_ENABLED,
            ocrspace_available=bool(OCR_SPACE_API_KEYS),
        )
    )


def record_remote_ocr_status(
    ok: bool,
    latency_ms: int,
    card_count: int = 0,
    text_count: int = 0,
    error: str = "",
    health_check: bool = False,
    enhanced_used: bool = False,
    cache_hit: bool = False,
) -> None:
    record_remote_ocr_status_service(
        status=remote_ocr_status,
        logger=logger,
        now_factory=remote_ocr_now,
        ensure_today=ensure_remote_ocr_today,
        ok=ok,
        latency_ms=latency_ms,
        card_count=card_count,
        text_count=text_count,
        error=error,
        health_check=health_check,
        enhanced_used=enhanced_used,
        cache_hit=cache_hit,
    )


def remote_ocr_available(force_probe: bool = False) -> tuple[bool, str]:
    if not REMOTE_OCR_ENABLED or not REMOTE_OCR_URL:
        return False, "disabled"
    if remote_ocr_is_circuit_open() and not force_probe:
        return False, remote_ocr_circuit_reason()
    cached = remote_ocr_health_cache.get("result")
    now = time.time()
    if (
        not force_probe
        and
        cached is not None
        and REMOTE_OCR_HEALTH_CACHE_SECONDS > 0
        and now - float(remote_ocr_health_cache.get("checked_at", 0.0)) <= REMOTE_OCR_HEALTH_CACHE_SECONDS
    ):
        ok, _payload, reason = cached  # type: ignore[misc]
        return bool(ok), str(reason)
    started_at = time.time()
    try:
        client = get_remote_http_client(REMOTE_OCR_TIMEOUT)
        response = client.get(f"{REMOTE_OCR_URL}/health")
        latency_ms = int((time.time() - started_at) * 1000)
        if response.status_code != 200:
            record_remote_ocr_status(False, latency_ms, error=f"health status {response.status_code}", health_check=True)
            mark_remote_ocr_offline(f"health status {response.status_code}")
            remote_ocr_health_cache.update({"checked_at": started_at, "result": (False, {}, f"status={response.status_code}")})
            return False, f"status={response.status_code}"
        record_remote_ocr_status(True, latency_ms, card_count=remote_ocr_status.get("last_card_count", 0), health_check=True)
        mark_remote_ocr_online()
        payload = response.json()
        remote_ocr_health_cache.update({"checked_at": started_at, "result": (True, payload if isinstance(payload, dict) else {}, "ok")})
        return True, "ok"
    except Exception as exc:
        latency_ms = int((time.time() - started_at) * 1000)
        record_remote_ocr_status(False, latency_ms, error=type(exc).__name__, health_check=True)
        mark_remote_ocr_offline(type(exc).__name__)
        remote_ocr_health_cache.update({"checked_at": started_at, "result": (False, {}, type(exc).__name__)})
        return False, type(exc).__name__


def run_remote_ocr(
    image_path: Path,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> OcrResult | None:
    return recognize_remote(
        sys.modules[__name__],
        image_path,
        psn_hint=psn_hint,
        psn_expected_count=psn_expected_count,
        pubg_expected_count=pubg_expected_count,
    )


def run_ocr(
    image_path: Path,
    psn_hint: bool = False,
    psn_expected_count: int | None = None,
    pubg_expected_count: int | None = None,
) -> OcrResult:
    return route_ocr(
        sys.modules[__name__],
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


async def recognize_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[OcrResult, Path | None]:
    image_path: Path | None = None
    audit_record = None
    async with ocr_semaphore:
        image_path = await download_photo(update, context)
        caption = update.message.caption if update.message and update.message.caption else ""
        psn_hint = "PSN" in normalize_text(caption)
        psn_expected_count = parse_psn_expected_count(caption)
        pubg_expected_count = parse_pubg_expected_count(caption)
        message = update.message
        photo = message.photo[-1] if message and message.photo else None
        chat = update.effective_chat
        user = update.effective_user
        try:
            audit_record = await asyncio.to_thread(
                stage_ocr_audit_image,
                image_path,
                message_id=message.message_id if message else 0,
                file_unique_id=getattr(photo, "file_unique_id", ""),
                media_group_id=str(getattr(message, "media_group_id", "") or ""),
                source_chat_id=getattr(chat, "id", 0),
                source_chat_title=str(getattr(chat, "title", "") or ""),
                source_user_id=getattr(user, "id", 0),
                source_username=str(getattr(user, "username", "") or ""),
                message_created_at=getattr(message, "date", None),
            )
        except Exception:
            logger.exception("Failed to stage OCR audit image")
        try:
            cached_image = await asyncio.to_thread(
                cache_original_image,
                image_path,
                chat_id=int(getattr(chat, "id", 0) or 0),
                message_id=int(getattr(message, "message_id", 0) or 0),
                image_index=0,
                file_unique_id=str(getattr(photo, "file_unique_id", "") or ""),
                root=CARD_IMAGE_CACHE_DIR,
            )
            card_manager_images_by_update[id(update)] = cached_image
        except Exception:
            # 管理端缓存是旁路：失败绝不能妨碍现有 OCR 和 Telegram 回复。
            logger.exception("Failed to cache original image for card manager")
        try:
            result = await asyncio.to_thread(run_ocr, image_path, psn_hint, psn_expected_count, pubg_expected_count)
            return replace(result, source_caption=caption.strip()), audit_record
        except Exception as exc:
            mark_ocr_audit_failed(audit_record, str(exc))
            raise
        finally:
            if image_path is not None:
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
    return format_card_codes([card])


def format_card_codes(cards: list[str]) -> str:
    return f"<blockquote>{html.escape(chr(10).join(cards))}</blockquote>"


def format_underlined_card_code(card: str) -> str:
    return f"<u>{html.escape(card)}</u>"


def source_username_only(source_user: str) -> str:
    return source_username_only_service(source_user)


def result_pipeline_hooks() -> ResultPipelineHooks:
    return ResultPipelineHooks(
        occurrence_type=OrderedCardOccurrence,
        valid_card=valid_card,
        canonical_card=canonical_card,
        psn_key=psn_key,
        psn_is_pubg_substring=psn_is_pubg_substring,
        filter_psn_pubg_substrings=filter_psn_pubg_substrings,
        exact_unique_psn=exact_unique_psn,
        exact_unique_text=exact_unique_text,
        limit_psn_ordered=limit_psn_ordered,
        format_duplicate_lines=format_duplicate_lines,
        format_card_codes=format_card_codes,
        result_location=result_location,
        fuzzy_suffix=FUZZY_SUFFIX,
        success_prefix=SUCCESS_PREFIX,
        count_suffix=COUNT_SUFFIX,
        uncertain_prefix=UNCERTAIN_PREFIX,
        uncertain_suffix=UNCERTAIN_SUFFIX,
        manual_review_summary=MANUAL_REVIEW_SUMMARY,
        pubg_label=PUBG_LABEL,
        psn_label=PSN_LABEL,
    )


def ordered_pubg_occurrences(results: list[OcrResult]) -> list[OrderedCardOccurrence]:
    return pipeline_ordered_pubg_occurrences(results, result_pipeline_hooks())


def ordered_psn_occurrences(results: list[OcrResult]) -> list[OrderedCardOccurrence]:
    return pipeline_ordered_psn_occurrences(results, result_pipeline_hooks())


def format_reply(results: list[OcrResult]) -> str:
    return pipeline_format_reply(results, result_pipeline_hooks())


def result_card_lines(results: list[OcrResult]) -> tuple[list[str], list[str]]:
    return pipeline_result_card_lines(results, result_pipeline_hooks())


def has_card_results(results: list[OcrResult]) -> bool:
    pubg_cards, psn_lines = result_card_lines(results)
    return bool(pubg_cards or psn_lines)


def apply_card_corrections(chat_id: int, result: OcrResult) -> OcrResult:
    return preserve_one_time_card_result(chat_id, result)


def card_history_day_key(chat_id: int, now: datetime | None = None) -> str:
    return card_history_day_key_service(chat_id, card_history_hooks(), now)


def format_history_time(created_at: str) -> str:
    return format_history_time_service(created_at, LEDGER_TZ)


def card_history_hooks() -> CardHistoryHooks:
    return CardHistoryHooks(
        store=ledger_store,
        ledger_timezone=LEDGER_TZ,
        fuzzy_suffix=FUZZY_SUFFIX,
        result_card_lines=result_card_lines,
        user_label=user_label,
        format_card=format_underlined_card_code,
    )


def register_card_history(updates: list[Update], results: list[OcrResult]) -> list[CardHistoryDuplicate]:
    return register_card_history_service(updates, results, card_history_hooks())


def append_history_duplicates(reply: str, duplicates: list[CardHistoryDuplicate]) -> str:
    return append_history_duplicates_service(reply, duplicates, card_history_hooks())


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


async def reply_okx_price(message) -> None:
    try:
        prices, source = await fetch_okx_usdt_cny_prices()
    except Exception:
        logger.exception("OKX USDT/CNY price fetch failed")
        await message.reply_text("币价获取失败，请稍后再试。")
        return
    await message.reply_text(format_okx_prices(prices, source))


async def set_realtime_ledger_rate(update: Update) -> bool:
    if not update.message or not update.effective_chat:
        return False
    if not is_realtime_rate_command(update.message.text or ""):
        return False
    if update.effective_chat.id >= 0:
        await update.message.reply_text("请在群内设置实时汇率。")
        return True
    user_id = update.effective_user.id if update.effective_user else 0
    owner_ids = ledger_owner_ids(update.effective_chat.id)
    if not ledger_store.is_operator(update.effective_chat.id, user_id, owner_ids):
        await update.message.reply_text("无权限设置实时汇率。")
        return True
    old_rate, _fee = ledger_store.get_settings(update.effective_chat.id)
    try:
        prices, source = await fetch_okx_usdt_cny_prices()
    except Exception:
        logger.exception("OKX realtime ledger rate fetch failed")
        await update.message.reply_text(f"❌ 获取欧意实时汇率失败，已保留当前群原汇率：{_format_calc_result(old_rate)}")
        return True
    if not prices:
        await update.message.reply_text(f"❌ 获取欧意实时汇率失败，已保留当前群原汇率：{_format_calc_result(old_rate)}")
        return True
    new_rate = ledger_store.set_rate(update.effective_chat.id, prices[0])
    updated_at = datetime.now(LEDGER_TZ).strftime("%Y-%m-%d %H:%M:%S")
    await update.message.reply_text(
        "\n".join(
            [
                "✅ 当前群实时汇率已更新",
                "",
                f"汇率：{_format_calc_result(new_rate)}",
                f"来源：欧意 USDT/CNY 最新 1 档（{source}）",
                f"更新时间：{updated_at}",
            ]
        )
    )
    return True


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


def ocr_debug_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return ocr_command_service.debug_input(update, context)


async def ocr_debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.debug_command(
        update,
        context,
        is_owner=is_owner_update,
        formatter=format_ocr_debug,
    )


async def ocr_candidates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.candidates_command(
        update,
        context,
        is_owner=is_owner_update,
        formatter=format_ocr_candidates_debug,
    )


async def ocr_font_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.text_command(
        update,
        is_owner=is_owner_update,
        build_text=lambda: format_ocr_font_stats_plus(font_repository),
    )


async def ocr_review_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.text_command(
        update,
        is_owner=is_owner_update,
        build_text=lambda: format_ocr_review(OCR_CANDIDATES_PATH),
    )


async def ocr_export_fonts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.export_fonts_command(
        update,
        is_owner=is_owner_update,
        export_templates=export_font_templates,
        templates_path=Path("outputs") / "font_templates.json",
    )


async def ocr_import_fonts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.import_fonts_command(
        update,
        context,
        is_owner=is_owner_update,
        import_templates=import_font_templates,
        templates_path=Path("outputs") / "font_templates.json",
    )


async def ocr_version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.text_command(
        update,
        is_owner=is_owner_update,
        build_text=lambda: format_ocr_version(Path("."), current_version=BOT_VERSION),
    )


async def ocr_cache_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.cache_today_command(
        update,
        is_owner=is_owner_update,
        cache_path=TODAY_OCR_CACHE_PATH,
        summary_reader=today_ocr_cache_summary,
    )


async def ocr_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.health_command(
        update,
        is_owner=is_owner_update,
        provider=OCR_PROVIDER,
        ocrspace_key_count=len(OCR_SPACE_API_KEYS),
        local_fallback=LOCAL_FALLBACK,
        cache_path=TODAY_OCR_CACHE_PATH,
        summary_reader=today_ocr_cache_summary,
    )


async def remote_ocr_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.remote_status_command(
        update,
        is_owner=is_owner_update,
        remote_available=remote_ocr_available,
        remote_enabled=REMOTE_OCR_ENABLED,
        remote_url=REMOTE_OCR_URL,
        status=remote_ocr_status,
        average_latency=avg_remote_latency_ms,
        percent=percent_rate,
        current_provider=current_ocr_provider,
    )


async def status_panel_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if is_owner_update(update):
        return True
    if not update.effective_chat or not update.effective_user or not context:
        return False
    try:
        member = await asyncio.wait_for(
            context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id),
            timeout=1.5,
        )
    except Exception:
        return False
    return getattr(member, "status", "") in {"administrator", "creator"}


async def status_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await status_panel_allowed(update, context):
        await update.message.reply_text("无权限。")
        return
    try:
        text = await asyncio.to_thread(build_status_panel)
    except Exception as exc:
        logger.exception("Failed to build status panel")
        text = f"状态查询失败：{exc.__class__.__name__}"
    await update.message.reply_text(text)


def command_body(update: Update, command: str) -> str:
    return ocr_command_service.command_body(update, command)


def learn_cards_body(update: Update) -> str:
    return ocr_command_service.learn_cards_body(update)


async def learn_cards_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.learn_cards_command(
        update,
        is_owner=is_owner_update,
        preview_builder=build_learning_preview,
        pending_texts=pending_learning_texts,
    )


async def auto_learn_cards_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    return


async def learn_confirm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.learn_confirm_command(
        update,
        is_owner=is_owner_update,
        pending_texts=pending_learning_texts,
        execute=execute_learning,
    )


async def learn_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.learn_cancel_command(
        update,
        is_owner=is_owner_update,
        pending_texts=pending_learning_texts,
    )


async def ocr_learning_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await ocr_command_service.text_command(
        update,
        is_owner=is_owner_update,
        build_text=format_learning_stats,
    )


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
        bool(getattr(update.effective_user, "is_bot", False)),
    )


def ensure_private_ledger_owner(update: Update) -> None:
    if not update.effective_chat or not update.effective_user:
        return
    if getattr(update.effective_chat, "type", "") == "private":
        ledger_store.set_chat_owner(update.effective_chat.id, update.effective_user.id)


def remember_bot_chat(update: Update) -> None:
    chat = update.effective_chat
    if not chat:
        return
    chat_type = getattr(chat, "type", "")
    if chat_type not in {"group", "supergroup"}:
        return
    title = getattr(chat, "title", "") or getattr(chat, "full_name", "") or str(chat.id)
    ledger_store.remember_bot_chat(chat.id, title, chat_type)


def owner_user_id() -> int | None:
    return parse_chat_id(OWNER_CHAT_ID)


def is_owner_update(update: Update | None) -> bool:
    return update_user_is_owner(update, OWNER_CHAT_ID)


async def reply_ledger(message, text: str) -> None:
    await message.reply_text(
        text,
        reply_markup=ledger_keyboard(),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def handle_ledger_text(update: Update, context: ContextTypes.DEFAULT_TYPE, allow_trc20: bool = True) -> bool:
    hooks = LedgerTextHooks(
        store=ledger_store,
        remember_bot_chat=remember_bot_chat,
        remember_ledger_user=remember_ledger_user,
        ensure_private_owner=ensure_private_ledger_owner,
        owner_ids=ledger_owner_ids,
        extract_trc20_address=extract_trc20_address,
        reply_trc20_verify_image=reply_trc20_verify_image,
        set_realtime_rate=set_realtime_ledger_rate,
        is_price_command=is_price_command,
        reply_okx_price=reply_okx_price,
        calculate_expression=calculate_expression,
        actor_from_update=ledger_actor,
        actor_from_message=ledger_actor_from_message,
        handle_command_text=handle_ledger_command_text,
        reply_ledger=reply_ledger,
    )
    return await handle_ledger_text_service(update, hooks, allow_trc20=allow_trc20)


async def handle_class_mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    mode = _class_mode_command(update.message.text or "")
    if not mode:
        return
    if not is_group_update(update):
        if is_owner_update(update):
            for row in ledger_store.list_active_bot_groups():
                chat_id = int(row["chat_id"])
                ledger_store.set_recognition_enabled(chat_id, mode == "on")
                ledger_store.set_class_mode_notice(chat_id, mode)
        raise ApplicationHandlerStop
    remember_bot_chat(update)
    remember_ledger_user(update)
    if update.effective_user and update.effective_user.id not in ledger_owner_ids(update.effective_chat.id):
        await update.message.reply_text("只有本群管理权限用户可以使用上课/下课。")
        raise ApplicationHandlerStop
    ledger_store.set_recognition_enabled(update.effective_chat.id, mode == "on")
    ledger_store.set_class_mode_notice(update.effective_chat.id, mode)
    raise ApplicationHandlerStop


async def handle_class_mode_notice_once(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    if not is_group_update(update):
        return
    if getattr(update.message, "new_chat_members", None) or getattr(update.message, "left_chat_member", None):
        return
    if update.effective_user and getattr(update.effective_user, "is_bot", False):
        return
    if (update.message.text or "").strip().startswith("/"):
        return
    if _class_mode_command(update.message.text or ""):
        return
    mode = ledger_store.consume_class_mode_notice(update.effective_chat.id)
    if mode == "on":
        await update.message.reply_text(CLASS_ON_NOTICE)
    elif mode == "off":
        await update.message.reply_text(CLASS_OFF_NOTICE)


async def handle_priority_ledger_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await handle_broadcast_text(update, context):
        raise ApplicationHandlerStop
    handled = await handle_ledger_text(update, context, allow_trc20=False)
    if handled:
        raise ApplicationHandlerStop


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


def extract_broadcast_all_text(text: str, command: str) -> str:
    stripped = text.strip()
    if stripped == command:
        return ""
    if stripped.startswith(command):
        return stripped[len(command) :].lstrip(" \t\r\n")
    return stripped


async def handle_new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    remember_bot_chat(update)
    bot_user = await context.bot.get_me()
    await handle_new_chat_members_service(
        update,
        context,
        GroupLifecycleHooks(
            store=ledger_store,
            welcome_sent_at=welcome_sent_at,
            welcome_message=group_welcome_message,
        ),
        bot_user.id,
    )


async def handle_left_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    remember_bot_chat(update)
    bot_user = await context.bot.get_me()
    await handle_left_chat_member_service(
        update,
        context,
        GroupLifecycleHooks(
            store=ledger_store,
            welcome_sent_at=welcome_sent_at,
            welcome_message=group_welcome_message,
        ),
        bot_user.id,
    )


async def handle_bot_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_bot_chat_member_service(
        update,
        context,
        GroupLifecycleHooks(
            store=ledger_store,
            welcome_sent_at=welcome_sent_at,
            welcome_message=group_welcome_message,
        ),
    )


def update_is_from_owner(update: Update | None) -> bool:
    return update_user_or_chat_is_owner(update, OWNER_CHAT_ID)


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
    source_text = await resolve_audit_source_text(first, context.bot)
    text = source_text + "\n\n" + append_history_duplicates(format_reply(results), history_duplicates or [])
    if AUDIT_BOT_TOKEN:
        try:
            photo_paths = await download_audit_photo_paths(updates, context)
            if photo_paths:
                try:
                    await send_audit_bot_photos(target_chat_id_int, photo_paths, text)
                finally:
                    cleanup_audit_photo_paths(photo_paths)
            else:
                await send_audit_bot_message(target_chat_id_int, text)
        except Exception:
            logger.exception("Audit bot forwarding failed")
            try:
                await send_audit_bot_message(target_chat_id_int, text)
            except Exception:
                logger.exception("Audit bot text fallback failed")
        return
    await send_html_chunks(context, target_chat_id_int, text)


async def send_audit_bot_message(chat_id: int, text: str) -> None:
    await _send_audit_bot_message(
        chat_id,
        text,
        bot_token=AUDIT_BOT_TOKEN,
        timeout=TELEGRAM_TIMEOUT,
    )


async def send_audit_bot_photos(chat_id: int, photo_paths: list[Path], caption_text: str) -> None:
    await _send_audit_bot_photos(
        chat_id,
        photo_paths,
        caption_text,
        bot_token=AUDIT_BOT_TOKEN,
        timeout=TELEGRAM_TIMEOUT,
        send_message=send_audit_bot_message,
    )


def photo_rate_limit_reason(update: Update, now: float | None = None) -> str | None:
    return check_photo_rate_limit(
        update,
        now=now,
        is_owner=is_owner_update,
        window_seconds=PHOTO_RATE_WINDOW_SECONDS,
        chat_limit=PHOTO_RATE_LIMIT_PER_CHAT,
        user_limit=PHOTO_RATE_LIMIT_PER_USER,
    )


async def warn_photo_rate_limited(message, key: tuple[str, int], text: str) -> None:
    await _warn_photo_rate_limited(
        message,
        key,
        text,
        window_seconds=PHOTO_RATE_WINDOW_SECONDS,
    )


async def flush_chat_batch(chat_id: int, context: ContextTypes.DEFAULT_TYPE, wait_seconds: float) -> None:
    async with chat_flush_locks[chat_id]:
        await asyncio.sleep(wait_seconds)
        updates = chat_buffers.pop(chat_id, [])
        chat_tasks.pop(chat_id, None)
        progress = ocr_live_progresses.pop(chat_id, None)
        if not updates:
            return
        updates = order_batch_updates(updates, photo_display_order)
        forget_photo_sequences(updates)
        message = updates[-1].message
        if not message:
            return

        await message.chat.send_action("typing")
        if progress is None:
            progress = LiveOcrBatchProgress(message)
            for batch_update in updates:
                progress.register_image(batch_update.message or message)
            await progress.publish(force=True)
        batch_id = f"{chat_id}_{int(time.time() * 1000)}"

        async def recognize_batch_update(batch_index: int, update: Update) -> tuple[int, OcrResult, OcrResult, bool]:
            try:
                result, audit_record = await ocr_batch_jobs.take(
                    id(update),
                    lambda: recognize_update(update, context),
                )
                result = replace(result, sequence_index=batch_index)
                corrected = apply_card_corrections(chat_id, result)
                try:
                    await asyncio.to_thread(
                        finalize_ocr_audit,
                        audit_record,
                        batch_id=batch_id,
                        sequence_index=batch_index,
                        raw_result=result,
                        final_result=corrected,
                    )
                except Exception:
                    logger.exception("Failed to finalize OCR audit record")
                corrected_pubg, corrected_psn = result_card_lines([corrected])
                if not corrected_pubg and not corrected_psn and result.raw_text.strip():
                    logger.info("Unrecognized OCR raw text: %s", result.raw_text.strip().replace("\n", " | ")[:1000])
                return batch_index, corrected, result, True
            except Exception:
                logger.exception("Batch image OCR failed")
                return batch_index, OcrResult(cards=tuple(), sequence_index=batch_index), OcrResult(cards=tuple()), False

        batch_results = await asyncio.gather(
            *(recognize_batch_update(batch_index, update) for batch_index, update in enumerate(updates, start=1))
        )
        batch_results = order_batch_results(batch_results)
        results: list[OcrResult] = []
        raw_results: list[OcrResult] = []
        for _batch_index, corrected, raw_result, success in batch_results:
            results.append(corrected)
            raw_results.append(raw_result)
            if success:
                try:
                    append_today_ocr_cache(
                        list(corrected.cards) + [psn_key(line) or line for line in corrected.psn_ordered],
                        raw_candidates=exact_unique_text(list(raw_result.cards) + list(raw_result.psn_ordered)),
                        image_count=1,
                        path=TODAY_OCR_CACHE_PATH,
                    )
                except Exception:
                    logger.exception("Failed to write today OCR cache")
            else:
                try:
                    append_today_ocr_cache([], image_count=1, path=TODAY_OCR_CACHE_PATH)
                except Exception:
                    logger.exception("Failed to write empty today OCR cache")

        has_results = has_card_results(results)
        await progress.finish(has_results)

        # 待核对图只在原聊天回复原图；不经过审计转发路径，也不影响同批其它结果。
        for batch_index, update in enumerate(updates, start=1):
            item = manual_review_notifier.needs_review(results[batch_index - 1])
            if item is not None:
                await manual_review_notifier.notify(
                    update,
                    context,
                    batch_index=batch_index,
                    item=item,
                )

        manager_images = {
            id(update): card_manager_images_by_update.pop(id(update))
            for update in updates
            if id(update) in card_manager_images_by_update
        }

        async def persist_card_manager_records() -> None:
            try:
                await asyncio.to_thread(
                    persist_ocr_batch,
                    card_manager_store,
                    updates=updates,
                    final_results=results,
                    raw_results=raw_results,
                    images_by_update=manager_images,
                    result_card_lines=result_card_lines,
                )
            except Exception:
                # 桌面管理端异常不能成为 OCR 成功或 Telegram 回复的前置条件。
                logger.exception("Failed to persist card manager records")

        asyncio.create_task(persist_card_manager_records())

        # 管理端会保留未识别图片供人工录入；这条旁路任务不参与原机器人流程。
        if not has_results:
            return

        history_duplicates = register_card_history(updates, results)
        if should_reply_to_source(updates):
            await reply_html_chunks(
                message,
                format_source_reply(updates, results, history_duplicates),
            )
        await notify_owner(updates, results, context, history_duplicates)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    remember_bot_chat(update)
    remember_ledger_user(update)
    chat_id = update.message.chat_id
    if not ledger_store.is_recognition_enabled(chat_id):
        return
    rate_limit_reason = photo_rate_limit_reason(update)
    if rate_limit_reason:
        await warn_photo_rate_limited(update.message, ("rate", chat_id), rate_limit_reason)
        return
    owner_photo = is_owner_update(update)
    if not owner_photo and batch_capacity_reached(len(chat_buffers[chat_id]), PHOTO_BATCH_MAX_IMAGES):
        await warn_photo_rate_limited(
            update.message,
            ("batch", chat_id),
            f"当前批次图片已达到{PHOTO_BATCH_MAX_IMAGES}张，后续图片已保护性忽略，请等本批识别完成后再发。",
        )
        return
    await assign_photo_sequence(update)
    chat_buffers[chat_id].append(update)
    progress = ocr_live_progresses.get(chat_id)
    if progress is None:
        progress = LiveOcrBatchProgress(update.message)
        ocr_live_progresses[chat_id] = progress
    progress.register_image(update.message)

    async def recognize_with_progress():
        try:
            recognized = await recognize_update(update, context)
            result = recognized[0]
            await progress.mark_done(
                has_card_result=bool(result.cards or result.psn_cards or result.psn_uncertain)
            )
            return recognized
        except Exception:
            await progress.mark_done()
            raise

    ocr_batch_jobs.start(id(update), recognize_with_progress)
    old_task = chat_tasks.get(chat_id)
    if old_task and not old_task.done():
        old_task.cancel()
    owner_bulk_photo = owner_photo and bool(
        getattr(update.message, "forward_origin", None) or getattr(update.message, "media_group_id", None)
    )
    wait_seconds = batch_debounce_seconds(
        owner_photo=owner_photo,
        owner_bulk_photo=owner_bulk_photo,
        batch_size=len(chat_buffers[chat_id]),
        single_wait_seconds=SINGLE_WAIT_SECONDS,
        multi_wait_seconds=MULTI_BATCH_WAIT_SECONDS,
        owner_bulk_wait_seconds=OWNER_FORWARD_BATCH_WAIT_SECONDS,
    )
    chat_tasks[chat_id] = asyncio.create_task(flush_chat_batch(chat_id, context, wait_seconds))


notify_all_cooldowns: dict[int, float] = {}


def is_group_update(update: Update | None) -> bool:
    if not update or not update.effective_chat:
        return False
    return getattr(update.effective_chat, "type", "") in {"group", "supergroup"}


def can_use_group_notify(update: Update | None) -> bool:
    if not update or not update.effective_chat or not update.effective_user:
        return False
    if is_owner_update(update):
        return True
    return ledger_store.is_operator(
        update.effective_chat.id,
        update.effective_user.id,
        ledger_owner_ids(update.effective_chat.id),
    )


def broadcast_controller() -> BroadcastController:
    """按当前运行时依赖创建控制器，确保测试替换与兼容变量继续生效。"""
    return BroadcastController(
        ledger_store=ledger_store,
        is_owner_update=is_owner_update,
        is_private_update=update_is_private_chat,
        extract_broadcast_text=extract_broadcast_all_text,
        logger=logger,
    )


def notify_controller() -> NotifyController:
    """按当前运行时依赖创建通知控制器，保留测试替换能力。"""
    return NotifyController(
        ledger_store=ledger_store,
        is_group_update=is_group_update,
        can_use_group_notify=can_use_group_notify,
        remember_bot_chat=remember_bot_chat,
        remember_ledger_user=remember_ledger_user,
        cooldowns=notify_all_cooldowns,
    )


def broadcast_group_keyboard(selected: set[int] | None = None) -> InlineKeyboardMarkup:
    return broadcast_controller().group_keyboard(selected)


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await broadcast_controller().start(update, context)


async def broadcast_preview_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await broadcast_controller().preview(update, context)


async def broadcast_cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await broadcast_controller().cancel(update, context)


def selected_broadcast_titles(selected: set[int]) -> list[str]:
    return broadcast_controller().selected_titles(selected)


async def handle_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await broadcast_controller().handle_callback(update, context)


async def handle_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return await broadcast_controller().handle_text(update, context)


def extract_notify_all_text(text: str) -> str:
    return notify_extract_all_text(text)


def html_mention_for_member(row) -> str:
    return notify_html_mention(row)


def chunked(values: list[str], size: int) -> list[list[str]]:
    return notify_chunked(values, size)


async def notify_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await notify_controller().notify_all(update, context)


async def notify_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await notify_controller().notify_members(update, context)


def main() -> None:
    from config.application import build_telegram_application
    from config.logging_config import configure_logging
    from handlers.registry import register_handlers

    configure_logging()
    app = build_telegram_application(
        register_handlers=register_handlers,
        post_init=start_background_tasks,
        post_shutdown=stop_background_tasks,
    )
    logger.info("Bot is starting. Version=%s.", BOT_VERSION)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

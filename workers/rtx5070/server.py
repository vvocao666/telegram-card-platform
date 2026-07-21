from fastapi import FastAPI, HTTPException, UploadFile, File
from paddlex import create_pipeline
from ocr_fast_path import enhance_reason
from ocr_line_recovery import recover_suspicious_pubg_lines
from worker_config import load_worker_config, load_worker_env
from worker_metrics import WorkerMetrics
from worker_queue import WorkerQueueFull, WorkerTaskQueue
from cpu_ocr import CpuOcrEngine
from cpu_preprocess import CpuPreparationPool, cpu_evidence_image_path
from cpu_review_policy import assess_cpu_review_risk
from cpu_shadow_dispatcher import CpuShadowDispatcher
from gpu_variant_review import review_gpu_variant_conflict, result_payload
from thin_strip_input import prepare_worker_input
import asyncio
import copy
import hashlib
import os
import re
import tempfile
import threading
import time

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

try:
    import paddle
except Exception:
    paddle = None


load_worker_env()
WORKER_CONFIG = load_worker_config()
WORKER_METRICS = WorkerMetrics()
CPU_OCR = CpuOcrEngine(WORKER_CONFIG, WORKER_METRICS)
CPU_PREPROCESSOR = CpuPreparationPool(WORKER_CONFIG, WORKER_METRICS)
CPU_SHADOW_DISPATCHER = CpuShadowDispatcher(CPU_OCR, WORKER_CONFIG, WORKER_METRICS)
WORKER_QUEUE = WorkerTaskQueue(WORKER_CONFIG.queue_workers, WORKER_CONFIG.queue_capacity)

app = FastAPI()
pipeline = create_pipeline("OCR")
paddle_semaphore = threading.Semaphore(1)

CARD_RE = re.compile(r"(S07[0-9A-Z]{3}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{5}|[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})")

CACHE_TTL_SECONDS = 24 * 60 * 60
cache_lock = threading.Lock()
ocr_cache = {}


@app.on_event("shutdown")
def shutdown_worker_resources():
    CPU_SHADOW_DISPATCHER.close()


@app.get("/")
def root():
    return {"status": "ok", "engine": "paddlex_ocr", "gpu": "RTX5070"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "gpu": "RTX5070",
        "engine": "paddlex_ocr",
        "pipeline_loaded": True,
        "opencv": cv2 is not None,
        "cpu_ocr": CPU_OCR.status(),
        "stats": WORKER_METRICS.snapshot(),
        "queue": WORKER_QUEUE.snapshot(),
    }


@app.post("/ocr")
async def ocr(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    image_bytes = await file.read()
    WORKER_METRICS.increment("requests")
    try:
        if WORKER_CONFIG.queue_v2_enabled:
            return await WORKER_QUEUE.run(_process_ocr, image_bytes, suffix)
        return await asyncio.to_thread(_process_ocr, image_bytes, suffix)
    except WorkerQueueFull as exc:
        WORKER_METRICS.increment("queue_rejected")
        raise HTTPException(status_code=429, detail="worker_busy") from exc


def _process_ocr(image_bytes, suffix):
    start = time.time()
    image_sha1 = _cache_key(image_bytes)

    cached = _cache_get(image_sha1)
    if cached is not None:
        WORKER_METRICS.increment("cache_hits")
        response = copy.deepcopy(cached)
        response["cached"] = True
        response["latency_ms"] = int((time.time() - start) * 1000)
        return response

    metrics = _image_metrics(image_bytes)
    prepared_input = prepare_worker_input(image_bytes, suffix, metrics)
    original_path = _write_temp_file(prepared_input.data, prepared_input.suffix)
    enhanced_path = None

    try:
        prepared_enhancement = CPU_PREPROCESSOR.start(
            prepared_input.data, prepared_input.suffix, metrics
        )
        original_result, latency_original_ms = _run_ocr_path(original_path)
        enhance_reason = _enhance_reason(metrics, original_result)
        enhanced_used = enhance_reason != "not_needed"
        latency_enhanced_ms = 0
        enhanced_result = _empty_ocr_result()

        if enhanced_used:
            enhanced_path = CPU_PREPROCESSOR.result(prepared_enhancement)
            if not enhanced_path:
                enhanced_path = _write_enhanced_image(
                    prepared_input.data, prepared_input.suffix
                )
            enhanced_result, latency_enhanced_ms = _run_ocr_path(enhanced_path or original_path)
            best, best_engine, selection = _choose_best_result(original_result, enhanced_result)
        else:
            best = original_result
            best_engine = "original"
            selection = _selection_payload(original_result, enhanced_result)

        variant_review = review_gpu_variant_conflict(
            original_path,
            original_result,
            enhanced_result,
            _run_ocr_path,
        )
        if variant_review.resolved:
            if variant_review.selected_engine == "original":
                best = original_result
            else:
                best = enhanced_result
            best_engine = variant_review.selected_engine

        best, line_recoveries = recover_suspicious_pubg_lines(
            enhanced_path if best_engine == "enhanced" and enhanced_path else original_path,
            copy.deepcopy(best),
            _run_ocr_path,
        )
        cpu_review = assess_cpu_review_risk(
            best,
            original_result,
            enhanced_result,
            line_recoveries=line_recoveries,
            image_metrics=metrics,
            low_confidence=WORKER_CONFIG.cpu_low_confidence,
            variant_conflict_resolved=variant_review.resolved,
        )
        cpu_payload = _cpu_evidence(
            cpu_evidence_image_path(original_path, enhanced_path, best_engine),
            prepared_input.data,
            prepared_input.suffix,
            best,
            cpu_review.review_required,
            cpu_review.reasons,
        )

        response = {
            "ok": True,
            "engine": "paddlex_ocr",
            "gpu": "RTX5070",
            "latency_ms": int((time.time() - start) * 1000),
            "text_count": best["text_count"],
            "card_count": best["card_count"],
            "texts": best["texts"],
            "cards": best["cards"],
            "latency_original_ms": latency_original_ms,
            "latency_enhanced_ms": latency_enhanced_ms,
            "best_engine": best_engine,
            "selection": selection,
            "variant_review": result_payload(variant_review),
            "ocr_original": original_result,
            "ocr_enhanced": enhanced_result,
            "enhanced_used": enhanced_used,
            "enhance_reason": enhance_reason,
            "line_recoveries": line_recoveries,
            "cpu_ocr": cpu_payload,
            "thin_strip_padding_applied": prepared_input.padding_applied,
            "cached": False,
        }
        _cache_set(image_sha1, response)
        return response

    finally:
        _remove_file(original_path)
        if enhanced_path and enhanced_path != original_path:
            _remove_file(enhanced_path)


def _run_ocr_path(path):
    start = time.time()
    # PaddleX GPU 推理串行进入，OpenCV 预处理仍由 CPU 完成。
    wait_started = WORKER_METRICS.gpu_wait_started()
    paddle_semaphore.acquire()
    WORKER_METRICS.gpu_wait_finished(wait_started)
    gpu_started = WORKER_METRICS.gpu_started()
    try:
        results = list(pipeline.predict(path))
    finally:
        WORKER_METRICS.gpu_finished(gpu_started)
        paddle_semaphore.release()
    texts = []
    cards = []

    for item in results:
        rec_texts = item.get("rec_texts", [])
        rec_scores = item.get("rec_scores", [])
        rec_boxes = item.get("rec_boxes", [])

        for index, (text, score) in enumerate(zip(rec_texts, rec_scores)):
            clean = _clean_text(text)
            score = float(score)
            text_item = {"text": clean, "score": score}
            if index < len(rec_boxes):
                box = rec_boxes[index]
                text_item["box"] = box.tolist() if hasattr(box, "tolist") else list(box)
            texts.append(text_item)

            for card in CARD_RE.findall(clean):
                cards.append({"text": card, "score": score})

    return {
        "text_count": len(texts),
        "card_count": len(cards),
        "avg_score": _avg_score(texts),
        "max_score": _max_score(texts),
        "texts": texts,
        "cards": cards,
    }, int((time.time() - start) * 1000)


def _choose_best_result(original, enhanced):
    original_consistency = _consistency_score(original, enhanced)
    enhanced_consistency = _consistency_score(enhanced, original)
    original_score = _selection_score(original, original_consistency)
    enhanced_score = _selection_score(enhanced, enhanced_consistency)
    selection = _selection_payload(
        original,
        enhanced,
        original_consistency=original_consistency,
        enhanced_consistency=enhanced_consistency,
        original_score=original_score,
        enhanced_score=enhanced_score,
    )

    if enhanced_score > original_score:
        return enhanced, "enhanced", selection
    return original, "original", selection


def _selection_payload(
    original,
    enhanced,
    original_consistency=0.0,
    enhanced_consistency=0.0,
    original_score=None,
    enhanced_score=None,
):
    if original_score is None:
        original_score = _selection_score(original, original_consistency)
    if enhanced_score is None:
        enhanced_score = _selection_score(enhanced, enhanced_consistency)
    return {
        "original": {
            "avg_score": original["avg_score"],
            "max_score": original["max_score"],
            "card_count": original["card_count"],
            "consistency": original_consistency,
            "selection_score": original_score,
        },
        "enhanced": {
            "avg_score": enhanced["avg_score"],
            "max_score": enhanced["max_score"],
            "card_count": enhanced["card_count"],
            "consistency": enhanced_consistency,
            "selection_score": enhanced_score,
        },
    }


def _selection_score(result, consistency):
    card_factor = min(result["card_count"], 20) / 20
    if result["card_count"] == 0:
        card_factor = -0.5
    return (
        result["avg_score"] * 45
        + result["max_score"] * 20
        + card_factor * 20
        + consistency * 15
    )


def _consistency_score(left, right):
    left_cards = {item["text"] for item in left["cards"]}
    right_cards = {item["text"] for item in right["cards"]}
    if left_cards or right_cards:
        union = left_cards | right_cards
        if not union:
            return 0.0
        return len(left_cards & right_cards) / len(union)

    left_texts = {item["text"] for item in left["texts"]}
    right_texts = {item["text"] for item in right["texts"]}
    union = left_texts | right_texts
    if not union:
        return 0.0
    return len(left_texts & right_texts) / len(union)


def _image_metrics(data):
    metrics = {"width": 0, "height": 0, "image_variance": 0.0}
    if cv2 is None or np is None:
        return metrics
    try:
        buffer = np.frombuffer(data, dtype=np.uint8)
        image = cv2.imdecode(buffer, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return metrics
        height, width = image.shape[:2]
        metrics["width"] = int(width)
        metrics["height"] = int(height)
        metrics["image_variance"] = float(cv2.Laplacian(image, cv2.CV_64F).var())
        return metrics
    except Exception:
        return metrics


def _enhance_reason(metrics, original_result):
    return enhance_reason(metrics, original_result)


def _avg_score(items):
    if not items:
        return 0.0
    return sum(item["score"] for item in items) / len(items)


def _max_score(items):
    if not items:
        return 0.0
    return max(item["score"] for item in items)


def _empty_ocr_result():
    return {"text_count": 0, "card_count": 0, "avg_score": 0.0, "max_score": 0.0, "texts": [], "cards": []}


def _cpu_evidence(image_path, image_bytes, suffix, result, review_required, reasons):
    """CPU 的结果只作为可审计的同 ROI 证据，正式 cards 不在此处改写。"""
    payload = CPU_OCR.status()
    payload.update(
        {
            "review_required": bool(review_required),
            "review_reasons": list(reasons),
            "deferred": False,
            "latency_ms": 0,
            "lines": [],
            "conflicts": [],
            "roi_conflicts_resolved": False,
        }
    )
    if not WORKER_CONFIG.cpu_ocr_effective:
        return payload
    if review_required:
        WORKER_METRICS.increment("cpu_high_risk_reviews")
        evidence = CPU_OCR.inspect_gpu_lines(image_path, list(result.get("texts", [])))
        evidence.update(
            {
                "review_required": True,
                "review_reasons": list(reasons),
                "deferred": False,
            }
        )
        return evidence
    payload["deferred"] = CPU_SHADOW_DISPATCHER.submit(
        image_bytes, suffix, list(result.get("texts", []))
    )
    return payload


def _cache_key(image_bytes):
    base = hashlib.sha1(image_bytes).hexdigest()
    if not WORKER_CONFIG.enabled:
        return base
    cpu = CPU_OCR.status()
    version = "|".join(
        (
            "hybrid-v4-thin-padding",
            str(cpu.get("model_fingerprint", "")),
            str(cpu.get("preprocess_version", "")),
            str(WORKER_CONFIG.confirmation_mode),
        )
    )
    return hashlib.sha1(f"{base}|{version}".encode("ascii")).hexdigest()


def _clean_text(text):
    return (
        str(text)
        .strip()
        .replace(" ", "")
        .replace("—", "-")
        .replace("–", "-")
        .replace("－", "-")
    )


def _write_temp_file(data, suffix):
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        return tmp.name


def _write_enhanced_image(data, suffix):
    from cpu_preprocess import write_enhanced_image

    return write_enhanced_image(data, suffix) or _write_temp_file(data, suffix)


def _cache_get(key):
    now = time.time()
    with cache_lock:
        _cache_cleanup(now)
        item = ocr_cache.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at <= now:
            ocr_cache.pop(key, None)
            return None
        return value


def _cache_set(key, value):
    now = time.time()
    with cache_lock:
        _cache_cleanup(now)
        ocr_cache[key] = (now + CACHE_TTL_SECONDS, copy.deepcopy(value))


def _cache_cleanup(now):
    expired = [key for key, (expires_at, _) in ocr_cache.items() if expires_at <= now]
    for key in expired:
        ocr_cache.pop(key, None)


def _remove_file(path):
    try:
        os.remove(path)
    except Exception:
        pass


def _gpu_available():
    if paddle is None:
        return True
    try:
        return bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        return True


def _gpu_name():
    if paddle is not None:
        try:
            return paddle.device.cuda.get_device_name()
        except Exception:
            pass
    return "RTX5070"

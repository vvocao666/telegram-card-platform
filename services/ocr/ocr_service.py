from __future__ import annotations

from services.runtime import (
    OcrResult,
    download_message_photo,
    download_photo,
    enhance,
    enhance_variants,
    filter_local_ocr_cards,
    flush_chat_batch,
    handle_photo,
    iter_local_ocr_images,
    prepare_ocrspace_image,
    recognize_update,
    resize_for_ocr,
    rotations_for,
    run_local_ocr,
    run_ocr,
    run_ocrspace,
)

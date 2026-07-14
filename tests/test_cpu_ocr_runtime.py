from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
import sys


WORKER_ROOT = Path(__file__).resolve().parents[1] / "workers" / "rtx5070"
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

preprocess = ModuleType("cpu_preprocess")
preprocess.PREPROCESS_VERSION = "test-roi"
preprocess.write_roi_crop = lambda *_args, **_kwargs: None
sys.modules.setdefault("cpu_preprocess", preprocess)

registry = ModuleType("model_registry")
registry.CpuModelStatus = SimpleNamespace
registry.validate_cpu_model = lambda: SimpleNamespace(available=False, version="", model_fingerprint="", error="")
sys.modules.setdefault("model_registry", registry)

import cpu_ocr
from worker_metrics import WorkerMetrics


def test_cpu_ocr_receives_partial_pubg_prefix_roi(monkeypatch, tmp_path):
    image = tmp_path / "roi.png"
    image.write_bytes(b"test")
    crop = tmp_path / "crop.png"
    crop.write_bytes(b"crop")
    config = SimpleNamespace(cpu_ocr_workers=1, cpu_ocr_effective=True, cpu_shadow_only=True,
                             cpu_can_affect_result=False, confirmation_mode="strict")
    metrics = WorkerMetrics()
    engine = cpu_ocr.CpuOcrEngine(config, metrics)
    monkeypatch.setattr(engine, "_model_status", lambda: SimpleNamespace(
        available=True, version="test", model_fingerprint="test", error=""
    ))
    monkeypatch.setattr(cpu_ocr, "write_roi_crop", lambda *_args: str(crop))
    monkeypatch.setattr(
        engine,
        "_get_ocr",
        lambda: lambda *_args, **_kwargs: ([[None, "S07324-JWWB-Y596-", 0.91]], None),
    )

    payload = engine.inspect_gpu_lines(
        str(image),
        [{"text": "密码：S07324-JWWB-Y596-", "box": [1, 2, 30, 12]}],
    )

    assert payload["lines"] == [{"box": [1, 2, 30, 12], "raw_text": "S07324-JWWB-Y596-", "score": 0.91}]
    snapshot = metrics.snapshot()
    assert snapshot["cpu_preprocess_runs"] == 1
    assert snapshot["cpu_ocr_runs"] == 1


def test_cpu_ocr_receives_roi_when_gpu_reads_pubg_leading_s_as_five(monkeypatch, tmp_path):
    image = tmp_path / "roi.png"
    image.write_bytes(b"test")
    crop = tmp_path / "crop.png"
    crop.write_bytes(b"crop")
    config = SimpleNamespace(cpu_ocr_workers=1, cpu_ocr_effective=True, cpu_shadow_only=True,
                             cpu_can_affect_result=False, confirmation_mode="strict")
    engine = cpu_ocr.CpuOcrEngine(config, WorkerMetrics())
    monkeypatch.setattr(engine, "_model_status", lambda: SimpleNamespace(
        available=True, version="test", model_fingerprint="test", error=""
    ))
    monkeypatch.setattr(cpu_ocr, "write_roi_crop", lambda *_args: str(crop))
    monkeypatch.setattr(
        engine,
        "_get_ocr",
        lambda: lambda *_args, **_kwargs: ([[None, "S07324-Z4ZH-S4Y7-NBRSB", 0.95]], None),
    )

    payload = engine.inspect_gpu_lines(
        str(image),
        [{"text": "507324-Z4ZH-54Y7-NBRSB", "box": [1, 2, 30, 12]}],
    )

    assert payload["lines"][0]["raw_text"] == "S07324-Z4ZH-S4Y7-NBRSB"


def test_cpu_ocr_parses_rapidocr_line_only_response(monkeypatch, tmp_path):
    image = tmp_path / "roi.png"
    image.write_bytes(b"test")
    crop = tmp_path / "crop.png"
    crop.write_bytes(b"crop")
    config = SimpleNamespace(cpu_ocr_workers=1, cpu_ocr_effective=True, cpu_shadow_only=True,
                             cpu_can_affect_result=False, confirmation_mode="strict")
    engine = cpu_ocr.CpuOcrEngine(config, WorkerMetrics())
    monkeypatch.setattr(engine, "_model_status", lambda: SimpleNamespace(
        available=True, version="test", model_fingerprint="test", error=""
    ))
    monkeypatch.setattr(engine, "_get_ocr", lambda: lambda *_args, **_kwargs: (
        [["S07324-Z4ZH-S4Y7-NBRSB", 0.95]], [1.0]
    ))

    text, score = engine._recognize(str(crop))

    assert text == "S07324-Z4ZH-S4Y7-NBRSB"
    assert score == 0.95

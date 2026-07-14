from types import SimpleNamespace
from pathlib import Path
import sys


WORKER_ROOT = Path(__file__).resolve().parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from cpu_preprocess import CpuPreparationPool, should_prepare_enhanced
from worker_metrics import WorkerMetrics


def test_only_static_fast_path_failures_prebuild_enhancement() -> None:
    assert should_prepare_enhanced({"width": 700, "height": 240, "image_variance": 180.0}) is False
    assert should_prepare_enhanced({"width": 300, "height": 240, "image_variance": 180.0}) is True
    assert should_prepare_enhanced({"width": 700, "height": 800, "image_variance": 180.0}) is True
    assert should_prepare_enhanced({"width": 700, "height": 240, "image_variance": 40.0}) is True


def test_disabled_preprocess_never_schedules_work() -> None:
    pool = CpuPreparationPool(
        SimpleNamespace(cpu_preprocess_enabled=False, cpu_preprocess_workers=1),
        WorkerMetrics(),
    )
    assert pool.start(b"image", ".png", {"width": 300, "height": 240, "image_variance": 180.0}) is None


def test_preprocess_pool_records_completed_work(monkeypatch) -> None:
    metrics = WorkerMetrics()
    pool = CpuPreparationPool(
        SimpleNamespace(cpu_preprocess_enabled=True, cpu_preprocess_workers=1),
        metrics,
    )
    monkeypatch.setattr("cpu_preprocess.write_enhanced_image", lambda *_args: "enhanced.png")
    future = pool.start(b"image", ".png", {"width": 300, "height": 240, "image_variance": 180.0})
    assert pool.result(future) == "enhanced.png"
    assert metrics.snapshot()["cpu_preprocess_runs"] == 1

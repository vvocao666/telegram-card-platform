from types import SimpleNamespace
from pathlib import Path
import importlib.util
import sys


WORKER_ROOT = Path(__file__).resolve().parent
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

# tests/test_cpu_ocr_runtime deliberately supplies a tiny cpu_preprocess stub
# before importing cpu_ocr.  Load this module from its source file under an
# isolated name so collection order cannot replace the actual preprocessor.
_SPEC = importlib.util.spec_from_file_location(
    "worker_cpu_preprocess_under_test", WORKER_ROOT / "cpu_preprocess.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
CpuPreparationPool = _MODULE.CpuPreparationPool
should_prepare_enhanced = _MODULE.should_prepare_enhanced
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
    monkeypatch.setattr(_MODULE, "write_enhanced_image", lambda *_args: "enhanced.png")
    future = pool.start(b"image", ".png", {"width": 300, "height": 240, "image_variance": 180.0})
    assert pool.result(future) == "enhanced.png"
    assert metrics.snapshot()["cpu_preprocess_runs"] == 1

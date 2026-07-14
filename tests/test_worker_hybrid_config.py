import importlib.util
from pathlib import Path
import sys


WORKER_ROOT = Path(__file__).resolve().parents[1] / "workers" / "rtx5070"


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, WORKER_ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_worker_config_master_switch_disables_cpu(monkeypatch):
    module = load_module("worker_config")
    monkeypatch.setenv("LOCAL_HYBRID_ENHANCEMENT_ENABLED", "false")
    monkeypatch.setenv("LOCAL_CPU_OCR_ENABLED", "true")
    config = module.load_worker_config()
    assert not config.enabled
    assert not config.cpu_ocr_effective


def test_worker_config_reads_bounded_queue(monkeypatch):
    module = load_module("worker_config")
    monkeypatch.setenv("LOCAL_HYBRID_ENHANCEMENT_ENABLED", "true")
    monkeypatch.setenv("LOCAL_WORKER_QUEUE_CAPACITY", "999")
    config = module.load_worker_config()
    assert config.queue_capacity == 128


def test_worker_env_file_overrides_stale_service_flag(tmp_path, monkeypatch):
    module = load_module("worker_config")
    target = tmp_path / "hybrid.env"
    target.write_text("LOCAL_CPU_OCR_CAN_AFFECT_RESULT=true\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_CPU_OCR_CAN_AFFECT_RESULT", "false")
    module.load_worker_env(target)
    assert module.os.getenv("LOCAL_CPU_OCR_CAN_AFFECT_RESULT") == "true"


def test_worker_env_file_accepts_utf8_bom(tmp_path, monkeypatch):
    module = load_module("worker_config")
    target = tmp_path / "hybrid.env"
    target.write_text(
        "LOCAL_CPU_OCR_CAN_AFFECT_RESULT=true\n", encoding="utf-8-sig"
    )
    monkeypatch.setenv("LOCAL_CPU_OCR_CAN_AFFECT_RESULT", "false")
    module.load_worker_env(target)
    assert module.load_worker_config().cpu_can_affect_result

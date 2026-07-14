import threading

import pytest

from services.ocr.remote_execution_gate import RemoteExecutionGate, RemoteWorkerBusy


def test_gate_rejects_when_all_slots_are_busy():
    gate = RemoteExecutionGate(1)
    with gate.slot(0):
        with pytest.raises(RemoteWorkerBusy):
            with gate.slot(0):
                pass
    assert gate.snapshot().rejected == 1
    assert gate.snapshot().active == 0


def test_gate_recovers_after_slot_released():
    gate = RemoteExecutionGate(1)
    with gate.slot(0):
        pass
    with gate.slot(0):
        assert gate.snapshot().active == 1

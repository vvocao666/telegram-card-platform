from __future__ import annotations

from pathlib import Path

from storage.repositories.ledger_storage import LedgerStore


def create_ledger_store(path: str | Path) -> LedgerStore:
    return LedgerStore(Path(path))

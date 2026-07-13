from __future__ import annotations

import threading

import httpx


_client: httpx.Client | None = None
_client_timeout: float | None = None
_client_lock = threading.Lock()


def get_ocrspace_http_client(timeout: float) -> httpx.Client:
    global _client, _client_timeout
    target_timeout = float(timeout)
    with _client_lock:
        if _client is None or _client_timeout != target_timeout:
            _close_client_unlocked()
            _client = httpx.Client(timeout=target_timeout)
            _client_timeout = target_timeout
        return _client


def close_ocrspace_http_client() -> None:
    with _client_lock:
        _close_client_unlocked()


def _close_client_unlocked() -> None:
    global _client, _client_timeout
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
    _client = None
    _client_timeout = None

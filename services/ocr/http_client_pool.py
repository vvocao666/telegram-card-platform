from __future__ import annotations

import threading

import httpx


_ocrspace_client: httpx.Client | None = None
_ocrspace_client_timeout: float | None = None
_ocrspace_client_lock = threading.Lock()
_remote_clients: dict[float, httpx.Client] = {}
_remote_client_lock = threading.Lock()


def get_ocrspace_http_client(timeout: float) -> httpx.Client:
    global _ocrspace_client, _ocrspace_client_timeout
    target_timeout = float(timeout)
    with _ocrspace_client_lock:
        if _ocrspace_client is None or _ocrspace_client_timeout != target_timeout:
            _close_ocrspace_client_unlocked()
            _ocrspace_client = httpx.Client(timeout=target_timeout)
            _ocrspace_client_timeout = target_timeout
        return _ocrspace_client


def close_ocrspace_http_client() -> None:
    with _ocrspace_client_lock:
        _close_ocrspace_client_unlocked()


def _close_ocrspace_client_unlocked() -> None:
    global _ocrspace_client, _ocrspace_client_timeout
    if _ocrspace_client is not None:
        try:
            _ocrspace_client.close()
        except Exception:
            pass
    _ocrspace_client = None
    _ocrspace_client_timeout = None


def get_remote_http_client(timeout: float) -> httpx.Client:
    target_timeout = float(timeout)
    with _remote_client_lock:
        client = _remote_clients.get(target_timeout)
        if client is None:
            client = httpx.Client(timeout=target_timeout)
            _remote_clients[target_timeout] = client
        return client


def close_remote_http_client() -> None:
    with _remote_client_lock:
        clients = list(_remote_clients.values())
        _remote_clients.clear()
    for client in clients:
        try:
            client.close()
        except Exception:
            pass

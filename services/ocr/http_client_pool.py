from __future__ import annotations

import threading

import httpx


_ocrspace_client: httpx.Client | None = None
_ocrspace_client_timeout: float | None = None
_ocrspace_client_lock = threading.Lock()
_remote_clients: dict[tuple[float, float], httpx.Client] = {}
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


def get_remote_http_client(
    timeout: float, connect_timeout: float | None = None
) -> httpx.Client:
    read_timeout = float(timeout)
    target_connect_timeout = float(
        read_timeout if connect_timeout is None else connect_timeout
    )
    client_key = (read_timeout, target_connect_timeout)
    with _remote_client_lock:
        client = _remote_clients.get(client_key)
        if client is None:
            timeout_config: float | httpx.Timeout
            if target_connect_timeout == read_timeout:
                timeout_config = read_timeout
            else:
                timeout_config = httpx.Timeout(
                    read_timeout,
                    connect=target_connect_timeout,
                )
            client = httpx.Client(timeout=timeout_config)
            _remote_clients[client_key] = client
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

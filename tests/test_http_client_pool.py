import services.ocr.http_client_pool as pool


class FakeClient:
    created: list[float] = []
    closed = 0

    def __init__(self, timeout: float):
        self.timeout = float(timeout)
        type(self).created.append(self.timeout)

    def close(self) -> None:
        type(self).closed += 1


def test_remote_clients_reuse_connections_without_timeout_churn(monkeypatch):
    monkeypatch.setattr(pool.httpx, "Client", FakeClient)
    FakeClient.created = []
    FakeClient.closed = 0
    pool.close_remote_http_client()

    try:
        health_client = pool.get_remote_http_client(1.5)
        ocr_client = pool.get_remote_http_client(3.0)

        assert pool.get_remote_http_client(1.5) is health_client
        assert pool.get_remote_http_client(3.0) is ocr_client
        assert FakeClient.created == [1.5, 3.0]
        assert FakeClient.closed == 0
    finally:
        pool.close_remote_http_client()

    assert FakeClient.closed == 2

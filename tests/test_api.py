import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.socket_client import ClamAVUnavailable, UploadTooLarge


@pytest.fixture
def client():
    app = create_app(
        Settings(
            max_upload_size=1024,
            stream_chunk_size=1024,
            scan_queue_timeout=0.01,
            scan_timeout=0.01,
        )
    )
    with TestClient(app) as test_client:
        mock = AsyncMock()
        app.state.clamav = mock
        yield test_client, mock, app


def test_request_id_is_returned(client):
    http, _, _ = client
    response = http.get("/health", headers={"x-request-id": "request-123"})
    assert response.headers["x-request-id"] == "request-123"


def test_invalid_request_id_is_replaced(client):
    http, _, _ = client
    response = http.get("/health", headers={"x-request-id": "invalid value"})
    assert response.headers["x-request-id"] != "invalid value"
    assert len(response.headers["x-request-id"]) == 36


def test_metrics_are_disabled_by_default():
    app = create_app(Settings())
    with TestClient(app) as http:
        assert http.get("/metrics").status_code == 404


def test_metrics_can_be_enabled():
    app = create_app(Settings(metrics_enabled=True))
    with TestClient(app) as http:
        response = http.get("/metrics")
        assert response.status_code == 200
        assert "clamr_http_requests_total" in response.text


def test_liveness(client):
    http, _, _ = client
    assert http.get("/health").json() == {"status": "ok"}


def test_clamav_readiness(client):
    http, clamav, _ = client
    clamav.ping.return_value = "PONG"
    response = http.get("/health/clamav")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "clamav": "PONG"}


def test_unexpected_ping_is_not_ready(client):
    http, clamav, _ = client
    clamav.ping.return_value = "NOPE"
    assert http.get("/health/clamav").status_code == 503


def test_clamav_unavailable(client):
    http, clamav, _ = client
    clamav.ping.side_effect = ClamAVUnavailable("internal socket detail")
    response = http.get("/health/clamav")
    assert response.status_code == 503
    assert response.json() == {"detail": "ClamAV is unavailable"}


def test_version_is_parsed(client):
    http, clamav, _ = client
    clamav.version.return_value = "ClamAV 1.5.3/28080/Sun Aug 2"
    body = http.get("/clamav/version").json()
    assert body["engine_version"] == "ClamAV 1.5.3"
    assert body["parsed"] == {"major": 1, "minor": 5, "patch": 3, "database_version": 28080}


def test_clean_multipart_scan(client):
    http, clamav, _ = client
    clamav.scan_stream.return_value = ("stream: OK", 3)
    response = http.post("/scan/file", files={"file": ("safe.txt", b"abc")})
    assert response.status_code == 200
    assert response.json()["status"] == "clean"
    assert response.json()["filename"] == "safe.txt"
    assert "raw_result" not in response.json()


def test_raw_stream_scan(client):
    http, clamav, _ = client
    clamav.scan_stream.return_value = ("stream: OK", 3)
    response = http.post(
        "/scan/stream",
        content=b"abc",
        headers={"content-type": "application/octet-stream", "x-filename": "safe.bin"},
    )
    assert response.status_code == 200
    assert response.json()["filename"] == "safe.bin"


def test_raw_stream_rejects_content_length_early(client):
    http, clamav, _ = client
    response = http.post("/scan/stream", content=b"x" * 1025)
    assert response.status_code == 413
    clamav.scan_stream.assert_not_awaited()


def test_infected_scan(client):
    http, clamav, _ = client
    clamav.scan_stream.return_value = ("stream: Eicar-Test-Signature FOUND", 68)
    body = http.post("/scan/file", files={"file": ("eicar.com", b"test")}).json()
    assert body["status"] == "infected"
    assert body["signature"] == "Eicar-Test-Signature"


def test_scan_error(client):
    http, clamav, _ = client
    clamav.scan_stream.return_value = ("stream: size limit exceeded ERROR", 11)
    response = http.post("/scan/file", files={"file": ("large", b"123")})
    assert response.status_code == 502


def test_unknown_scan_response(client):
    http, clamav, _ = client
    clamav.scan_stream.return_value = ("nonsense", 3)
    assert http.post("/scan/stream", content=b"abc").status_code == 502


def test_upload_limit(client):
    http, clamav, _ = client
    clamav.scan_stream.side_effect = UploadTooLarge("too large")
    response = http.post("/scan/file", files={"file": ("large", b"123")})
    assert response.status_code == 413


def test_multipart_transport_limit_is_enforced_before_scan(client):
    http, clamav, _ = client
    response = http.post(
        "/scan/file",
        files={"file": ("large.bin", b"x" * (1024 * 1024 + 1025))},
    )
    assert response.status_code == 413
    clamav.scan_stream.assert_not_awaited()


def test_scan_deadline(client):
    http, clamav, _ = client

    async def never_finishes(*_args):
        await asyncio.sleep(1)

    clamav.scan_stream.side_effect = never_finishes
    response = http.post("/scan/stream", content=b"abc")
    assert response.status_code == 504


def test_scan_queue_timeout(client):
    http, clamav, app = client
    app.state.scan_slots = asyncio.Semaphore(0)
    response = http.post("/scan/stream", content=b"abc")
    assert response.status_code == 429
    clamav.scan_stream.assert_not_awaited()


def test_docs_can_be_disabled():
    app = create_app(Settings(docs_enabled=False))
    with TestClient(app) as http:
        assert http.get("/docs").status_code == 404
        assert http.get("/openapi.json").status_code == 404


def test_unmatched_metric_path_has_bounded_label():
    app = create_app(Settings(metrics_enabled=True))
    with TestClient(app) as http:
        assert http.get("/a-secret-random-path").status_code == 404
        metrics = http.get("/metrics").text
    assert 'path="unmatched"' in metrics
    assert "a-secret-random-path" not in metrics


def test_deadline_releases_scan_capacity(client):
    http, clamav, app = client

    async def never_finishes(*_args):
        await asyncio.sleep(1)

    clamav.scan_stream.side_effect = never_finishes
    assert http.post("/scan/stream", content=b"abc").status_code == 504
    assert app.state.scan_slots._value == 4


def test_multipart_rejects_fields_and_releases_upload_capacity(client):
    http, clamav, app = client
    response = http.post("/scan/file", files={"wrong": (None, "value")})
    assert response.status_code in {400, 422}
    assert app.state.upload_slots._value == 4
    clamav.scan_stream.assert_not_awaited()


def test_protected_route_uses_authenticator(client):
    http, clamav, app = client
    authenticator = AsyncMock()
    authenticator.authenticate.side_effect = HTTPException(status_code=401)
    app.state.authenticator = authenticator
    assert http.post("/scan/stream", content=b"abc").status_code == 401
    assert http.get("/health").status_code == 200
    clamav.scan_stream.assert_not_awaited()

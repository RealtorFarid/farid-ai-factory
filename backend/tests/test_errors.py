"""The error envelope and correlation-id propagation."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_error_envelope_shape(client: TestClient) -> None:
    body = client.post("/v1/agents/ghost/run", json={"prompt": "hi"}).json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) >= {"code", "message", "request_id"}
    assert isinstance(error["message"], str)


def test_validation_error_includes_details(client: TestClient) -> None:
    body = client.post("/v1/agents/atlas/run", json={}).json()
    details = body["error"]["details"]
    assert details and any("prompt" in d["location"] for d in details)


def test_unknown_route_uses_the_envelope(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_request_id_is_generated_and_echoed(client: TestClient) -> None:
    response = client.get("/health")
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36  # uuid4
    assert response.headers["X-Request-ID"] == request_id


def test_inbound_request_id_is_honoured(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-abc"})
    assert response.headers["X-Request-ID"] == "trace-abc"


def test_request_id_appears_in_error_bodies(client: TestClient) -> None:
    response = client.post(
        "/v1/agents/ghost/run", json={"prompt": "hi"}, headers={"X-Request-ID": "trace-xyz"}
    )
    assert response.json()["error"]["request_id"] == "trace-xyz"


def test_unhandled_exception_returns_generic_500(app: FastAPI) -> None:
    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("private failure detail")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "private failure detail" not in error["message"]

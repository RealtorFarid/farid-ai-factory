"""Liveness and readiness probes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.runtime.agent import AgentRegistry
from backend.runtime.config import Settings
from tests.conftest import make_runtime


def test_health_reports_service_identity(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Propilot AI"
    assert body["environment"] == "development"
    assert body["version"]


def test_ready_is_ready_when_configured(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["agents"] == "ok"
    assert body["checks"]["llm_credentials"] == "ok"
    assert body["checks"]["tracing"] == "disabled"


def test_ready_is_degraded_without_credentials(settings: Settings) -> None:
    without_key = settings.model_copy(update={"openai_api_key": None})
    app = create_app(settings=without_key, runtime=make_runtime(without_key))
    with TestClient(app) as client:
        body = client.get("/health/ready").json()
    assert body["status"] == "degraded"
    assert body["checks"]["llm_credentials"] == "missing"


def test_ready_is_degraded_without_agents(settings: Settings) -> None:
    runtime = make_runtime(settings, agents=AgentRegistry())
    with TestClient(create_app(settings=settings, runtime=runtime)) as client:
        body = client.get("/health/ready").json()
    assert body["status"] == "degraded"
    assert body["checks"]["agents"] == "no agents registered"


def test_docs_are_exposed_outside_production(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 200


def test_docs_are_hidden_in_production() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="production",
        cors_origins=["https://app.test"],
        log_level="WARNING",
    )
    with TestClient(create_app(settings=settings, runtime=make_runtime(settings))) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404

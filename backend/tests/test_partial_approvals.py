"""Sprint 4A: per-tool isolation, partial success, proposed vs executed.

The scenario under test is the one that broke in live use: a run proposes two
gated actions, the user approves one and rejects the other. Before this work
that path failed the whole run and silently discarded the approved action.

Everything is asserted through HTTP and by *effect* on the workspace, because
"the API said partial" is worth nothing if the email did not actually go.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.runtime.agent import build_registry
from backend.runtime.config import Settings
from backend.runtime.container import Runtime, build_runtime
from backend.runtime.tools import ToolRegistry, ToolSpec, build_default_tools
from backend.runtime.workspace import InMemoryWorkspaceStore, WorkspaceService
from tests.sse import parse_sse

SEND_EMAIL = "send_email"
COMPLETE_TASK = "complete_task"


@pytest.fixture
def stub_settings(settings: Settings) -> Settings:
    """The deterministic offline model that proposes two gated actions."""
    return settings.model_copy(update={"default_model": "stub"})


@pytest.fixture
def stub_runtime(stub_settings: Settings, clock: Callable[[], datetime]) -> Runtime:
    store = InMemoryWorkspaceStore(clock=clock)
    workspace = WorkspaceService(store)
    tools = build_default_tools(workspace)
    registry = build_registry(stub_settings, tools)

    runtime = build_runtime(stub_settings, store=store, agents=registry)
    # Share the exact service the tools closed over, so HTTP assertions observe
    # the same workspace the tools mutate.
    object.__setattr__(runtime, "workspace", workspace)
    object.__setattr__(runtime, "tools", tools)
    return runtime


@pytest.fixture
def client(stub_settings: Settings, stub_runtime: Runtime) -> Iterator[TestClient]:
    with TestClient(create_app(settings=stub_settings, runtime=stub_runtime)) as test_client:
        yield test_client


# ---- Helpers -------------------------------------------------------------


def _start(client: TestClient) -> dict[str, Any]:
    response = client.post("/v1/agents/atlas/run", json={"prompt": "Sort out my morning"})
    assert response.status_code == 200
    return response.json()


def _pending_id(run: dict[str, Any], tool_name: str) -> str:
    match = [p for p in run["pending_approvals"] if p["tool_name"] == tool_name]
    assert match, f"{tool_name} not pending: {run['pending_approvals']}"
    return str(match[0]["tool_call_id"])


def _call(run: dict[str, Any], tool_name: str) -> dict[str, Any]:
    match = [c for c in run["tool_calls"] if c["tool_name"] == tool_name]
    assert match, f"{tool_name} not recorded: {run['tool_calls']}"
    return dict(match[0])


def _email_needs_response(client: TestClient, email_id: str) -> bool:
    threads = client.get("/v1/workspace/email/summary?limit=50").json()["threads"]
    return bool(next(t["needs_response"] for t in threads if t["id"] == email_id))


def _task_ids(client: TestClient) -> set[str]:
    return {t["id"] for t in client.get("/v1/workspace/tasks").json()}


# ---- The gate pauses on every gated call ---------------------------------


def test_run_pauses_with_both_gated_actions_pending(client: TestClient) -> None:
    run = _start(client)

    assert run["status"] == "awaiting_approval"
    assert {p["tool_name"] for p in run["pending_approvals"]} == {SEND_EMAIL, COMPLETE_TASK}

    # The ungated read ran; neither gated action did.
    assert _call(run, "summarize_leads")["status"] == "executed"
    assert _call(run, SEND_EMAIL)["status"] == "proposed"
    assert _call(run, COMPLETE_TASK)["status"] == "proposed"

    # Nothing has touched the workspace.
    assert _email_needs_response(client, "eml_001") is True
    assert "tsk_001" in _task_ids(client)


# ---- The acceptance criterion --------------------------------------------


def test_approve_one_reject_the_other(client: TestClient) -> None:
    """Approve the email, reject the task. Both outcomes must be real."""
    run = _start(client)
    email_id = _pending_id(run, SEND_EMAIL)
    task_id = _pending_id(run, COMPLETE_TASK)

    resolved = client.post(
        f"/v1/runs/{run['id']}/approvals",
        json={
            "decisions": [
                {"tool_call_id": email_id, "approved": True},
                {"tool_call_id": task_id, "approved": False, "reason": "I'll do this myself."},
            ]
        },
    )
    assert resolved.status_code == 200
    body = resolved.json()

    # 1. The run reports PARTIAL.
    assert body["status"] == "partial"
    # 2. The user still gets an answer.
    assert body["output"]
    # 3. Per-call outcomes are distinguishable.
    assert _call(body, SEND_EMAIL)["status"] == "executed"
    assert _call(body, SEND_EMAIL)["approved"] is True
    assert _call(body, COMPLETE_TASK)["status"] == "denied"
    assert _call(body, COMPLETE_TASK)["approved"] is False
    assert _call(body, COMPLETE_TASK)["error"] == "I'll do this myself."
    # 4. The approved action landed.
    assert _email_needs_response(client, "eml_001") is False
    # 5. The rejected action did not.
    assert "tsk_001" in _task_ids(client)
    # 6. No duplicate audit entries.
    assert len(body["tool_calls"]) == len({c["tool_call_id"] for c in body["tool_calls"]})


def test_approving_everything_completes(client: TestClient) -> None:
    run = _start(client)
    body = client.post(
        f"/v1/runs/{run['id']}/approvals",
        json={
            "decisions": [
                {"tool_call_id": _pending_id(run, SEND_EMAIL), "approved": True},
                {"tool_call_id": _pending_id(run, COMPLETE_TASK), "approved": True},
            ]
        },
    ).json()

    assert body["status"] == "completed"
    assert _email_needs_response(client, "eml_001") is False
    assert "tsk_001" not in _task_ids(client)


def test_rejecting_everything_is_partial_with_no_effects(client: TestClient) -> None:
    run = _start(client)
    body = client.post(
        f"/v1/runs/{run['id']}/approvals",
        json={
            "decisions": [
                {"tool_call_id": _pending_id(run, SEND_EMAIL), "approved": False},
                {"tool_call_id": _pending_id(run, COMPLETE_TASK), "approved": False},
            ]
        },
    ).json()

    assert body["status"] == "partial"
    assert _email_needs_response(client, "eml_001") is True
    assert "tsk_001" in _task_ids(client)


def test_omitting_one_decision_denies_only_that_one(client: TestClient) -> None:
    """The regression: a partial decision set must not fail the run."""
    run = _start(client)

    body = client.post(
        f"/v1/runs/{run['id']}/approvals",
        json={"decisions": [{"tool_call_id": _pending_id(run, SEND_EMAIL), "approved": True}]},
    ).json()

    assert body["status"] == "partial"
    assert _call(body, SEND_EMAIL)["status"] == "executed"
    assert _call(body, COMPLETE_TASK)["status"] == "denied"
    # The approved action still happened — this is what used to be lost.
    assert _email_needs_response(client, "eml_001") is False


# ---- proposed vs executed events -----------------------------------------


def test_events_distinguish_proposed_from_executed(client: TestClient) -> None:
    run = _start(client)
    run_id = run["id"]

    with client.stream("GET", f"/v1/runs/{run_id}/events") as response:
        before = parse_sse(response.read().decode())

    names = [name for name, _ in before]
    proposed = [d["data"]["tool_name"] for n, d in before if n == "tool.proposed"]
    executed = [d["data"]["tool_name"] for n, d in before if n == "tool.executed"]

    # The ungated read is `called` then `executed`; gated ones are only proposed.
    assert "tool.called" in names
    assert set(proposed) == {SEND_EMAIL, COMPLETE_TASK}
    assert executed == ["summarize_leads"]
    assert SEND_EMAIL not in executed

    client.post(
        f"/v1/runs/{run_id}/approvals",
        json={
            "decisions": [
                {"tool_call_id": _pending_id(run, SEND_EMAIL), "approved": True},
                {"tool_call_id": _pending_id(run, COMPLETE_TASK), "approved": False},
            ]
        },
    )

    with client.stream("GET", f"/v1/runs/{run_id}/events") as response:
        after = parse_sse(response.read().decode())

    executed_after = [d["data"]["tool_name"] for n, d in after if n == "tool.executed"]
    resolved = {
        d["data"]["tool_name"]: d["data"]["approved"] for n, d in after if n == "approval.resolved"
    }
    final = after[-1]

    assert SEND_EMAIL in executed_after  # only now
    assert COMPLETE_TASK not in executed_after  # never
    assert resolved == {SEND_EMAIL: True, COMPLETE_TASK: False}
    assert final[0] == "run.completed"
    assert final[1]["data"]["status"] == "partial"


def test_proposed_event_marks_the_call_as_requiring_approval(client: TestClient) -> None:
    run = _start(client)
    with client.stream("GET", f"/v1/runs/{run['id']}/events") as response:
        frames = parse_sse(response.read().decode())

    for name, payload in frames:
        if name == "tool.proposed":
            assert payload["data"]["requires_approval"] is True
        if name == "tool.called":
            assert payload["data"]["requires_approval"] is False


# ---- Per-tool isolation --------------------------------------------------


def test_a_raising_tool_does_not_fail_the_run(
    stub_settings: Settings, clock: Callable[[], datetime]
) -> None:
    """An exception inside a tool becomes a result, not a dead run."""
    store = InMemoryWorkspaceStore(clock=clock)
    workspace = WorkspaceService(store)
    tools = build_default_tools(workspace)

    def explode() -> dict[str, Any]:
        """Always raises."""
        raise RuntimeError("disk on fire")

    tools.register(ToolSpec(name="explode", description="Always raises.", function=explode))

    # Called directly through the registry's wrapper, as the agent would.
    wrapped = {t.name: t for t in tools.as_pydantic_tools()}["explode"]
    result = wrapped.function()  # type: ignore[attr-defined]

    assert result["ok"] is False
    assert "disk on fire" in result["error"]
    assert "RuntimeError" in result["error"]


def test_isolation_preserves_the_tool_signature(tools: ToolRegistry) -> None:
    """Wrapping must not break schema generation, or the model loses the args."""
    built = {t.name: t for t in tools.as_pydantic_tools()}
    schema = built[SEND_EMAIL].function_schema.json_schema  # type: ignore[attr-defined]
    assert set(schema["properties"]) == {"lead_id", "subject", "body"}

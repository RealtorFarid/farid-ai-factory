"""The tool registry and the tools themselves."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from backend.runtime.tools import ToolRegistry, ToolSpec, build_default_tools, parse_when
from backend.runtime.workspace import WorkspaceService
from tests.conftest import FROZEN_NOW


def _call(tools: ToolRegistry, name: str, **kwargs: Any) -> Any:
    spec = tools.get(name)
    assert spec is not None, f"{name} is not registered"
    return spec.function(**kwargs)


# ---- Registry ------------------------------------------------------------


def test_registry_rejects_duplicates() -> None:
    registry = ToolRegistry()
    spec = ToolSpec(name="t", description="d", function=lambda: None)
    registry.register(spec)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec)


def test_registry_lookup_and_iteration(tools: ToolRegistry) -> None:
    assert len(tools) == 8
    assert "send_email" in tools
    assert tools.get("nope") is None
    assert sorted(tools.names()) == sorted(spec.name for spec in tools)


def test_only_effectful_tools_are_gated(tools: ToolRegistry) -> None:
    gated = {spec.name for spec in tools.requiring_approval()}
    assert gated == {"send_email", "schedule_showing", "complete_task"}
    # Everything gated must say so in its description, so the model can explain it.
    assert all("approval" in spec.description.lower() for spec in tools.requiring_approval())


def test_pydantic_tools_carry_the_approval_flag(tools: ToolRegistry) -> None:
    built = {tool.name: tool for tool in tools.as_pydantic_tools()}
    assert built["send_email"].requires_approval is True
    assert built["summarize_leads"].requires_approval is False


# ---- Read-only tools -----------------------------------------------------


def test_list_todays_tasks_is_json_serialisable(tools: ToolRegistry) -> None:
    result = _call(tools, "list_todays_tasks")
    assert result
    assert all(isinstance(task["due_at"], str) for task in result)


def test_summaries_match_the_service(tools: ToolRegistry, workspace: WorkspaceService) -> None:
    """A tool must never report a different number than the dashboard."""
    assert _call(tools, "summarize_leads")["total"] == workspace.lead_summary().total
    assert _call(tools, "summarize_inbox")["unread"] == workspace.email_summary().unread
    assert (
        _call(tools, "summarize_calendar")["today_count"]
        == workspace.calendar_summary().today_count
    )


def test_get_lead_hit_and_miss(tools: ToolRegistry) -> None:
    assert _call(tools, "get_lead", lead_id="lead_001")["name"] == "Priya Raman"
    assert _call(tools, "get_lead", lead_id="nope") is None


# ---- Gated tools ---------------------------------------------------------


def test_send_email_marks_the_thread_answered(
    tools: ToolRegistry, workspace: WorkspaceService
) -> None:
    result = _call(tools, "send_email", lead_id="lead_001", subject="Hi", body="Confirming.")
    assert result["sent"] is True
    assert result["to"] == "priya.raman@example.com"

    thread = next(t for t in workspace.email_summary(limit=50).threads if t.id == "eml_001")
    assert thread.needs_response is False


def test_send_email_to_an_unknown_lead_reports_the_miss(tools: ToolRegistry) -> None:
    result = _call(tools, "send_email", lead_id="nope", subject="s", body="b")
    assert result["sent"] is False
    assert "nope" in result["reason"]


def test_schedule_showing_creates_an_event(
    tools: ToolRegistry, workspace: WorkspaceService
) -> None:
    before = len(workspace.calendar_summary().events)
    result = _call(
        tools,
        "schedule_showing",
        lead_id="lead_001",
        starts_at=(FROZEN_NOW + timedelta(hours=6)).isoformat(),
        location="155 Yonge St",
    )
    assert result["booked"] is True
    assert result["event"]["lead_id"] == "lead_001"
    assert len(workspace.calendar_summary().events) == before + 1


def test_schedule_showing_for_an_unknown_lead(tools: ToolRegistry) -> None:
    result = _call(
        tools, "schedule_showing", lead_id="nope", starts_at=FROZEN_NOW.isoformat(), location="x"
    )
    assert result["booked"] is False


def test_schedule_showing_rejects_an_unreadable_time_without_raising(
    tools: ToolRegistry,
) -> None:
    """A bad timestamp must be a tool result, not an exception that kills the run."""
    result = _call(tools, "schedule_showing", lead_id="lead_001", starts_at="a", location="x")
    assert result["booked"] is False
    assert "ISO-8601" in result["reason"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-03-18T18:00:00Z", True),
        ("2026-03-18T18:00:00+00:00", True),
        ("2026-03-18T18:00:00", True),  # naive input is assumed UTC
        ("2026-03-18", True),
        ("a", False),
        ("", False),
        ("   ", False),
        ("next Thursday", False),
    ],
)
def test_parse_when(value: str, expected: bool) -> None:
    parsed = parse_when(value)
    assert (parsed is not None) is expected
    if parsed is not None:
        assert parsed.tzinfo is not None  # always timezone-aware


def test_complete_task(tools: ToolRegistry, workspace: WorkspaceService) -> None:
    assert _call(tools, "complete_task", task_id="tsk_001")["completed"] is True
    assert _call(tools, "complete_task", task_id="nope")["completed"] is False
    assert "tsk_001" not in {task.id for task in workspace.todays_tasks()}


def test_build_default_tools_is_independent_per_service(
    workspace: WorkspaceService,
) -> None:
    """Two registries must not share state through a module-level global."""
    first = build_default_tools(workspace)
    second = build_default_tools(workspace)
    assert first is not second
    assert len(first) == len(second)

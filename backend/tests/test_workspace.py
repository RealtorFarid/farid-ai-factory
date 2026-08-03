"""The workspace domain and its REST surface.

The service is the single source of truth shared by the agent tools and the
UI, so these tests pin the arithmetic as well as the shapes.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from backend.runtime.workspace import (
    InMemoryWorkspaceStore,
    TaskStatus,
    WorkspaceService,
)
from tests.conftest import FROZEN_NOW

# ---- Service -------------------------------------------------------------


def test_todays_tasks_excludes_done_and_sorts_by_urgency(
    workspace: WorkspaceService,
) -> None:
    tasks = workspace.todays_tasks()

    assert all(t.status is not TaskStatus.DONE for t in tasks)
    priorities = [t.priority.value for t in tasks]
    assert priorities == sorted(priorities, key=lambda p: {"high": 0, "medium": 1, "low": 2}[p])
    # A task due tomorrow is not "today".
    assert all(t.due_at.date() <= FROZEN_NOW.date() for t in tasks)


def test_todays_tasks_can_include_completed(workspace: WorkspaceService) -> None:
    assert len(workspace.todays_tasks(include_done=True)) > len(workspace.todays_tasks())


def test_lead_summary_arithmetic(workspace: WorkspaceService) -> None:
    summary = workspace.lead_summary()

    assert summary.total == 6
    assert sum(summary.by_stage.values()) == summary.total
    assert summary.by_stage["offer"] == 1
    # Sofia was last contacted nine days ago and is still active.
    assert summary.needs_follow_up == 1
    assert [lead.score for lead in summary.hottest] == sorted(
        [lead.score for lead in summary.hottest], reverse=True
    )
    # Closed and lost leads are never "hot".
    assert all(lead.stage.value not in ("closed", "lost") for lead in summary.hottest)


def test_email_summary_counts(workspace: WorkspaceService) -> None:
    summary = workspace.email_summary()
    assert summary.unread == 3
    assert summary.needs_response == 4
    assert summary.threads == sorted(summary.threads, key=lambda t: t.received_at, reverse=True)


def test_calendar_summary_finds_the_next_event(workspace: WorkspaceService) -> None:
    summary = workspace.calendar_summary()

    assert summary.today_count == 3
    assert summary.next_event is not None
    assert summary.next_event.starts_at >= FROZEN_NOW
    assert summary.events == sorted(summary.events, key=lambda e: e.starts_at)


def test_scheduling_an_event_shows_up_in_the_calendar(
    workspace: WorkspaceService,
) -> None:
    before = len(workspace.calendar_summary().events)
    workspace.schedule_event(
        title="Showing — test",
        starts_at=FROZEN_NOW + timedelta(hours=4),
        location="1 Test St",
        lead_id="lead_001",
    )
    assert len(workspace.calendar_summary().events) == before + 1


def test_marking_an_email_answered_clears_both_flags(
    workspace: WorkspaceService,
) -> None:
    assert workspace.mark_email_answered("eml_001") is True
    thread = next(t for t in workspace.email_summary(limit=50).threads if t.id == "eml_001")
    assert thread.unread is False
    assert thread.needs_response is False


def test_mutations_report_a_miss(workspace: WorkspaceService) -> None:
    assert workspace.mark_email_answered("nope") is False
    assert workspace.complete_task("nope") is False


def test_suggestions_are_ranked_by_impact(workspace: WorkspaceService) -> None:
    impacts = [s.impact.value for s in workspace.suggestions()]
    assert impacts == sorted(impacts, key=lambda i: {"high": 0, "medium": 1, "low": 2}[i])
    assert all(s.prompt for s in workspace.suggestions())


def test_the_seed_follows_the_clock(clock: Callable[[], datetime]) -> None:
    """Seed data is anchored to 'now', so the dashboard is never empty."""
    later = WorkspaceService(InMemoryWorkspaceStore(clock=lambda: FROZEN_NOW.replace(year=2030)))
    assert later.todays_tasks()
    assert later.calendar_summary().today_count > 0


# ---- REST surface --------------------------------------------------------


def test_dashboard_returns_every_panel(client: TestClient) -> None:
    body = client.get("/v1/workspace/dashboard").json()

    assert set(body) == {
        "generated_at",
        "tasks",
        "leads",
        "emails",
        "calendar",
        "suggestions",
    }
    assert body["tasks"]
    assert body["leads"]["total"] == 6
    assert body["emails"]["unread"] == 3
    assert body["suggestions"]


def test_panel_endpoints(client: TestClient) -> None:
    assert client.get("/v1/workspace/tasks").status_code == 200
    assert client.get("/v1/workspace/leads").status_code == 200
    assert client.get("/v1/workspace/leads/summary").status_code == 200
    assert client.get("/v1/workspace/email/summary").status_code == 200
    assert client.get("/v1/workspace/calendar/summary").status_code == 200
    assert client.get("/v1/workspace/suggestions").status_code == 200


def test_leads_are_returned_hottest_first(client: TestClient) -> None:
    scores = [lead["score"] for lead in client.get("/v1/workspace/leads").json()]
    assert scores == sorted(scores, reverse=True)


def test_query_parameters_are_validated(client: TestClient) -> None:
    assert client.get("/v1/workspace/email/summary?limit=0").status_code == 422
    assert client.get("/v1/workspace/calendar/summary?days=999").status_code == 422

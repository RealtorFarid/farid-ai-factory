"""Postgres persistence.

The test that matters is :func:`test_paused_approval_survives_a_restart` — it
builds a run, pauses it on the approval gate, throws the entire runtime away,
builds a new one from the database, and resumes. That is the whole point of
the sprint; everything else here supports it.

Skipped when no database is configured, so the suite still runs offline.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import text

from backend.db.engine import Database
from backend.db.models import Base
from backend.db.repositories import (
    Channel,
    ClaimRepository,
    ConsentRepository,
    PostgresRunStore,
    PostgresWorkspaceStore,
)
from backend.db.seed import seed_workspace
from backend.runtime.claims import Sensitivity, SourceType
from backend.runtime.config import Settings
from backend.runtime.container import build_runtime
from backend.runtime.runs import ApprovalDecision, RunNotFoundError, RunStatus
from backend.runtime.workspace import WorkspaceService

TEST_DATABASE_URL = os.environ.get("PROPILOT_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="PROPILOT_TEST_DATABASE_URL is not set"
)

ORG = "org_test"


@pytest.fixture
def db() -> Iterator[Database]:
    """A clean schema per test. Fast, and removes all cross-test coupling."""
    assert TEST_DATABASE_URL
    database = Database(TEST_DATABASE_URL)
    with database.engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    Base.metadata.create_all(database.engine)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def seeded(db: Database) -> Database:
    seed_workspace(db, ORG)
    return db


@pytest.fixture
def db_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        log_level="CRITICAL",
        openai_api_key="sk-test",
        default_model="stub",
        database_url=TEST_DATABASE_URL,
        default_org_id=ORG,
        max_prompt_chars=500,
    )


# ---- Seeding -------------------------------------------------------------


def test_seeding_is_idempotent(db: Database) -> None:
    assert seed_workspace(db, ORG) is True
    assert seed_workspace(db, ORG) is False  # already populated

    workspace = WorkspaceService(PostgresWorkspaceStore(db, ORG))
    assert len(workspace.leads()) == 6


def test_workspace_store_matches_the_in_memory_contract(seeded: Database) -> None:
    workspace = WorkspaceService(PostgresWorkspaceStore(seeded, ORG))

    assert workspace.lead_summary().total == 6
    assert workspace.email_summary().unread == 3
    assert workspace.lead("lead_001") is not None
    assert workspace.lead("nope") is None
    assert workspace.todays_tasks()

    assert workspace.mark_email_answered("eml_001") is True
    assert workspace.mark_email_answered("nope") is False
    thread = next(t for t in workspace.email_summary(limit=50).threads if t.id == "eml_001")
    assert thread.needs_response is False


def test_tenancy_isolates_organisations(db: Database) -> None:
    seed_workspace(db, ORG)
    other = WorkspaceService(PostgresWorkspaceStore(db, "org_someone_else"))

    assert other.leads() == []
    assert other.lead("lead_001") is None  # exists, but not for this tenant
    assert other.mark_email_answered("eml_001") is False


# ---- The Claim Ledger ----------------------------------------------------


def test_claims_record_provenance(seeded: Database) -> None:
    claims = ClaimRepository(seeded, ORG)
    claim_id = claims.assert_claim(
        lead_id="lead_001",
        predicate="spouse_name",
        object_value="Reza",
        source_type=SourceType.CONVERSATION,
        confidence=0.8,
        source_quote="my husband Reza will come to the showing",
        source_ref="conv_123",
    )

    stored = claims.for_lead("lead_001")
    assert len(stored) == 1
    assert stored[0].id == claim_id
    assert stored[0].object_value == "Reza"
    assert stored[0].confidence == 0.8
    assert stored[0].source_quote  # a claim you cannot quote is not a claim


def test_claims_supersede_rather_than_overwrite(seeded: Database) -> None:
    """History must stay reconstructable, so corrections never destroy the past."""
    claims = ClaimRepository(seeded, ORG)
    first = claims.assert_claim(
        lead_id="lead_001",
        predicate="budget_max",
        object_value="1000000",
        source_type=SourceType.CONVERSATION,
        confidence=0.6,
    )
    second = claims.assert_claim(
        lead_id="lead_001",
        predicate="budget_max",
        object_value="1200000",
        source_type=SourceType.OPERATOR,
        confidence=0.95,
    )
    assert claims.supersede(first, second) is True

    active = claims.for_lead("lead_001")
    assert [c.id for c in active] == [second]

    # The superseded row still exists, marked, not deleted.
    with seeded.session() as s:
        row = s.execute(
            text("SELECT status, superseded_by FROM claims WHERE id = :id"), {"id": first}
        ).one()
    assert row.status == "contradicted"
    assert row.superseded_by == second


def test_protected_attributes_cannot_be_inferred(seeded: Database) -> None:
    """Fair housing: a protected attribute must be declared, never guessed."""
    claims = ClaimRepository(seeded, ORG)
    with pytest.raises(ValueError, match="declared, never inferred"):
        claims.assert_claim(
            lead_id="lead_001",
            predicate="religion",
            object_value="Muslim",
            source_type=SourceType.INFERENCE,
            sensitivity=Sensitivity.PROTECTED,
        )


def test_protected_attributes_are_withheld_unless_asked_for(seeded: Database) -> None:
    claims = ClaimRepository(seeded, ORG)
    claims.assert_claim(
        lead_id="lead_001",
        predicate="children_count",
        object_value="2",
        source_type=SourceType.CLIENT,
        sensitivity=Sensitivity.PROTECTED,
    )
    claims.assert_claim(
        lead_id="lead_001",
        predicate="favourite_restaurant",
        object_value="Pai",
        source_type=SourceType.CONVERSATION,
    )

    default_view = claims.for_lead("lead_001")
    assert [c.predicate for c in default_view] == ["favourite_restaurant"]

    opted_in = claims.for_lead("lead_001", include_protected=True)
    assert len(opted_in) == 2


def test_confidence_is_bounded(seeded: Database) -> None:
    claims = ClaimRepository(seeded, ORG)
    with pytest.raises(ValueError, match="between 0 and 1"):
        claims.assert_claim(
            lead_id="lead_001",
            predicate="x",
            object_value="y",
            source_type=SourceType.OPERATOR,
            confidence=1.5,
        )


def test_verification_raises_confidence(seeded: Database) -> None:
    claims = ClaimRepository(seeded, ORG)
    claim_id = claims.assert_claim(
        lead_id="lead_001",
        predicate="pet_name",
        object_value="Mochi",
        source_type=SourceType.CONVERSATION,
        confidence=0.5,
    )
    assert claims.verify(claim_id, verified_by="operator_1") is True
    assert claims.for_lead("lead_001")[0].confidence == 1.0


# ---- The Consent Ledger --------------------------------------------------


def test_no_record_means_no_contact(seeded: Database) -> None:
    """Silence is never consent."""
    consent = ConsentRepository(seeded, ORG)
    decision = consent.may_contact(lead_id="lead_001", channel=Channel.SMS)
    assert decision.allowed is False
    assert decision.status == "never_asked"


def test_granting_and_revoking_consent(seeded: Database) -> None:
    consent = ConsentRepository(seeded, ORG)
    consent.grant(
        lead_id="lead_001",
        channel=Channel.EMAIL,
        basis="express",
        jurisdiction="CA",
        evidence="Signed buyer representation agreement 2026-03-01",
    )
    assert consent.may_contact(lead_id="lead_001", channel=Channel.EMAIL).allowed is True

    # A grant on one channel says nothing about another.
    assert consent.may_contact(lead_id="lead_001", channel=Channel.SMS).allowed is False

    assert consent.revoke(lead_id="lead_001", channel=Channel.EMAIL) is True
    after = consent.may_contact(lead_id="lead_001", channel=Channel.EMAIL)
    assert after.allowed is False
    assert after.status == "revoked"


def test_expired_consent_is_not_consent(seeded: Database) -> None:
    from datetime import UTC, datetime, timedelta

    consent = ConsentRepository(seeded, ORG)
    consent.grant(
        lead_id="lead_001",
        channel=Channel.SMS,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    decision = consent.may_contact(lead_id="lead_001", channel=Channel.SMS)
    assert decision.allowed is False
    assert decision.status == "expired"


# ---- Runs ----------------------------------------------------------------


def test_run_store_round_trip(seeded: Database) -> None:
    runs = PostgresRunStore(seeded, ORG)
    run = runs.create(agent="atlas", model="stub", prompt="hello", session_id="s1")

    run.status = RunStatus.COMPLETED
    run.output = "done"
    runs.save(run)

    loaded = runs.get(run.id)
    assert loaded.output == "done"
    assert loaded.status is RunStatus.COMPLETED
    assert loaded.session_id == "s1"

    assert [r.id for r in runs.list()] == [run.id]
    assert [r.id for r in runs.list(session_id="s1")] == [run.id]
    assert runs.list(session_id="other") == []

    with pytest.raises(RunNotFoundError):
        runs.get("run_missing")


def test_tool_calls_are_upserted_not_duplicated(seeded: Database) -> None:
    """A call's status changes over its life; the audit must not fork."""
    from backend.runtime.runs import ToolCallRecord, ToolCallStatus

    runs = PostgresRunStore(seeded, ORG)
    run = runs.create(agent="atlas", model="stub", prompt="hi")
    run.tool_calls.append(
        ToolCallRecord(
            tool_name="send_email",
            tool_call_id="call_1",
            args={"lead_id": "lead_001"},
            status=ToolCallStatus.PROPOSED,
            requires_approval=True,
        )
    )
    runs.save(run)

    run.tool_calls[0].status = ToolCallStatus.EXECUTED
    run.tool_calls[0].approved = True
    runs.save(run)

    reloaded = runs.get(run.id)
    assert len(reloaded.tool_calls) == 1
    assert reloaded.tool_calls[0].status is ToolCallStatus.EXECUTED
    assert reloaded.tool_calls[0].approved is True


# ---- The sprint's reason for existing ------------------------------------


async def test_paused_approval_survives_a_restart(db_settings: Settings, db: Database) -> None:
    """Pause on an approval, discard the whole runtime, resume from Postgres."""
    seed_workspace(db, ORG)

    # --- process one: start a run and pause on the gate
    first = build_runtime(db_settings, database=db)
    run = await first.runner.start("atlas", "Sort out my morning")
    run_id = run.id

    assert run.status is RunStatus.AWAITING_APPROVAL
    assert len(run.pending_approvals) == 2
    first.shutdown()
    del first

    # --- process two: nothing in memory, everything from the database
    second = build_runtime(db_settings, database=db)
    reloaded = second.runs.get(run_id)

    assert reloaded.status is RunStatus.AWAITING_APPROVAL
    assert {p.tool_name for p in reloaded.pending_approvals} == {
        "send_email",
        "complete_task",
    }
    assert reloaded.messages, "message history must be rehydrated to resume"
    assert reloaded.deferred is not None, "deferred requests must be rehydrated"

    email = next(p for p in reloaded.pending_approvals if p.tool_name == "send_email")
    task = next(p for p in reloaded.pending_approvals if p.tool_name == "complete_task")

    resumed = await second.runner.resume(
        run_id,
        [
            ApprovalDecision(tool_call_id=email.tool_call_id, approved=True),
            ApprovalDecision(tool_call_id=task.tool_call_id, approved=False),
        ],
    )

    assert resumed.status is RunStatus.PARTIAL
    assert resumed.output

    # The approved action took effect in the database, the denied one did not.
    workspace = WorkspaceService(PostgresWorkspaceStore(db, ORG))
    thread = next(t for t in workspace.email_summary(limit=50).threads if t.id == "eml_001")
    assert thread.needs_response is False
    assert "tsk_001" in {t.id for t in workspace.todays_tasks()}

    # And the outcome is durable too.
    third = build_runtime(db_settings, database=db)
    final = third.runs.get(run_id)
    assert final.status is RunStatus.PARTIAL
    assert {c.tool_name: c.status.value for c in final.tool_calls}["send_email"] == "executed"
    assert {c.tool_name: c.status.value for c in final.tool_calls}["complete_task"] == "denied"

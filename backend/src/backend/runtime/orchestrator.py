"""Run orchestration and the human-in-the-loop approval gate.

This is where a run's *lifecycle* lives: start it, pause it when the agent
wants to do something consequential, resume it once a human has decided.
:mod:`backend.runtime.runner` holds the stateless execution primitives; nothing
else in the codebase drives an agent.

The gate is not advisory. A tool declares ``requires_approval`` and the
registry constructs it that way, so PydanticAI suspends the run before the
function is ever called. There is no code path that executes a gated tool
without an explicit :class:`ApprovalDecision`.

Every state change is published to the event bus, which is what the SSE
transport streams. The orchestrator itself knows nothing about HTTP.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic_ai import (
    AgentRunResultEvent,
    DeferredToolRequests,
    FunctionToolCallEvent,
    PartDeltaEvent,
)
from pydantic_ai.messages import TextPartDelta
from pydantic_ai.tools import DeferredToolResults, ToolApproved, ToolDenied

from backend.runtime.agent import AgentRegistry, AgentSpec
from backend.runtime.events import EventBus, EventType
from backend.runtime.logger import get_logger
from backend.runtime.runner import UsageSnapshot, validate_prompt
from backend.runtime.runs import (
    ApprovalDecision,
    PendingApproval,
    Run,
    RunStatus,
    RunStore,
    ToolCallRecord,
)
from backend.runtime.tools import ToolRegistry

__all__ = ["AgentRunner", "RunNotResumableError", "StartedRun", "UnknownApprovalError"]

log = get_logger(__name__)


class RunNotResumableError(RuntimeError):
    """A resume was attempted on a run that is not waiting for approval."""

    def __init__(self, run_id: str, status: RunStatus) -> None:
        super().__init__(f"run {run_id} is {status.value}, not awaiting approval")
        self.run_id = run_id
        self.status = status


class UnknownApprovalError(ValueError):
    """A decision referenced a tool call the run is not waiting on."""

    def __init__(self, tool_call_id: str) -> None:
        super().__init__(f"no pending approval with tool_call_id {tool_call_id!r}")
        self.tool_call_id = tool_call_id


@dataclass(frozen=True, slots=True)
class StartedRun:
    """A run executing in the background, plus its handle."""

    run: Run
    task: asyncio.Task[Run]


class AgentRunner:
    """Drives agent runs and mediates the approval gate."""

    def __init__(
        self,
        *,
        agents: AgentRegistry,
        runs: RunStore,
        bus: EventBus,
        tools: ToolRegistry | None = None,
        timeout_seconds: float = 120.0,
        max_prompt_chars: int = 20_000,
    ) -> None:
        self._agents = agents
        self._runs = runs
        self._bus = bus
        self._tools = tools
        self._timeout = timeout_seconds
        self._max_prompt_chars = max_prompt_chars
        # Strong references, so a background run is not garbage collected
        # mid-flight while only the event loop holds it.
        self._tasks: set[asyncio.Task[Run]] = set()

    @property
    def bus(self) -> EventBus:
        return self._bus

    # ---- Public API ------------------------------------------------------

    def _open(self, agent_name: str, prompt: str, session_id: str | None) -> tuple[Run, AgentSpec]:
        spec = self._agents.get(agent_name)  # -> AgentNotFoundError
        validate_prompt(prompt, self._max_prompt_chars)  # -> PromptTooLongError

        run = self._runs.create(
            agent=spec.name, model=spec.model, prompt=prompt, session_id=session_id
        )
        self._bus.publish(
            run.id,
            EventType.RUN_STARTED,
            agent=spec.name,
            model=spec.model,
            prompt=prompt,
        )
        return run, spec

    async def start(self, agent_name: str, prompt: str, *, session_id: str | None = None) -> Run:
        """Run to completion. Returns when it finishes, fails, or pauses for approval."""
        run, spec = self._open(agent_name, prompt, session_id)
        return await self._execute(run, spec, user_prompt=prompt)

    async def begin(
        self, agent_name: str, prompt: str, *, session_id: str | None = None
    ) -> StartedRun:
        """Start a run in the background and return immediately.

        Used by the streaming transport: the caller subscribes to the event bus
        and relays events as they are published. Validation errors still raise
        here, before any stream is opened.
        """
        run, spec = self._open(agent_name, prompt, session_id)
        task = asyncio.create_task(
            self._execute(run, spec, user_prompt=prompt), name=f"run:{run.id}"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return StartedRun(run=run, task=task)

    async def resume(self, run_id: str, decisions: Sequence[ApprovalDecision]) -> Run:
        """Apply the user's approval decisions and continue the run."""
        run = self._runs.get(run_id)  # -> RunNotFoundError

        if run.status is not RunStatus.AWAITING_APPROVAL or run.deferred is None:
            raise RunNotResumableError(run.id, run.status)

        pending_ids = {approval.tool_call_id for approval in run.pending_approvals}
        by_id: dict[str, ApprovalDecision] = {}
        for decision in decisions:
            if decision.tool_call_id not in pending_ids:
                raise UnknownApprovalError(decision.tool_call_id)
            by_id[decision.tool_call_id] = decision

        missing = pending_ids - set(by_id)
        if missing:
            # Anything left undecided is denied. Silence must never approve.
            for tool_call_id in missing:
                by_id[tool_call_id] = ApprovalDecision(
                    tool_call_id=tool_call_id,
                    approved=False,
                    reason="No decision supplied; denied by default.",
                )

        results = run.deferred.build_results(
            approvals={
                tool_call_id: (
                    ToolApproved()
                    if decision.approved
                    else ToolDenied(decision.reason or "The user declined this action.")
                )
                for tool_call_id, decision in by_id.items()
            }
        )

        for approval in run.pending_approvals:
            decision = by_id[approval.tool_call_id]
            run.tool_calls.append(
                ToolCallRecord(
                    tool_name=approval.tool_name,
                    tool_call_id=approval.tool_call_id,
                    args=approval.args,
                    approved=decision.approved,
                )
            )
            self._bus.publish(
                run.id,
                EventType.APPROVAL_RESOLVED,
                tool_call_id=approval.tool_call_id,
                tool_name=approval.tool_name,
                approved=decision.approved,
                reason=decision.reason,
            )

        log.info(
            "run.resumed",
            run_id=run.id,
            approved=sum(1 for d in by_id.values() if d.approved),
            denied=sum(1 for d in by_id.values() if not d.approved),
        )

        run.status = RunStatus.RUNNING
        run.pending_approvals = []
        run.deferred = None
        run.touch()

        self._bus.reopen(run.id)
        self._bus.publish(run.id, EventType.RUN_RESUMED)

        spec = self._agents.get(run.agent)
        return await self._execute(run, spec, deferred_results=results)

    # ---- Execution -------------------------------------------------------

    async def _execute(
        self,
        run: Run,
        spec: AgentSpec,
        *,
        user_prompt: str | None = None,
        deferred_results: DeferredToolResults | None = None,
    ) -> Run:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout):
                await self._consume_stream(
                    run, spec, user_prompt=user_prompt, deferred_results=deferred_results
                )
        except TimeoutError:
            return self._fail(
                run, started, code="agent_timeout", message=f"Run exceeded {self._timeout}s."
            )
        except Exception as exc:
            log.exception("run.failed", run_id=run.id, agent=spec.name, error=str(exc))
            return self._fail(
                run, started, code="internal_error", message="An internal error occurred."
            )

        run.duration_ms += int((time.perf_counter() - started) * 1000)
        run.touch()
        return run

    async def _consume_stream(
        self,
        run: Run,
        spec: AgentSpec,
        *,
        user_prompt: str | None,
        deferred_results: DeferredToolResults | None,
    ) -> None:
        context = spec.agent.run_stream_events(
            user_prompt,
            message_history=run.messages or None,
            deferred_tool_results=deferred_results,
        )

        async with context as stream:
            async for event in stream:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    delta = event.delta.content_delta
                    if delta:
                        self._bus.publish(run.id, EventType.RUN_TOKEN, delta=delta)

                elif isinstance(event, FunctionToolCallEvent):
                    part = event.part
                    args = part.args_as_dict() if hasattr(part, "args_as_dict") else {}
                    run.tool_calls.append(
                        ToolCallRecord(
                            tool_name=part.tool_name,
                            tool_call_id=part.tool_call_id,
                            args=args,
                        )
                    )
                    self._bus.publish(
                        run.id,
                        EventType.TOOL_CALLED,
                        tool_name=part.tool_name,
                        tool_call_id=part.tool_call_id,
                        args=args,
                    )

                elif isinstance(event, AgentRunResultEvent):
                    self._finish(run, event)

    def _finish(self, run: Run, event: AgentRunResultEvent[object]) -> None:
        result = event.result
        run.messages = list(result.all_messages())
        run.usage = UsageSnapshot.from_run_usage(result.usage)
        output = result.output

        if isinstance(output, DeferredToolRequests):
            run.deferred = output
            run.pending_approvals = [
                PendingApproval(
                    tool_call_id=call.tool_call_id,
                    tool_name=call.tool_name,
                    args=call.args_as_dict() if hasattr(call, "args_as_dict") else {},
                    description=self._describe(call.tool_name),
                )
                for call in output.approvals
            ]
            run.status = RunStatus.AWAITING_APPROVAL
            run.touch()

            for approval in run.pending_approvals:
                self._bus.publish(
                    run.id,
                    EventType.APPROVAL_REQUIRED,
                    tool_call_id=approval.tool_call_id,
                    tool_name=approval.tool_name,
                    args=approval.args,
                    description=approval.description,
                )
            log.info("run.awaiting_approval", run_id=run.id, pending=len(run.pending_approvals))
            # The stream ends here; the transport must not treat that as
            # completion, so the channel stays open for the resumed run.
            self._bus.close(run.id)
            return

        run.output = str(output)
        run.status = RunStatus.COMPLETED
        run.touch()
        self._bus.publish(
            run.id,
            EventType.RUN_COMPLETED,
            output=run.output,
            usage=_usage_payload(run.usage),
        )
        self._bus.close(run.id)
        log.info("run.completed", run_id=run.id, agent=run.agent)

    def _fail(self, run: Run, started: float, *, code: str, message: str) -> Run:
        run.status = RunStatus.FAILED
        run.error = message
        run.error_code = code
        run.duration_ms += int((time.perf_counter() - started) * 1000)
        run.touch()
        self._bus.publish(run.id, EventType.RUN_FAILED, code=code, message=message)
        self._bus.close(run.id)
        return run

    def _describe(self, tool_name: str) -> str:
        spec = self._tools.get(tool_name) if self._tools else None
        return spec.description.strip() if spec else ""


def _usage_payload(usage: UsageSnapshot | None) -> dict[str, int]:
    if usage is None:
        return {}
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
        "requests": usage.requests,
    }


def decisions_from_mapping(mapping: Mapping[str, bool]) -> list[ApprovalDecision]:
    """Convenience for callers holding a plain ``{tool_call_id: approved}`` map."""
    return [ApprovalDecision(tool_call_id=k, approved=v) for k, v in mapping.items()]

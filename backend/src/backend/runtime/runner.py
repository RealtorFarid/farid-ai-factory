"""Agent execution: the single place where an agent is actually invoked.

Both the JSON and the streaming API routes go through here, so timeout,
validation, usage accounting and logging behave identically for both.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from pydantic_ai.usage import RunUsage

from backend.runtime.agent import AgentSpec
from backend.runtime.logger import get_logger

__all__ = [
    "AgentTimeoutError",
    "DoneEvent",
    "PromptTooLongError",
    "RunOutcome",
    "StreamEvent",
    "TokenEvent",
    "UsageSnapshot",
    "run_agent",
    "stream_agent",
]

log = get_logger(__name__)


class PromptTooLongError(ValueError):
    """The prompt exceeded ``Settings.max_prompt_chars``."""

    def __init__(self, length: int, limit: int) -> None:
        super().__init__(f"prompt is {length} characters; limit is {limit}")
        self.length = length
        self.limit = limit


class AgentTimeoutError(TimeoutError):
    """The agent did not finish within the configured timeout."""

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__(f"agent run exceeded {timeout_seconds}s")
        self.timeout_seconds = timeout_seconds


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    """Token accounting for a single run."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    requests: int

    @classmethod
    def from_run_usage(cls, usage: RunUsage) -> UsageSnapshot:
        return cls(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            requests=usage.requests,
        )


@dataclass(frozen=True, slots=True)
class RunOutcome:
    output: str
    usage: UsageSnapshot
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """An incremental chunk of model output."""

    delta: str


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """Terminal event of a stream, carrying the assembled result."""

    output: str
    usage: UsageSnapshot
    duration_ms: int


StreamEvent = TokenEvent | DoneEvent


def validate_prompt(prompt: str, max_chars: int) -> None:
    """Reject prompts that would be expensive or abusive."""
    if len(prompt) > max_chars:
        raise PromptTooLongError(len(prompt), max_chars)


async def run_agent(spec: AgentSpec, prompt: str, *, timeout_seconds: float) -> RunOutcome:
    """Run an agent to completion.

    Raises :class:`AgentTimeoutError` if the run exceeds ``timeout_seconds``.
    """
    started = time.perf_counter()
    log.info("agent.run.started", agent=spec.name, model=spec.model, prompt_chars=len(prompt))

    try:
        async with asyncio.timeout(timeout_seconds):
            result = await spec.agent.run(prompt)
    except TimeoutError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.warning("agent.run.timeout", agent=spec.name, duration_ms=duration_ms)
        raise AgentTimeoutError(timeout_seconds) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    usage = UsageSnapshot.from_run_usage(result.usage)
    log.info(
        "agent.run.finished",
        agent=spec.name,
        duration_ms=duration_ms,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
    return RunOutcome(output=str(result.output), usage=usage, duration_ms=duration_ms)


async def stream_agent(
    spec: AgentSpec, prompt: str, *, timeout_seconds: float
) -> AsyncIterator[StreamEvent]:
    """Stream an agent run as incremental token events followed by a done event."""
    started = time.perf_counter()
    log.info("agent.stream.started", agent=spec.name, model=spec.model, prompt_chars=len(prompt))
    chunks: list[str] = []

    try:
        async with asyncio.timeout(timeout_seconds):
            async with spec.agent.run_stream(prompt) as stream:
                async for delta in stream.stream_text(delta=True):
                    chunks.append(delta)
                    yield TokenEvent(delta=delta)
                usage = UsageSnapshot.from_run_usage(stream.usage)
    except TimeoutError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log.warning("agent.stream.timeout", agent=spec.name, duration_ms=duration_ms)
        raise AgentTimeoutError(timeout_seconds) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "agent.stream.finished",
        agent=spec.name,
        duration_ms=duration_ms,
        output_tokens=usage.output_tokens,
    )
    yield DoneEvent(output="".join(chunks), usage=usage, duration_ms=duration_ms)

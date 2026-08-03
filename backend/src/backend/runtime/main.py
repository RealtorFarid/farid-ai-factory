"""Smoke test against a real model, without going through HTTP.

    uv run python -m backend.runtime.main "your prompt here"

Requires real LLM credentials; the HTTP API is the normal way to run agents.
"""

from __future__ import annotations

import asyncio
import sys

from backend.runtime.agent import build_registry
from backend.runtime.config import get_settings
from backend.runtime.logger import configure_logging, get_logger
from backend.runtime.runner import run_agent

DEFAULT_PROMPT = "Introduce yourself in one sentence, then list your operating rules."


async def _run(prompt: str) -> int:
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    log = get_logger(__name__)

    if not settings.llm_configured:
        log.error("smoke.no_credentials", hint="set PROPILOT_OPENAI_API_KEY in backend/.env")
        return 1

    spec = build_registry(settings).default
    outcome = await run_agent(spec, prompt, timeout_seconds=settings.agent_timeout_seconds)

    log.info(
        "smoke.completed",
        agent=spec.name,
        duration_ms=outcome.duration_ms,
        total_tokens=outcome.usage.total_tokens,
    )
    sys.stdout.write(f"\n{outcome.output}\n")
    return 0


def main() -> int:
    prompt = " ".join(sys.argv[1:]) or DEFAULT_PROMPT
    return asyncio.run(_run(prompt))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

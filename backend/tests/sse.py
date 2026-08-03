"""Shared Server-Sent Events parsing for tests."""

from __future__ import annotations

import json
from typing import Any

__all__ = ["parse_sse"]


def parse_sse(raw: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into ``(event_name, payload)`` pairs."""
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = "", "{}"
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        frames.append((event, json.loads(data)))
    return frames

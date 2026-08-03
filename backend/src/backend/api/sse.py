"""Server-Sent Events encoding.

One encoder, used by every streaming endpoint, so frame format cannot drift
between them.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["SSE_HEADERS", "sse_frame"]

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Stop nginx and friends from buffering the stream into uselessness.
    "X-Accel-Buffering": "no",
}


def sse_frame(event: str, data: dict[str, Any], *, event_id: int | None = None) -> str:
    """Encode one SSE frame.

    ``event_id`` becomes the SSE ``id:`` field, which browsers echo back as
    ``Last-Event-ID`` on reconnect — that is how a dropped stream resumes
    without replaying everything.
    """
    head = f"id: {event_id}\n" if event_id is not None else ""
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"{head}event: {event}\ndata: {body}\n\n"

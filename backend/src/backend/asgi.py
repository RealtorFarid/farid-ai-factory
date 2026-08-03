"""ASGI entry point.

Used by process managers that expect a module-level application object::

    uvicorn backend.asgi:app
"""

from __future__ import annotations

from backend.api.app import create_app

app = create_app()

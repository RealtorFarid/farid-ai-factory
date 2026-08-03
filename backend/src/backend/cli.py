"""Console entry point: ``propilot`` starts the HTTP API."""

from __future__ import annotations

import uvicorn

from backend.runtime.config import get_settings
from backend.runtime.logger import configure_logging, get_logger


def main() -> None:
    """Run the API server using the configured host, port and log settings."""
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    log = get_logger(__name__)
    log.info(
        "server.starting",
        host=settings.host,
        port=settings.port,
        environment=settings.environment,
        reload=settings.debug,
    )

    uvicorn.run(
        "backend.asgi:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_config=None,  # logging is owned by structlog
        access_log=False,  # RequestContextMiddleware emits the access line
    )


if __name__ == "__main__":  # pragma: no cover
    main()

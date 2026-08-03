"""Propilot AI — agent runtime and HTTP API.

This module is intentionally free of side effects: importing it must never
print, read the environment, or open a network connection.
"""

from __future__ import annotations

__all__ = ["APP_NAME", "__version__"]

__version__ = "0.1.0"
APP_NAME = "Propilot AI"

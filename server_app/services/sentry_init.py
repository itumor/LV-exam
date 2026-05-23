"""Sentry init service (T-020).

Re-exports the Sentry bootstrap + ``capture_exception`` helper from
:mod:`server_app.core`. Loaded once at startup by :func:`server_app.serve`.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    capture_exception,
    init_sentry,
    log_event,
)

__all__ = ["capture_exception", "init_sentry", "log_event"]

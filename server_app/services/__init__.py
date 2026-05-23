"""Cross-cutting service modules (T-020).

Each submodule re-exports a coherent slice of the service layer from
:mod:`server_app.core`. The intent is to make ownership obvious in code
review — touching the quota module is reviewed by the platform owner;
touching the evaluator is reviewed by the AI scoring owner — without
moving any code in the T-020 PR (which would risk subtle dispatch
changes). A follow-up task (T-020a) will lift the bodies into these
modules.
"""

from __future__ import annotations

from . import (  # noqa: F401
    attempts,
    auth_store,
    evaluator,
    quota,
    sentry_init,
)

__all__ = [
    "attempts",
    "auth_store",
    "evaluator",
    "quota",
    "sentry_init",
]

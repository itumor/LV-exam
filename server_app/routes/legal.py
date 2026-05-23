"""Legal-page routes (T-011 → T-020).

Serves the markdown-rendered Terms, Privacy, Cookie, Refund, and DPA
pages introduced by T-011. The implementation lives in
:mod:`server_app.core` (``try_serve_legal_page``); this module documents
the route table and re-exports the helper for the audit list.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    LEGAL_PAGES,
    LEGAL_ROOT,
    try_serve_legal_page,
)

ROUTES: list[tuple[str, str]] = [
    ("GET", "/legal/terms"),
    ("GET", "/legal/privacy"),
    ("GET", "/legal/cookies"),
    ("GET", "/legal/refund"),
    ("GET", "/legal/dpa"),
]

__all__ = ["LEGAL_PAGES", "LEGAL_ROOT", "ROUTES", "try_serve_legal_page"]

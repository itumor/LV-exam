"""ThreadingHTTPServer-compatible request handler (T-020).

Re-exports :class:`AppHandler` and :class:`DualStackServer` from
:mod:`server_app.core`. They remain in ``core`` because the load-time
hook chain (rate-limit → metrics → debug-gate → uploads) monkey-patches
the ``do_GET`` / ``do_POST`` methods at import time, and the chain has
to execute against the original class object. Splitting the class out
would have required re-running the patch chain against the new class
which is a behaviour-changing operation we deliberately avoid for the
T-020 PR.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    AppHandler,
    DualStackServer,
)

__all__ = ["AppHandler", "DualStackServer"]

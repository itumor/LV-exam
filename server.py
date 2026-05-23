#!/usr/bin/env python3
"""Backwards-compatibility shim for the modularised ``server_app`` package.

T-020 split the 5800-line ``server.py`` monolith into the ``server_app``
package. This file is preserved so:

* ``python3 server.py`` still boots the same HTTP server on the same
  port (used by ``playwright.config.js`` and the Fly.io ``CMD``).
* ``import server`` continues to work for every test under
  ``tests/server/`` and the legacy ``scripts/`` helpers. The module is
  *aliased* to :mod:`server_app.core` via ``sys.modules`` so that
  ``patch.object(server, "AUTH_DB_PATH", ...)`` and similar test
  patterns continue to mutate the underlying module's globals — which
  is what the actual route handlers read at runtime.

The actual implementation lives in :mod:`server_app.core`. The hook
ordering (rate-limit → metrics → debug-gate → routing) is documented in
:mod:`server_app.__init__`.
"""

from __future__ import annotations

import sys

# Importing ``server_app`` triggers the side-effecting hook chain that
# wires the rate-limit / metrics / debug-gate / uploads middleware onto
# ``AppHandler``. After this import the package and its ``core`` module
# are both registered in ``sys.modules``.
from server_app import core as _core, serve as _serve

if __name__ == "__main__":
    # Run as ``python3 server.py``: boot the HTTP server. We intentionally
    # do NOT alias ``__main__`` to ``server_app.core`` because that would
    # rewrite the running module record and confuse traceback printing.
    raise SystemExit(_serve())

# Imported as ``import server`` (e.g. from the test suite). Alias to
# ``server_app.core`` so attribute reads/writes — especially
# ``unittest.mock.patch.object(server, "AUTH_DB_PATH", …)`` — propagate
# to the underlying module that the live request handlers read.
sys.modules[__name__] = _core

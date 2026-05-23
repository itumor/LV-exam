"""Speaking-upload routes (T-018 → T-020).

Owns the audio upload + playback endpoints introduced by T-018. The
T-018 hook block in the historic ``server.py`` has been kept inline in
:mod:`server_app.core` so it executes in the documented hook order
(after the rate-limit / metrics / debug-gate middleware).

Routes:

* ``POST /api/uploads/speaking?attempt_id=…&task_id=…`` — store audio.
* ``GET  /api/uploads/speaking/<attempt_id>/<task_id>``  — replay audio.
* ``GET  /api/uploads/speaking/<upload_id>`` — legacy single-ID replay.
"""

from __future__ import annotations

from server_app.core import (  # noqa: F401
    MAX_AUDIO_BYTES,
    _ALLOWED_AUDIO_TYPES,
    _safe_speaking_audio_path,
    _t018_handle_upload_get,
    _t018_handle_upload_post,
    store_speaking_upload,
)

ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/uploads/speaking"),
    ("GET", "/api/uploads/speaking/<attempt_id>/<task_id>"),
    ("GET", "/api/uploads/speaking/<upload_id>"),
]

__all__ = [
    "MAX_AUDIO_BYTES",
    "ROUTES",
    "_ALLOWED_AUDIO_TYPES",
    "_safe_speaking_audio_path",
    "_t018_handle_upload_get",
    "_t018_handle_upload_post",
    "store_speaking_upload",
]

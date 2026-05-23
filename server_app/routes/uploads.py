"""Speaking-upload routes (T-018 -> T-020 -> T-024).

Owns the audio upload + playback endpoints introduced by T-018. The
T-018 hook block in the historic ``server.py`` has been kept inline in
:mod:`server_app.core` so it executes in the documented hook order
(after the rate-limit / metrics / debug-gate middleware).

T-024 wires the speaking upload route into the server-enforced
entitlement gate. The reasoning: a speaking task is part of a paid
attempt, so the same ``exam_unlock`` entitlement that gates
``POST /api/attempts/start`` also guards the speaking upload that
belongs to it. Free-tier and frozen accounts receive HTTP 402 from the
end-of-core hook block before the upload handler runs, so we never
write audio bytes to disk for a user we will refuse to score.

Routes:

* ``POST /api/uploads/speaking?attempt_id=...&task_id=...`` -- store audio
  (gated by T-024: requires ``exam_unlock``).
* ``GET  /api/uploads/speaking/<attempt_id>/<task_id>``  -- replay audio.
* ``GET  /api/uploads/speaking/<upload_id>`` -- legacy single-ID replay.
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
from server_app.services.entitlements import (  # noqa: F401
    EntitlementError,
    entitled,
    require_entitlement,
)

ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/uploads/speaking"),
    ("GET", "/api/uploads/speaking/<attempt_id>/<task_id>"),
    ("GET", "/api/uploads/speaking/<upload_id>"),
]

__all__ = [
    "EntitlementError",
    "MAX_AUDIO_BYTES",
    "ROUTES",
    "_ALLOWED_AUDIO_TYPES",
    "_safe_speaking_audio_path",
    "_t018_handle_upload_get",
    "_t018_handle_upload_post",
    "entitled",
    "require_entitlement",
    "store_speaking_upload",
]

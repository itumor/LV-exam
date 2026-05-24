"""Voice scoring routes (T-046).

Owns ``POST /api/voice/score`` — the pronunciation-scoring endpoint
added on top of the T-018 speaking-capture pipeline. The body is

::

    {
      "expected_text": "Labdien, kā jums klājas?",
      "audio_url": "/api/uploads/speaking/<attempt_id>/<task_id>"
    }

and the response is

::

    {
      "transcript": "labdien ka jums klajas",
      "transcript_confidence": 0.81,
      "accuracy_percent": 72.7,
      "phoneme_score": 86.3,
      "word_errors": [{"expected": "kā", "got": "ka", "kind": "substitution"}],
      "suggestions": ["You said 'ka', but the word is 'kā' — watch the long vowels (garumzīme)."],
      "expected_tokens": [...],
      "transcript_tokens": [...],
      "provider": "groq",
      "model": "whisper-large-v3-turbo"
    }

The actual dispatch wiring is installed by a tail-of-file hook in
:mod:`server_app.core` (``_t046_install_voice_score_route``); this
module re-exports the helpers + the route audit tuple so the
modularisation contract test can prove the route is registered.
"""

from __future__ import annotations


# T-046 dispatch handler lives in :mod:`server_app.core` and is wired by a
# tail-of-file hook block (``_t046_install_voice_score_route``). We expose
# it via a lazy attribute lookup so importing this module during the
# routes-package initialisation never triggers the partially-initialised
# ``server_app.core`` symbol lookup (the circular-import trap flagged in CI
# during the v1.1.0 release attempt).
def __getattr__(name: str):  # noqa: D401 - matches PEP 562 module hook
    if name == "_t046_handle_voice_score":
        from server_app import core  # local import — only at access time

        return core._t046_handle_voice_score
    raise AttributeError(f"module 'server_app.routes.voice' has no attribute {name!r}")


ROUTES: list[tuple[str, str]] = [
    ("POST", "/api/voice/score"),
]

__all__ = [
    "ROUTES",
    "_t046_handle_voice_score",
]

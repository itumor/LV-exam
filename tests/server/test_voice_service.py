"""T-046 voice pipeline tests.

Covers three layers:

1. :mod:`server_app.services.voice` — pure-Python scoring + helpers.
   No network access. Exercises edit-distance alignment, suggestion
   generation, syllabification, and the high-level
   :func:`score_voice_submission` glue with a mocked STT response.

2. The route registry — ``POST /api/voice/score`` must appear in the
   :data:`server_app.routes.ROUTES` audit list and the AppHandler must
   carry the ``_t046_installed`` marker (mirrors the audit pattern used
   by the T-022 / T-037 hooks).

3. End-to-end smoke through the ``AppHandler`` dispatch chain: the
   route validates input, calls a mocked transcribe + scoring path,
   reserves a daily quota slot, and returns a populated JSON body.

The mocked STT uses the public ``LVCODEX_VOICE_FAKE_TRANSCRIPT`` env hook
so no API keys are needed for CI.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import server
import server_app
from server_app.services import voice as voice_service
from server_app.services import quota as quota_service


# ---------------------------------------------------------------------------
# Pure scoring tests (no I/O)
# ---------------------------------------------------------------------------


class TokenizationAndNormalizationTests(unittest.TestCase):
    def test_tokenize_strips_punctuation_keeps_diacritics(self) -> None:
        tokens = voice_service.tokenize("Labdien, kā jums klājas?")
        self.assertEqual(tokens, ["labdien", "kā", "jums", "klājas"])

    def test_normalize_lowercases_and_nfc(self) -> None:
        # Combining diacritic (NFD) should fold to a single NFC codepoint.
        nfd = "māte"  # a + combining macron
        self.assertEqual(voice_service.normalize_text(nfd), "māte")

    def test_fold_diacritics_drops_garumzime(self) -> None:
        self.assertEqual(voice_service.fold_diacritics("māte"), "mate")
        self.assertEqual(voice_service.fold_diacritics("ļauj"), "lauj")

    def test_syllabify_breaks_on_vowels(self) -> None:
        # Every vowel starts a syllable. The exact split is approximate
        # but it must be deterministic and lossless (concatenation =
        # original).
        for word in ["māte", "labdien", "klājas", "jums", "ko"]:
            syllables = voice_service.syllabify(word)
            self.assertEqual("".join(syllables), word)


class ScorePronunciationTests(unittest.TestCase):
    """Edit-distance + alignment-based scoring tests (deterministic)."""

    def test_perfect_match_yields_100_percent(self) -> None:
        result = voice_service.score_pronunciation(
            "Labdien, kā jums klājas?",
            "Labdien, kā jums klājas?",
        )
        self.assertEqual(result.accuracy_percent, 100.0)
        self.assertEqual(result.phoneme_score, 100.0)
        self.assertEqual(result.word_errors, [])
        self.assertEqual(result.suggestions, [])

    def test_long_vowel_substitution_emits_garumzime_hint(self) -> None:
        result = voice_service.score_pronunciation("māte", "mate")
        # Exactly one substitution word-error.
        self.assertEqual(len(result.word_errors), 1)
        err = result.word_errors[0]
        self.assertEqual(err.expected, "māte")
        self.assertEqual(err.got, "mate")
        self.assertEqual(err.kind, "substitution")
        # The garumzīme hint must trigger when the only difference is a
        # long-vowel diacritic loss.
        self.assertTrue(
            any("garumzīme" in s for s in result.suggestions),
            f"expected garumzīme hint, got {result.suggestions!r}",
        )
        # Phoneme-level score should still be quite high — the learner
        # got the word right except for the diacritic.
        self.assertGreater(result.phoneme_score, 50.0)

    def test_soft_consonant_substitution_emits_mikstinajums_hint(self) -> None:
        # ļauj -> lauj : single ļ→l substitution.
        result = voice_service.score_pronunciation("ļauj", "lauj")
        self.assertEqual(len(result.word_errors), 1)
        self.assertTrue(
            any("mīkstinājums" in s for s in result.suggestions),
            f"expected soft-consonant hint, got {result.suggestions!r}",
        )

    def test_deletion_produces_missed_word_hint(self) -> None:
        result = voice_service.score_pronunciation(
            "labdien kā jums",
            "labdien",
        )
        # Two missing words.
        kinds = [err.kind for err in result.word_errors]
        self.assertEqual(kinds.count("deletion"), 2)
        self.assertTrue(
            any("Missed the word" in s for s in result.suggestions),
        )
        # 1 / 3 expected tokens matched -> ~33%.
        self.assertAlmostEqual(result.accuracy_percent, 33.3, places=0)

    def test_extra_words_produce_insertion_hint(self) -> None:
        result = voice_service.score_pronunciation(
            "labdien",
            "labdien eee paldies",
        )
        kinds = [err.kind for err in result.word_errors]
        self.assertEqual(kinds.count("insertion"), 2)
        self.assertTrue(
            any("Extra word" in s for s in result.suggestions),
        )

    def test_empty_expected_text_yields_neutral_score(self) -> None:
        # No reference text + empty transcript = full credit (the
        # caller should not have invoked us, but we don't crash).
        result = voice_service.score_pronunciation("", "")
        self.assertEqual(result.accuracy_percent, 100.0)

    def test_max_suggestions_caps_output(self) -> None:
        result = voice_service.score_pronunciation(
            "viens divi trīs četri pieci seši septiņi astoņi deviņi desmit",
            "",
            max_suggestions=3,
        )
        self.assertEqual(len(result.suggestions), 3)


# ---------------------------------------------------------------------------
# High-level score_voice_submission (with mocked STT)
# ---------------------------------------------------------------------------


class ScoreVoiceSubmissionTests(unittest.TestCase):
    """Verify the end-to-end ``transcribe + score`` glue.

    Uses a manually-injected ``transcribe_fn`` so no network call
    happens. Each test confirms one observable behaviour of the
    response envelope.
    """

    def _fake_transcribe(self, transcript: str, confidence: float = 0.85):
        def fn(audio_bytes, *, audio_filename, audio_mime, language):
            return voice_service.VoiceTranscription(
                transcript=transcript,
                confidence=confidence,
                raw={"text": transcript, "fake": True},
                provider="fake",
                model="fake-whisper",
            )
        return fn

    def test_response_shape_matches_route_contract(self) -> None:
        body = voice_service.score_voice_submission(
            expected_text="Labdien, kā jums klājas?",
            audio_bytes=b"fake-audio-blob",
            transcribe_fn=self._fake_transcribe("Labdien, kā jums klājas?", confidence=0.9),
        )
        # All keys documented in the route docstring must be present.
        for key in (
            "transcript",
            "transcript_confidence",
            "accuracy_percent",
            "phoneme_score",
            "word_errors",
            "suggestions",
            "expected_tokens",
            "transcript_tokens",
            "provider",
            "model",
        ):
            self.assertIn(key, body, f"missing key: {key}")
        self.assertEqual(body["accuracy_percent"], 100.0)
        self.assertEqual(body["provider"], "fake")

    def test_confidence_passes_through(self) -> None:
        body = voice_service.score_voice_submission(
            expected_text="paldies",
            audio_bytes=b"x",
            transcribe_fn=self._fake_transcribe("paldies", confidence=0.42),
        )
        self.assertEqual(body["transcript_confidence"], 0.42)

    def test_partial_match_drops_accuracy_below_full(self) -> None:
        body = voice_service.score_voice_submission(
            expected_text="Labdien, kā jums klājas?",
            audio_bytes=b"x",
            transcribe_fn=self._fake_transcribe("labdien ka jums klajas"),
        )
        # Diacritic loss on two tokens out of four → 50% accuracy.
        self.assertLess(body["accuracy_percent"], 100.0)
        self.assertGreater(body["accuracy_percent"], 30.0)
        # Each diacritic-loss substitution should produce a garumzīme
        # hint.
        garumzime_hints = [
            s for s in body["suggestions"] if "garumzīme" in s
        ]
        self.assertGreaterEqual(len(garumzime_hints), 1)


# ---------------------------------------------------------------------------
# transcribe_audio with the LVCODEX_VOICE_FAKE_TRANSCRIPT hook
# ---------------------------------------------------------------------------


class TranscribeAudioFakeHookTests(unittest.TestCase):
    """The fake-transcript env hook short-circuits the HTTP call.

    Without this hook the function would attempt to reach Groq's
    /audio/transcriptions endpoint, requiring a real API key.
    """

    def test_fake_env_var_is_returned_verbatim(self) -> None:
        with patch.dict(
            os.environ,
            {"LVCODEX_VOICE_FAKE_TRANSCRIPT": "labdien, kā tev klājas"},
            clear=False,
        ):
            result = voice_service.transcribe_audio(b"ignored-audio-bytes")
        self.assertEqual(result.transcript, "labdien, kā tev klājas")
        self.assertEqual(result.confidence, 1.0)
        self.assertEqual(result.provider, "fake")

    def test_no_api_key_raises_voice_config_error(self) -> None:
        # Disable the fake hook AND blank the Groq key so the config
        # resolution fails. We use clear=True on the empty env so the
        # parent process's GROQ_API_KEY does not leak through.
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(voice_service.VoiceConfigError):
                voice_service.voice_provider_config()


# ---------------------------------------------------------------------------
# Audit list: /api/voice/score must be in the route registry
# ---------------------------------------------------------------------------


class RouteRegistryTests(unittest.TestCase):
    def test_voice_score_route_listed(self) -> None:
        from server_app.routes import ROUTES
        pairs = {(m, p) for m, p, _owner in ROUTES}
        self.assertIn(("POST", "/api/voice/score"), pairs)

    def test_handler_marker_set(self) -> None:
        # The end-of-file hook in core.py must mark AppHandler so the
        # modularisation tests can audit the install order.
        self.assertTrue(
            getattr(server.AppHandler, "_t046_installed", False),
            "AppHandler._t046_installed marker missing",
        )


# ---------------------------------------------------------------------------
# Audio resolution helper (load_audio_from_t018)
# ---------------------------------------------------------------------------


class LoadAudioFromT018Tests(unittest.TestCase):
    """End-to-end audio resolution from a T-018 upload URL."""

    def test_resolves_new_layout_url(self) -> None:
        from audio_uploads import AudioUploadStore

        with tempfile.TemporaryDirectory() as tmp:
            store = AudioUploadStore(
                base_dir=Path(tmp),
                max_bytes=4096,
                allowed_mimes=("audio/webm",),
            )
            store.save(
                attempt_id="attempt1",
                task_id="speaking-task1-0",
                user_id="user-alpha",
                content_type="audio/webm",
                stream=b"fake-webm-bytes",
            )
            payload, mime = voice_service.load_audio_from_t018(
                "/api/uploads/speaking/attempt1/speaking-task1-0",
                upload_store=store,
                user_id="user-alpha",
            )
        self.assertEqual(payload, b"fake-webm-bytes")
        self.assertEqual(mime, "audio/webm")

    def test_rejects_url_outside_prefix(self) -> None:
        from audio_uploads import AudioUploadStore

        with tempfile.TemporaryDirectory() as tmp:
            store = AudioUploadStore(
                base_dir=Path(tmp),
                max_bytes=4096,
                allowed_mimes=("audio/webm",),
            )
            with self.assertRaises(ValueError):
                voice_service.load_audio_from_t018(
                    "/elsewhere/foo",
                    upload_store=store,
                    user_id="u",
                )


# ---------------------------------------------------------------------------
# End-to-end smoke: ``_t046_handle_voice_score`` via mocked AppHandler
# ---------------------------------------------------------------------------


class _StubHandler:
    """Minimal AppHandler stand-in for direct route tests.

    Implements the slice of the BaseHTTPRequestHandler API that the
    route uses (``rfile``, ``headers``, ``wfile``, ``send_response``,
    ``send_header``, ``end_headers``) so we can drive the handler
    function without binding a real socket.
    """

    def __init__(self, path: str, body: bytes, cookies: str = "") -> None:
        self.path = path
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.headers = {
            "Content-Length": str(len(body)),
            "Content-Type": "application/json",
            "Cookie": cookies,
            "Host": "localhost",
        }
        self.client_address = ("127.0.0.1", 0)
        self.status_code: int | None = None
        self._response_headers: list[tuple[str, str]] = []

    def send_response(self, status):
        self.status_code = int(status)

    def send_header(self, key, value):
        self._response_headers.append((key, str(value)))

    def end_headers(self):
        pass

    @property
    def response_json(self):
        # Strip header bytes if any — json_response only writes the
        # body via wfile.write, so wfile is the body alone.
        return json.loads(self.wfile.getvalue().decode("utf-8"))


class HandleVoiceScoreSmokeTests(unittest.TestCase):
    """Drive ``_t046_handle_voice_score`` directly with a stub handler."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "auth.sqlite3"
        self.auth_db_patch = patch.object(server, "AUTH_DB_PATH", self.db_path)
        self.auth_db_patch.start()
        # Reset the once-flag so the DDL re-runs for our tempfile.
        quota_service._reset_ledger_ddl_cache()
        server.init_auth_store()

        # Seed an account + active session.
        with server.db_connection() as conn:
            conn.execute(
                """
                INSERT INTO accounts (id, email, password_salt, password_hash,
                                       status, created_at, deleted_at, role)
                VALUES ('acct_voice', 'voice@example.test', 'salt', 'hash',
                        'active', '2026-05-05T00:00:00Z', NULL, 'user')
                """
            )
            self.token = server.create_session(conn, "acct_voice")

        # Point the T-018 store at our tempdir and seed one upload.
        from audio_uploads import AudioUploadStore
        self.upload_root = Path(self.tmpdir.name) / "uploads"
        self.store = AudioUploadStore(
            base_dir=self.upload_root,
            max_bytes=4096,
            allowed_mimes=("audio/webm",),
        )
        self.store.save(
            attempt_id="attempt1",
            task_id="speaking-task1-0",
            user_id="acct_voice",
            content_type="audio/webm",
            stream=b"fake-audio-bytes",
        )
        self.store_patch = patch.object(
            server, "T018_SPEAKING_UPLOAD_STORE", self.store
        )
        self.store_patch.start()

        # Use the fake-transcript hook so no network call.
        self.env_patch = patch.dict(
            os.environ,
            {
                "LVCODEX_VOICE_FAKE_TRANSCRIPT": "labdien kā jums klājas",
                "LVCODEX_AI_DAILY_LIMIT": "100",
            },
            clear=False,
        )
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        self.store_patch.stop()
        self.auth_db_patch.stop()
        self.tmpdir.cleanup()
        quota_service._reset_ledger_ddl_cache()

    def _make_handler(self, payload: dict) -> _StubHandler:
        body = json.dumps(payload).encode("utf-8")
        return _StubHandler(
            path="/api/voice/score",
            body=body,
            cookies=f"{server.AUTH_SESSION_COOKIE}={self.token}",
        )

    def test_happy_path_returns_score_envelope(self) -> None:
        handler = self._make_handler({
            "expected_text": "Labdien, kā jums klājas?",
            "audio_url": "/api/uploads/speaking/attempt1/speaking-task1-0",
        })
        server._t046_handle_voice_score(handler)
        self.assertEqual(handler.status_code, HTTPStatus.OK)
        body = handler.response_json
        self.assertEqual(body["transcript"], "labdien kā jums klājas")
        # The fake transcript is missing the trailing word; expect partial credit.
        self.assertLessEqual(body["accuracy_percent"], 100.0)
        self.assertGreater(body["accuracy_percent"], 50.0)
        self.assertIn("quota", body)
        self.assertEqual(body["quota"]["used"], 1)
        self.assertEqual(body["provider"], "fake")

    def test_missing_expected_text_returns_400(self) -> None:
        handler = self._make_handler({
            "audio_url": "/api/uploads/speaking/attempt1/speaking-task1-0",
        })
        server._t046_handle_voice_score(handler)
        self.assertEqual(handler.status_code, HTTPStatus.BAD_REQUEST)

    def test_missing_audio_url_returns_400(self) -> None:
        handler = self._make_handler({"expected_text": "Labdien"})
        server._t046_handle_voice_score(handler)
        self.assertEqual(handler.status_code, HTTPStatus.BAD_REQUEST)

    def test_unauthenticated_request_returns_401(self) -> None:
        body = json.dumps({
            "expected_text": "Labdien",
            "audio_url": "/api/uploads/speaking/attempt1/speaking-task1-0",
        }).encode("utf-8")
        handler = _StubHandler(path="/api/voice/score", body=body, cookies="")
        server._t046_handle_voice_score(handler)
        self.assertEqual(handler.status_code, HTTPStatus.UNAUTHORIZED)

    def test_cross_user_audio_url_returns_404(self) -> None:
        # The upload exists for acct_voice but the URL points at a
        # different attempt_id+task_id pair that was never saved.
        handler = self._make_handler({
            "expected_text": "Labdien",
            "audio_url": "/api/uploads/speaking/attempt1/no-such-task",
        })
        server._t046_handle_voice_score(handler)
        self.assertEqual(handler.status_code, HTTPStatus.NOT_FOUND)

    def test_quota_exhaustion_returns_429(self) -> None:
        with patch.dict(
            os.environ,
            {"LVCODEX_AI_DAILY_LIMIT": "1"},
            clear=False,
        ):
            handler = self._make_handler({
                "expected_text": "Labdien",
                "audio_url": "/api/uploads/speaking/attempt1/speaking-task1-0",
            })
            server._t046_handle_voice_score(handler)
            self.assertEqual(handler.status_code, HTTPStatus.OK)
            # Second call exhausts the quota.
            handler2 = self._make_handler({
                "expected_text": "Labdien",
                "audio_url": "/api/uploads/speaking/attempt1/speaking-task1-0",
            })
            server._t046_handle_voice_score(handler2)
            self.assertEqual(handler2.status_code, HTTPStatus.TOO_MANY_REQUESTS)

    def test_provider_failure_refunds_quota(self) -> None:
        """When the STT provider raises, the daily quota slot is released."""

        # Remove the fake-transcript hook so the real provider path
        # runs; then force a config error (no API key).
        self.env_patch.stop()
        with patch.dict(
            os.environ,
            {"LVCODEX_AI_DAILY_LIMIT": "5"},
            clear=True,
        ):
            handler = self._make_handler({
                "expected_text": "Labdien",
                "audio_url": "/api/uploads/speaking/attempt1/speaking-task1-0",
            })
            server._t046_handle_voice_score(handler)
            # Should return 503 (service unavailable / config error).
            self.assertEqual(handler.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
            # And the quota slot must have been refunded — usage 0.
            ledger = quota_service.AIQuotaLedger()
            self.assertEqual(ledger.current_usage("acct_voice", "free"), 0)
        # Restart the env patch so tearDown sees a stable env.
        self.env_patch.start()


if __name__ == "__main__":
    unittest.main()

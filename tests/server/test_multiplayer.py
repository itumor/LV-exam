"""T-064 — Multiplayer roleplay tests.

Covers the surface added by ``server_app.services.multiplayer``:

1. **Scenario catalogue**
   * Five expected scenarios (cafe, airport, shop, doctor, neighbor)
     exist on disk and each has at least two roles.
2. **Matchmaking queue**
   * The first caller is queued; the second caller is matched to a
     room with the first as partner. Both seats see the same room_id
     and distinct role assignments.
3. **Room state + broadcast**
   * A ``send_message`` from seat A is delivered to seat B's event
     queue and ignored by an unrelated third learner (multi-user
     isolation).
4. **Disconnect cleanup**
   * ``leave_room`` closes the room and broadcasts a ``peer_left``
     event to the partner. A subsequent ``send_message`` raises
     ``InvalidRequest`` (room closed).
5. **Audio resolution (T-018 + T-046)**
   * ``send_message`` with an ``audio_url`` calls the injected
     ``transcribe_fn`` and the relayed event carries both the
     transcript text and the original ``audio_url``.
6. **Schema validation**
   * ``parse_queue_request`` / ``parse_say_request`` reject empty or
     malformed payloads with :class:`InvalidRequest`.
"""

from __future__ import annotations

import json
import os
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server  # noqa: F401  — ensures package import side-effects run
from server_app.services import multiplayer as mp


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "content" / "multiplayer_scenarios"
EXPECTED = {"cafe", "airport", "shop", "doctor", "neighbor"}


# ---------------------------------------------------------------------------
# 1. Scenario catalogue
# ---------------------------------------------------------------------------


class ScenarioCatalogueTests(unittest.TestCase):
    def test_five_scenarios_on_disk(self) -> None:
        self.assertTrue(SCENARIO_DIR.is_dir(), f"missing dir: {SCENARIO_DIR}")
        files = {p.stem for p in SCENARIO_DIR.glob("*.json")}
        self.assertEqual(files, EXPECTED)

    def test_list_scenarios_summary_shape(self) -> None:
        summaries = mp.list_scenarios(SCENARIO_DIR)
        ids = {s["id"] for s in summaries}
        self.assertEqual(ids, EXPECTED)
        for s in summaries:
            self.assertGreaterEqual(s["role_count"], 2)
            self.assertEqual(s["language_level"], "A2")
            self.assertTrue(s["title"])

    def test_each_scenario_has_two_roles(self) -> None:
        for scenario_id in EXPECTED:
            data = mp.load_scenario(scenario_id, root=SCENARIO_DIR)
            roles = data.get("roles") or []
            self.assertGreaterEqual(
                len(roles), 2, f"{scenario_id}: needs >=2 roles for multiplayer"
            )
            for role in roles[:2]:
                self.assertTrue(role.get("name"))
                self.assertTrue(role.get("objective"))

    def test_load_scenario_rejects_traversal_ids(self) -> None:
        for bad_id in ("../etc/passwd", "..", "cafe/extra", "a$b"):
            with self.assertRaises(mp.ScenarioNotFound):
                mp.load_scenario(bad_id, root=SCENARIO_DIR)

    def test_load_scenario_unknown(self) -> None:
        with self.assertRaises(mp.ScenarioNotFound):
            mp.load_scenario("does-not-exist", root=SCENARIO_DIR)


# ---------------------------------------------------------------------------
# 2. Matchmaking queue
# ---------------------------------------------------------------------------


class _MultiplayerTestBase(unittest.TestCase):
    """Provide an isolated registry for each test."""

    def setUp(self) -> None:
        mp.reset_registry_for_tests()

    def tearDown(self) -> None:
        mp.reset_registry_for_tests()


class MatchmakingQueueTests(_MultiplayerTestBase):
    def test_first_caller_is_queued_second_is_matched(self) -> None:
        # Alice queues — nobody else is waiting, so she gets ``queued``.
        first = mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "cafe"},
        )
        self.assertEqual(first["status"], "queued")
        self.assertEqual(first["scenario_id"], "cafe")
        self.assertEqual(first["position"], 1)

        # Bob queues for the same scenario — should be matched immediately.
        second = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "cafe"},
        )
        self.assertEqual(second["status"], "matched")
        room = second["room"]
        self.assertIn("room_id", room)
        self.assertEqual(room["scenario_id"], "cafe")
        seats = {p["account_id"] for p in room["participants"]}
        self.assertEqual(seats, {"acct_alice", "acct_bob"})
        # Distinct role assignments.
        roles = {p["role_id"] for p in room["participants"]}
        self.assertEqual(len(roles), 2)

    def test_invalid_scenario_id_rejected(self) -> None:
        with self.assertRaises(mp.ScenarioNotFound):
            mp.enqueue(
                account_id="acct_x",
                display_name="X",
                raw_body={"scenario_id": "no-such-scenario"},
            )

    def test_missing_scenario_id_raises_invalid_request(self) -> None:
        with self.assertRaises(mp.InvalidRequest):
            mp.enqueue(
                account_id="acct_x",
                display_name="X",
                raw_body={},  # missing scenario_id
            )

    def test_repeated_queue_call_returns_existing_room(self) -> None:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "shop"},
        )
        matched = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "shop"},
        )
        room_id = matched["room"]["room_id"]
        # Alice now polls again — she should be told she's already matched.
        again = mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "shop"},
        )
        self.assertEqual(again["status"], "matched")
        self.assertTrue(again.get("reused"))
        self.assertEqual(again["room"]["room_id"], room_id)


# ---------------------------------------------------------------------------
# 3. Room state + broadcast (multi-user isolation)
# ---------------------------------------------------------------------------


class RoomStateBroadcastTests(_MultiplayerTestBase):
    def _pair(self, scenario_id: str = "cafe") -> str:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": scenario_id},
        )
        result = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": scenario_id},
        )
        return result["room"]["room_id"]

    def test_message_relays_to_partner(self) -> None:
        room_id = self._pair()
        # Both seats attach SSE event queues.
        registry = mp.get_registry()
        _, q_alice = registry.attach_stream(room_id, account_id="acct_alice")
        _, q_bob = registry.attach_stream(room_id, account_id="acct_bob")

        # Drain the join broadcasts that attach_stream emits to the partner.
        _drain(q_alice)
        _drain(q_bob)

        # Alice says something.
        event = mp.send_message(
            room_id=room_id,
            account_id="acct_alice",
            raw_body={"text": "Sveiks Bob!"},
        )
        self.assertEqual(event["event"], "message")
        self.assertEqual(event["account_id"], "acct_alice")
        self.assertEqual(event["text"], "Sveiks Bob!")

        # Bob receives it via his SSE queue.
        delivered = q_bob.get(timeout=1.0)
        self.assertEqual(delivered["event"], "message")
        self.assertEqual(delivered["text"], "Sveiks Bob!")
        # Alice also receives the echo so her transcript stays in
        # sync after a reconnect (the in-memory ring buffer is the
        # source of truth for replay).
        alice_events = _drain(q_alice)
        alice_msgs = [e for e in alice_events if e.get("event") == "message"]
        self.assertEqual(len(alice_msgs), 1)
        self.assertEqual(alice_msgs[0]["text"], "Sveiks Bob!")

    def test_third_user_cannot_read_or_write_room(self) -> None:
        room_id = self._pair()
        registry = mp.get_registry()
        with self.assertRaises(mp.NotParticipant):
            registry.get_room(room_id, account_id="acct_carol")
        with self.assertRaises(mp.NotParticipant):
            mp.send_message(
                room_id=room_id,
                account_id="acct_carol",
                raw_body={"text": "intruder"},
            )

    def test_history_replays_on_attach(self) -> None:
        room_id = self._pair()
        # Alice connects, posts, then Bob connects — Bob should see the
        # earlier message in his replay.
        registry = mp.get_registry()
        _, q_alice = registry.attach_stream(room_id, account_id="acct_alice")
        _drain(q_alice)
        mp.send_message(
            room_id=room_id,
            account_id="acct_alice",
            raw_body={"text": "Labdien!"},
        )
        _drain(q_alice)
        _, q_bob = registry.attach_stream(room_id, account_id="acct_bob")
        replayed = _drain(q_bob)
        texts = [ev.get("text") for ev in replayed if ev.get("event") == "message"]
        self.assertIn("Labdien!", texts)

    def test_send_message_empty_payload_rejected(self) -> None:
        room_id = self._pair()
        with self.assertRaises(mp.InvalidRequest):
            mp.send_message(
                room_id=room_id,
                account_id="acct_alice",
                raw_body={"text": "   "},  # whitespace only
            )

    def test_send_message_message_too_long(self) -> None:
        room_id = self._pair()
        with self.assertRaises(mp.InvalidRequest):
            mp.send_message(
                room_id=room_id,
                account_id="acct_alice",
                raw_body={"text": "x" * (mp.MAX_MESSAGE_CHARS + 50)},
            )


# ---------------------------------------------------------------------------
# 4. Disconnect cleanup
# ---------------------------------------------------------------------------


class DisconnectCleanupTests(_MultiplayerTestBase):
    def test_leave_room_broadcasts_peer_left_and_closes(self) -> None:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "neighbor"},
        )
        matched = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "neighbor"},
        )
        room_id = matched["room"]["room_id"]

        registry = mp.get_registry()
        _, q_alice = registry.attach_stream(room_id, account_id="acct_alice")
        _, q_bob = registry.attach_stream(room_id, account_id="acct_bob")
        _drain(q_alice)
        _drain(q_bob)

        # Alice explicitly leaves.
        mp.leave_room(room_id=room_id, account_id="acct_alice")

        # Bob should receive a peer_left event with reason explicit_leave.
        events_bob = _drain(q_bob)
        peer_left = [e for e in events_bob if e.get("event") == "peer_left"]
        self.assertTrue(peer_left, f"expected peer_left, got {events_bob}")
        self.assertEqual(peer_left[0]["account_id"], "acct_alice")
        self.assertEqual(peer_left[0]["reason"], "explicit_leave")

        # The room is closed; further sends fail.
        with self.assertRaises(mp.InvalidRequest):
            mp.send_message(
                room_id=room_id,
                account_id="acct_bob",
                raw_body={"text": "anyone there?"},
            )

    def test_detach_stream_broadcasts_peer_left(self) -> None:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "doctor"},
        )
        matched = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "doctor"},
        )
        room_id = matched["room"]["room_id"]

        registry = mp.get_registry()
        _, q_alice = registry.attach_stream(room_id, account_id="acct_alice")
        _, q_bob = registry.attach_stream(room_id, account_id="acct_bob")
        _drain(q_alice)
        _drain(q_bob)

        # Simulate Alice's HTTP connection dropping.
        registry.detach_stream(room_id, account_id="acct_alice")

        events_bob = _drain(q_bob)
        peer_left = [e for e in events_bob if e.get("event") == "peer_left"]
        self.assertTrue(peer_left)
        self.assertEqual(peer_left[0]["account_id"], "acct_alice")

    def test_stream_generator_emits_hello_and_message_then_closes(self) -> None:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "airport"},
        )
        matched = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "airport"},
        )
        room_id = matched["room"]["room_id"]

        # Pre-publish a message before Bob attaches — must be in history.
        registry = mp.get_registry()
        _, q_alice = registry.attach_stream(room_id, account_id="acct_alice")
        _drain(q_alice)
        mp.send_message(
            room_id=room_id,
            account_id="acct_alice",
            raw_body={"text": "Esmu lidostā."},
        )

        # Bob streams. ``stop_after_events`` keeps the test fast.
        chunks: list[str] = []
        for chunk in mp.stream_room(
            room_id,
            account_id="acct_bob",
            stop_after_events=5,
            heartbeat_interval=0.05,
        ):
            chunks.append(chunk)
            if len(chunks) > 6:
                break
        # The first chunk is the synthetic ``hello`` event.
        self.assertIn("event: hello", chunks[0])
        # Some later chunk carries the relayed message text.
        text_blob = "".join(chunks)
        self.assertIn("Esmu lidostā.", text_blob)
        # SSE framing is correct.
        for chunk in chunks:
            self.assertTrue(
                chunk.startswith("event:") or chunk.startswith(": ping"),
                f"unexpected chunk shape: {chunk!r}",
            )
            self.assertTrue(chunk.endswith("\n\n"))


# ---------------------------------------------------------------------------
# 5. Audio resolution (T-018 + T-046)
# ---------------------------------------------------------------------------


class AudioResolutionTests(_MultiplayerTestBase):
    def test_audio_url_is_transcribed_and_relayed(self) -> None:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "shop"},
        )
        matched = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "shop"},
        )
        room_id = matched["room"]["room_id"]

        class FakeUploadStore:
            def load(self, *, attempt_id, task_id, user_id):
                # Return tiny payload + mime — content doesn't matter
                # because ``fake_transcribe`` ignores it.
                return "audio/webm", b"\x00\x01\x02"

        captured = {}

        def fake_transcribe(audio_bytes, *, audio_mime, **_kwargs):
            captured["bytes"] = audio_bytes
            captured["mime"] = audio_mime
            return {"transcript": "Cik tas maksā?"}

        event = mp.send_message(
            room_id=room_id,
            account_id="acct_alice",
            raw_body={
                "audio_url": "/api/uploads/speaking/att123/task1",
            },
            upload_store=FakeUploadStore(),
            transcribe_fn=fake_transcribe,
        )
        self.assertEqual(event["event"], "message")
        # Transcript was relayed as text.
        self.assertIn("Cik tas maksā?", event["text"])
        # Original audio_url is forwarded so the partner can listen.
        self.assertEqual(event["audio_url"], "/api/uploads/speaking/att123/task1")
        # The transcribe function was actually called.
        self.assertEqual(captured["mime"], "audio/webm")

    def test_audio_url_with_text_concatenates(self) -> None:
        mp.enqueue(
            account_id="acct_alice",
            display_name="Alice",
            raw_body={"scenario_id": "shop"},
        )
        matched = mp.enqueue(
            account_id="acct_bob",
            display_name="Bob",
            raw_body={"scenario_id": "shop"},
        )
        room_id = matched["room"]["room_id"]

        class FakeUploadStore:
            def load(self, *, attempt_id, task_id, user_id):
                return "audio/webm", b"\x00"

        def fake_transcribe(_b, *, audio_mime, **_kwargs):
            return {"transcript": "Paldies"}

        event = mp.send_message(
            room_id=room_id,
            account_id="acct_alice",
            raw_body={
                "text": "Labdien!",
                "audio_url": "/api/uploads/speaking/att123/task1",
            },
            upload_store=FakeUploadStore(),
            transcribe_fn=fake_transcribe,
        )
        self.assertIn("Labdien!", event["text"])
        self.assertIn("Paldies", event["text"])


# ---------------------------------------------------------------------------
# 6. Schema validation
# ---------------------------------------------------------------------------


class SchemaValidationTests(unittest.TestCase):
    def test_queue_request_rejects_empty_scenario_id(self) -> None:
        with self.assertRaises(mp.InvalidRequest):
            mp.parse_queue_request({"scenario_id": ""})

    def test_queue_request_rejects_bad_chars(self) -> None:
        with self.assertRaises(mp.InvalidRequest):
            mp.parse_queue_request({"scenario_id": "../etc"})

    def test_queue_request_accepts_known_scenario(self) -> None:
        out = mp.parse_queue_request({"scenario_id": "cafe", "display_name": "Z"})
        self.assertEqual(out.scenario_id, "cafe")
        self.assertEqual(out.display_name, "Z")

    def test_say_request_accepts_text_only(self) -> None:
        out = mp.parse_say_request({"text": "Labdien!"})
        self.assertEqual(out.text, "Labdien!")
        self.assertIsNone(out.audio_url)

    def test_say_request_accepts_audio_only(self) -> None:
        out = mp.parse_say_request(
            {"audio_url": "/api/uploads/speaking/x/y"},
        )
        self.assertEqual(out.audio_url, "/api/uploads/speaking/x/y")


# ---------------------------------------------------------------------------
# 7. Scenario root override (env var honour)
# ---------------------------------------------------------------------------


class ScenarioRootEnvOverrideTests(unittest.TestCase):
    def test_lvcodex_multiplayer_root_env_var_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "custom.json").write_text(
                json.dumps(
                    {
                        "id": "custom",
                        "title": "Custom",
                        "summary": "Test scenario",
                        "roles": [
                            {"id": "a", "name": "A", "label": "A", "objective": "x"},
                            {"id": "b", "name": "B", "label": "B", "objective": "y"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"LVCODEX_MULTIPLAYER_ROOT": str(tmp_path)},
                clear=False,
            ):
                summaries = mp.list_scenarios()
                ids = {s["id"] for s in summaries}
                self.assertIn("custom", ids)
                # Original cafe scenario is *not* visible while the env
                # override is active.
                self.assertNotIn("cafe", ids)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drain(q: "queue.Queue") -> list[dict]:
    """Pull all currently-queued events without blocking."""

    out: list[dict] = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

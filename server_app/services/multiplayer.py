"""Multiplayer roleplay service (T-064).

Two-user real-time roleplay built on top of the T-045 NPC content layer
and the T-046 voice scoring + T-018 speaking-upload pipeline. The
feature lets two signed-in learners pair up via a matchmaking queue,
land in a shared **room** for a curated scenario (cafe, airport, shop,
doctor, neighbour), and exchange short Latvian messages — either typed
or spoken (transcribed via T-046 STT from a T-018 upload).

Why in-process state?
---------------------
The lvcodex server is a single :class:`http.server.ThreadingHTTPServer`
process today (T-020 modularisation explicitly left this stable). For
the v1 of multiplayer we therefore keep the queue and room state in a
thread-safe in-memory registry. When/if we move to a multi-region
ASGI deployment (T-028 chore tracks the migration plan), the registry
contract here is small enough — :class:`MultiplayerRegistry` — that it
can be swapped for a Redis-backed implementation without touching the
route layer.

Server-Sent Events relay
------------------------
The room exposes a :func:`stream_room` generator that yields
text/event-stream messages whenever a participant says something, joins,
leaves, or the scenario ends. The route handler in
:mod:`server_app.routes.multiplayer` walks the generator under a long-
poll-style ``while True`` loop and writes each chunk to ``handler.wfile``
with the standard ``data: ...\\n\\n`` framing. The transport is
deliberately one-shot per HTTP connection — when the connection drops
(client navigates away, network glitch), the registry's *disconnect
cleanup* logic removes the participant and broadcasts a ``peer_left``
event to the partner.

Audio integration (T-018 + T-046)
---------------------------------
A learner can post a message with ``audio_url`` set to a path returned
by the speaking-upload route. The service then calls
:func:`server_app.services.voice.transcribe_audio` (the same STT shim
used by ``POST /api/voice/score``) to extract the spoken text. The
transcript becomes the message body that is relayed over SSE, while
``audio_url`` itself is also forwarded so the receiver's client can
play the original audio for listening practice. This keeps the
multiplayer dialog accessible to both typing and speaking learners
without inventing a parallel audio pipeline.

Public surface
--------------

* :func:`list_scenarios` — return scenario summaries for the UI.
* :func:`load_scenario` — read one scenario JSON file (traversal-safe).
* :class:`MultiplayerRegistry` — queue + room registry, thread-safe.
* :func:`enqueue` — public helper: place a participant in the matchmaker.
* :func:`send_message` — publish a turn from a participant.
* :func:`stream_room` — SSE generator for a given participant.
* :func:`leave_room` — explicit disconnect (also triggered by stream end).

Multi-user isolation
--------------------
A participant can only ever see events for a room they joined as one of
the two seats. The registry verifies the ``account_id`` on every read /
write and rejects a third caller with a 403-mapped exception. This
matches the T-045 NPC isolation contract.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

logger = logging.getLogger("lvcodex.multiplayer")


# ---------------------------------------------------------------------------
# Constants + paths
# ---------------------------------------------------------------------------


ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SCENARIO_ROOT = ROOT / "content" / "multiplayer_scenarios"

# Hard caps so a runaway client cannot blow the in-memory registry.
MAX_MESSAGE_CHARS = 800
MAX_HISTORY_PER_ROOM = 200
MAX_QUEUE_DEPTH = 200
MAX_ROOMS = 500
ROOM_IDLE_TIMEOUT_SECONDS = 60 * 30  # 30 min — room is reaped after this idle
SSE_HEARTBEAT_INTERVAL_SECONDS = 15
SSE_QUEUE_MAX_BUFFER = 64

EXPECTED_SCENARIOS = {"cafe", "airport", "shop", "doctor", "neighbor"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MultiplayerError(Exception):
    """Base error for the multiplayer surface."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ScenarioNotFound(MultiplayerError):
    status_code = 404


class RoomNotFound(MultiplayerError):
    status_code = 404


class InvalidRequest(MultiplayerError):
    status_code = 400


class NotParticipant(MultiplayerError):
    """The caller is not one of the two seats in this room."""

    status_code = 403


class RoomFull(MultiplayerError):
    """A third learner tried to join an already-paired room."""

    status_code = 409


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class QueueRequest(BaseModel):
    """Inbound body for ``POST /api/multiplayer/queue``."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    scenario_id: str = Field(..., min_length=1, max_length=32)
    display_name: Optional[str] = Field(default=None, max_length=64)

    @field_validator("scenario_id")
    @classmethod
    def _normalize_scenario_id(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned or not all(ch.isalnum() or ch in "-_" for ch in cleaned):
            raise ValueError("scenario_id must be alphanumeric / dash / underscore.")
        return cleaned


class SayRequest(BaseModel):
    """Inbound body for ``POST /api/multiplayer/room/<id>/say``.

    Either ``text`` or ``audio_url`` must be supplied. When ``audio_url`` is
    set the server resolves the upload (T-018) and transcribes it via the
    T-046 STT shim; the resulting transcript becomes ``text`` for the SSE
    relay. The original ``audio_url`` is forwarded so the partner can
    listen to the original audio.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: Optional[str] = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    audio_url: Optional[str] = Field(default=None, max_length=512)


# ---------------------------------------------------------------------------
# Scenario loader
# ---------------------------------------------------------------------------


def scenario_root_dir() -> Path:
    """Resolve the directory containing scenario JSON files.

    Honours ``LVCODEX_MULTIPLAYER_ROOT`` for tests so a tempdir can swap
    the catalogue without touching the repo content.
    """

    override = os.getenv("LVCODEX_MULTIPLAYER_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return DEFAULT_SCENARIO_ROOT


def list_scenarios(root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Return scenario summaries (id, title, location, role_count)."""

    target = root or scenario_root_dir()
    summaries: list[dict[str, Any]] = []
    if not target.exists():
        return summaries
    for path in sorted(target.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logger.warning("multiplayer_scenario_unreadable path=%s error=%s", path, error)
            continue
        sid = (data.get("id") or path.stem).strip()
        if not sid:
            continue
        roles = data.get("roles") or []
        summaries.append(
            {
                "id": sid,
                "title": data.get("title", sid),
                "summary": data.get("summary", ""),
                "location": data.get("location", ""),
                "language_level": data.get("language_level", "A2"),
                "estimated_duration_minutes": data.get(
                    "estimated_duration_minutes", 0
                ),
                "role_count": len(roles),
                "roles": [
                    {
                        "id": role.get("id", ""),
                        "name": role.get("name", ""),
                        "label": role.get("label", ""),
                        "objective": role.get("objective", ""),
                    }
                    for role in roles
                ],
            }
        )
    return summaries


def load_scenario(scenario_id: str, *, root: Optional[Path] = None) -> dict[str, Any]:
    """Load and validate one scenario by id."""

    cleaned = (scenario_id or "").strip().lower()
    if not cleaned or not all(ch.isalnum() or ch in "-_" for ch in cleaned):
        raise ScenarioNotFound(f"Unknown scenario id: {scenario_id!r}")
    target_root = root or scenario_root_dir()
    path = target_root / f"{cleaned}.json"
    if not path.exists():
        raise ScenarioNotFound(f"Unknown scenario id: {cleaned!r}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ScenarioNotFound(f"Scenario unreadable: {cleaned!r}") from error
    if not isinstance(data, dict) or not data.get("title"):
        raise ScenarioNotFound(f"Scenario malformed: {cleaned!r}")
    roles = data.get("roles") or []
    if not isinstance(roles, list) or len(roles) < 2:
        raise ScenarioNotFound(
            f"Scenario {cleaned!r} must define at least 2 roles for multiplayer."
        )
    data.setdefault("id", cleaned)
    return data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# In-memory registry (queue + rooms)
# ---------------------------------------------------------------------------


@dataclass
class Participant:
    """A single participant seat inside a room."""

    account_id: str
    display_name: str
    role_id: str
    role_label: str
    joined_at: float = field(default_factory=time.time)
    # Per-participant SSE event queue. ``None`` means the participant has
    # no live stream attached yet (typical right after enqueue → join).
    event_queue: Optional["queue.Queue[dict[str, Any]]"] = None


@dataclass
class Room:
    """One paired roleplay session for two participants."""

    id: str
    scenario_id: str
    scenario_title: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    participants: dict[str, Participant] = field(default_factory=dict)
    # Ring-buffered history so a reconnecting client can replay the
    # current conversation in order.
    history: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=MAX_HISTORY_PER_ROOM)
    )
    closed: bool = False

    def to_state(self) -> dict[str, Any]:
        return {
            "room_id": self.id,
            "scenario_id": self.scenario_id,
            "scenario_title": self.scenario_title,
            "created_at": datetime.fromtimestamp(self.created_at, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "participants": [
                {
                    "account_id": p.account_id,
                    "display_name": p.display_name,
                    "role_id": p.role_id,
                    "role_label": p.role_label,
                    "connected": p.event_queue is not None,
                }
                for p in self.participants.values()
            ],
            "history_length": len(self.history),
            "closed": self.closed,
        }


class MultiplayerRegistry:
    """Thread-safe in-memory registry for the matchmaking queue + rooms.

    The registry is the single source of truth for live state. All public
    methods take the ``account_id`` of the caller so the SQL-style multi-
    user isolation contract holds in memory too: a learner cannot read or
    write any room they are not a participant of.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # scenario_id -> deque[QueueEntry]
        self._queues: dict[str, deque[dict[str, Any]]] = {}
        # room_id -> Room
        self._rooms: dict[str, Room] = {}
        # account_id -> room_id (one active room per account at a time)
        self._account_room: dict[str, str] = {}

    # ------------------------------------------------------------------ queue
    def enqueue(
        self,
        *,
        account_id: str,
        scenario_id: str,
        display_name: str,
    ) -> dict[str, Any]:
        """Add the caller to the matchmaking queue for ``scenario_id``.

        If another learner is already waiting, immediately pair them into
        a new room and return the room state. Otherwise return a queued
        marker with the queue position.
        """

        if not account_id:
            raise InvalidRequest("account_id is required to queue.")
        with self._lock:
            self._reap_idle_rooms_locked()
            if account_id in self._account_room:
                room = self._rooms.get(self._account_room[account_id])
                if room and not room.closed:
                    return {
                        "status": "matched",
                        "room": room.to_state(),
                        "reused": True,
                    }
                # Stale entry — clean up before re-queueing.
                self._account_room.pop(account_id, None)

            scenario = load_scenario(scenario_id)
            roles = scenario["roles"]
            q = self._queues.setdefault(scenario_id, deque())

            # If a partner is waiting we pop them and start a room.
            while q:
                partner = q.popleft()
                if partner["account_id"] == account_id:
                    # Same learner re-queued; skip.
                    continue
                if len(self._rooms) >= MAX_ROOMS:
                    raise InvalidRequest("Server at room capacity, try later.")
                room_id = _new_id("room")
                room = Room(
                    id=room_id,
                    scenario_id=scenario_id,
                    scenario_title=scenario.get("title", scenario_id),
                )
                role_a, role_b = roles[0], roles[1]
                room.participants[partner["account_id"]] = Participant(
                    account_id=partner["account_id"],
                    display_name=partner["display_name"],
                    role_id=role_a.get("id", "role_a"),
                    role_label=role_a.get("label", "Role A"),
                )
                room.participants[account_id] = Participant(
                    account_id=account_id,
                    display_name=display_name,
                    role_id=role_b.get("id", "role_b"),
                    role_label=role_b.get("label", "Role B"),
                )
                self._rooms[room_id] = room
                self._account_room[partner["account_id"]] = room_id
                self._account_room[account_id] = room_id
                self._record_event_locked(
                    room,
                    {
                        "event": "room_opened",
                        "room": room.to_state(),
                    },
                    broadcast=False,
                )
                logger.info(
                    "multiplayer_match scenario=%s room=%s a=%s b=%s",
                    scenario_id,
                    room_id,
                    partner["account_id"],
                    account_id,
                )
                return {
                    "status": "matched",
                    "room": room.to_state(),
                    "reused": False,
                }

            if len(q) >= MAX_QUEUE_DEPTH:
                raise InvalidRequest("Queue is full, try again shortly.")
            q.append(
                {
                    "account_id": account_id,
                    "display_name": display_name,
                    "queued_at": time.time(),
                }
            )
            position = len(q)
            return {
                "status": "queued",
                "scenario_id": scenario_id,
                "position": position,
            }

    def cancel_queue(self, *, account_id: str, scenario_id: str) -> bool:
        """Remove the caller from the queue. Returns True if found."""

        with self._lock:
            q = self._queues.get(scenario_id)
            if not q:
                return False
            for idx, entry in enumerate(list(q)):
                if entry["account_id"] == account_id:
                    del q[idx]
                    return True
            return False

    # ------------------------------------------------------------------ rooms
    def get_room(self, room_id: str, *, account_id: str) -> Room:
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                raise RoomNotFound(f"Unknown room: {room_id!r}")
            if account_id not in room.participants:
                # The caller is not one of the two seats — never leak
                # state to a third party.
                raise NotParticipant("You are not a participant in this room.")
            return room

    def attach_stream(
        self, room_id: str, *, account_id: str
    ) -> tuple[Room, "queue.Queue[dict[str, Any]]"]:
        """Attach an event queue to the participant's seat.

        Replaces any previously-attached queue (e.g. a stale connection)
        so reconnect is supported. Returns the (room, queue) tuple. The
        caller MUST drain the queue and call :meth:`detach_stream` when
        done so the registry can broadcast a ``peer_left`` event.
        """

        with self._lock:
            room = self.get_room(room_id, account_id=account_id)
            participant = room.participants[account_id]
            new_queue: "queue.Queue[dict[str, Any]]" = queue.Queue(
                maxsize=SSE_QUEUE_MAX_BUFFER
            )
            participant.event_queue = new_queue
            # Replay the history so the new connection lands with full context.
            for event in list(room.history):
                try:
                    new_queue.put_nowait(event)
                except queue.Full:
                    break
            # Notify the other seat that this participant just connected.
            self._broadcast_locked(
                room,
                {
                    "event": "peer_joined",
                    "ts": _now_iso(),
                    "account_id": account_id,
                    "display_name": participant.display_name,
                    "role_id": participant.role_id,
                },
                exclude={account_id},
            )
            return room, new_queue

    def detach_stream(self, room_id: str, *, account_id: str) -> None:
        """Detach the participant's SSE queue. Broadcasts ``peer_left``."""

        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return
            participant = room.participants.get(account_id)
            if participant is None:
                return
            participant.event_queue = None
            self._broadcast_locked(
                room,
                {
                    "event": "peer_left",
                    "ts": _now_iso(),
                    "account_id": account_id,
                    "display_name": participant.display_name,
                },
                exclude={account_id},
            )
            # If both seats are disconnected we close the room so a fresh
            # match starts cleanly. The room is still reachable via state
            # endpoints for a short grace window (idle-reap).
            if all(p.event_queue is None for p in room.participants.values()):
                room.closed = True
                room.updated_at = time.time()

    def leave_room(self, room_id: str, *, account_id: str) -> None:
        """Explicit leave — removes the seat and closes the room."""

        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return
            if account_id not in room.participants:
                raise NotParticipant("You are not a participant in this room.")
            participant = room.participants[account_id]
            participant.event_queue = None
            self._broadcast_locked(
                room,
                {
                    "event": "peer_left",
                    "ts": _now_iso(),
                    "account_id": account_id,
                    "display_name": participant.display_name,
                    "reason": "explicit_leave",
                },
                exclude={account_id},
            )
            room.closed = True
            room.updated_at = time.time()
            self._account_room.pop(account_id, None)

    def send_message(
        self,
        room_id: str,
        *,
        account_id: str,
        text: Optional[str],
        audio_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Publish a message from the caller to both participants."""

        cleaned_text = (text or "").strip()
        cleaned_audio = (audio_url or "").strip() or None
        if not cleaned_text and not cleaned_audio:
            raise InvalidRequest("Either 'text' or 'audio_url' must be provided.")
        if cleaned_text and len(cleaned_text) > MAX_MESSAGE_CHARS:
            raise InvalidRequest(
                f"Message text exceeds {MAX_MESSAGE_CHARS} characters."
            )
        with self._lock:
            room = self.get_room(room_id, account_id=account_id)
            if room.closed:
                raise InvalidRequest("Room is closed.")
            participant = room.participants[account_id]
            event = {
                "event": "message",
                "ts": _now_iso(),
                "room_id": room.id,
                "account_id": account_id,
                "display_name": participant.display_name,
                "role_id": participant.role_id,
                "text": cleaned_text,
                "audio_url": cleaned_audio,
            }
            self._record_event_locked(room, event, broadcast=True)
            room.updated_at = time.time()
            return event

    # ------------------------------------------------------------------ internals
    def _record_event_locked(
        self, room: Room, event: dict[str, Any], *, broadcast: bool
    ) -> None:
        room.history.append(event)
        if broadcast:
            self._broadcast_locked(room, event, exclude=None)

    def _broadcast_locked(
        self,
        room: Room,
        event: dict[str, Any],
        *,
        exclude: Optional[set[str]],
    ) -> None:
        skip = exclude or set()
        for participant in room.participants.values():
            if participant.account_id in skip:
                continue
            if participant.event_queue is None:
                continue
            try:
                participant.event_queue.put_nowait(event)
            except queue.Full:
                # Slow consumer — drop the oldest queued event to make room.
                try:
                    participant.event_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    participant.event_queue.put_nowait(event)
                except queue.Full:
                    logger.warning(
                        "multiplayer_event_drop room=%s account=%s",
                        room.id,
                        participant.account_id,
                    )

    def _reap_idle_rooms_locked(self) -> None:
        """Drop rooms that have been closed and idle past the timeout."""

        cutoff = time.time() - ROOM_IDLE_TIMEOUT_SECONDS
        stale: list[str] = []
        for room_id, room in self._rooms.items():
            if room.closed and room.updated_at < cutoff:
                stale.append(room_id)
        for room_id in stale:
            room = self._rooms.pop(room_id)
            for participant in room.participants.values():
                if self._account_room.get(participant.account_id) == room_id:
                    self._account_room.pop(participant.account_id, None)

    # ------------------------------------------------------------------ debug / test
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "rooms": {
                    rid: room.to_state() for rid, room in self._rooms.items()
                },
                "queues": {
                    sid: [entry["account_id"] for entry in q]
                    for sid, q in self._queues.items()
                },
                "account_room": dict(self._account_room),
            }

    def reset(self) -> None:
        """Test hook — wipe all state."""

        with self._lock:
            self._queues.clear()
            self._rooms.clear()
            self._account_room.clear()


_REGISTRY = MultiplayerRegistry()


def get_registry() -> MultiplayerRegistry:
    """Return the process-wide registry singleton."""

    return _REGISTRY


def reset_registry_for_tests() -> None:
    """Wipe the registry — only used by tests."""

    _REGISTRY.reset()


# ---------------------------------------------------------------------------
# Audio resolution (T-018 + T-046)
# ---------------------------------------------------------------------------


def resolve_audio_to_text(
    audio_url: str,
    *,
    account_id: str,
    upload_store: Any,
    transcribe_fn: Optional[Callable[..., Any]] = None,
) -> str:
    """Resolve a T-018 audio_url to a transcript via the T-046 STT shim.

    Imported lazily so the multiplayer service has no hard dependency on
    the voice module at import time (keeps the test suite startup quick
    and avoids circular imports during the hook chain).
    """

    from server_app.services.voice import load_audio_from_t018, transcribe_audio

    audio_bytes, mime = load_audio_from_t018(
        audio_url,
        upload_store=upload_store,
        user_id=account_id,
    )
    fn = transcribe_fn or transcribe_audio
    result = fn(audio_bytes, audio_mime=mime)
    # ``transcribe_audio`` returns a :class:`VoiceTranscription` with a
    # ``transcript`` field. Tests pass a plain dict / str — handle both.
    if isinstance(result, str):
        text = result
    elif isinstance(result, dict):
        text = result.get("transcript") or result.get("text") or ""
    else:
        text = (
            getattr(result, "transcript", None)
            or getattr(result, "text", None)
            or ""
        )
    return (text or "").strip()


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------


def stream_room(
    room_id: str,
    *,
    account_id: str,
    stop_after_events: Optional[int] = None,
    heartbeat_interval: float = SSE_HEARTBEAT_INTERVAL_SECONDS,
) -> Iterator[str]:
    """Yield SSE chunks for the caller until the room closes or detaches.

    Each yielded item is a complete SSE frame (``data: {...}\\n\\n``) or a
    heartbeat comment (``: ping\\n\\n``). The caller (route layer) writes
    each chunk to ``handler.wfile`` and flushes immediately.

    ``stop_after_events`` is a test hook so unit tests can drain a fixed
    number of frames instead of looping forever.
    """

    registry = get_registry()
    room, q = registry.attach_stream(room_id, account_id=account_id)

    # First frame: a synthetic ``hello`` event so the client can
    # confirm the connection and learn its seat role.
    me = room.participants[account_id]
    hello = {
        "event": "hello",
        "ts": _now_iso(),
        "room_id": room.id,
        "scenario_id": room.scenario_id,
        "you": {
            "account_id": me.account_id,
            "role_id": me.role_id,
            "role_label": me.role_label,
            "display_name": me.display_name,
        },
        "state": room.to_state(),
    }
    yield _format_sse(hello)

    events_yielded = 0
    try:
        while True:
            if stop_after_events is not None and events_yielded >= stop_after_events:
                return
            # Hard stop if the room was closed since the last frame.
            current = registry._rooms.get(room_id)  # noqa: SLF001 — internal probe
            if current is None or current.closed:
                yield _format_sse({"event": "room_closed", "ts": _now_iso()})
                return
            try:
                event = q.get(timeout=heartbeat_interval)
            except queue.Empty:
                # Keep-alive comment — proxies and browsers reset the
                # stream after ~30s of silence otherwise.
                yield ": ping\n\n"
                continue
            yield _format_sse(event)
            events_yielded += 1
    finally:
        # Detach so the partner is notified even if the generator was
        # closed early (client disconnect, BrokenPipeError, etc.).
        registry.detach_stream(room_id, account_id=account_id)


def _format_sse(event: dict[str, Any]) -> str:
    """Encode one SSE frame. Includes an explicit ``event:`` line for
    clients that bind to specific event names."""

    name = (event.get("event") or "message").strip() or "message"
    data = json.dumps(event, ensure_ascii=False)
    return f"event: {name}\ndata: {data}\n\n"


# ---------------------------------------------------------------------------
# Thin top-level helpers used by the route layer
# ---------------------------------------------------------------------------


def parse_queue_request(raw: Any) -> QueueRequest:
    try:
        return QueueRequest.model_validate(raw)
    except ValidationError as error:
        raise InvalidRequest(
            "Queue request payload failed schema validation: " + str(error.errors())
        ) from error


def parse_say_request(raw: Any) -> SayRequest:
    try:
        return SayRequest.model_validate(raw)
    except ValidationError as error:
        raise InvalidRequest(
            "Say request payload failed schema validation: " + str(error.errors())
        ) from error


def enqueue(
    *,
    account_id: str,
    display_name: str,
    raw_body: Any,
) -> dict[str, Any]:
    """Top-level helper for ``POST /api/multiplayer/queue``."""

    request = parse_queue_request(raw_body)
    name = (request.display_name or display_name or "Learner").strip() or "Learner"
    return get_registry().enqueue(
        account_id=account_id,
        scenario_id=request.scenario_id,
        display_name=name,
    )


def send_message(
    *,
    room_id: str,
    account_id: str,
    raw_body: Any,
    upload_store: Any = None,
    transcribe_fn: Optional[Callable[..., Any]] = None,
) -> dict[str, Any]:
    """Top-level helper for ``POST /api/multiplayer/room/<id>/say``."""

    request = parse_say_request(raw_body)
    text = (request.text or "").strip() or None
    audio_url = (request.audio_url or "").strip() or None
    if audio_url and upload_store is not None:
        try:
            transcript = resolve_audio_to_text(
                audio_url,
                account_id=account_id,
                upload_store=upload_store,
                transcribe_fn=transcribe_fn,
            )
        except FileNotFoundError as error:
            raise InvalidRequest(f"Audio upload not found: {error}") from error
        except PermissionError as error:
            raise InvalidRequest(f"Audio upload not accessible: {error}") from error
        if transcript:
            # Merge transcript into the relayed text so the partner sees
            # both: the transcript and the audio_url for playback.
            text = (text + "\n" if text else "") + transcript
    if not text and not audio_url:
        raise InvalidRequest("Empty message — either text or audio_url is required.")
    return get_registry().send_message(
        room_id,
        account_id=account_id,
        text=text,
        audio_url=audio_url,
    )


def leave_room(*, room_id: str, account_id: str) -> None:
    """Top-level helper for ``POST /api/multiplayer/room/<id>/leave``."""

    get_registry().leave_room(room_id, account_id=account_id)


__all__ = [
    "DEFAULT_SCENARIO_ROOT",
    "EXPECTED_SCENARIOS",
    "InvalidRequest",
    "MAX_MESSAGE_CHARS",
    "MultiplayerError",
    "MultiplayerRegistry",
    "NotParticipant",
    "Participant",
    "QueueRequest",
    "Room",
    "RoomFull",
    "RoomNotFound",
    "SayRequest",
    "ScenarioNotFound",
    "enqueue",
    "get_registry",
    "leave_room",
    "list_scenarios",
    "load_scenario",
    "parse_queue_request",
    "parse_say_request",
    "reset_registry_for_tests",
    "resolve_audio_to_text",
    "scenario_root_dir",
    "send_message",
    "stream_room",
]

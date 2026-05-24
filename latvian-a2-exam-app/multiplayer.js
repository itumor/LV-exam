/*
 * T-064 — Multiplayer roleplay UI.
 *
 * Vanilla JS, no framework. Talks to the five endpoints shipped by
 * ``server_app/routes/multiplayer.py``:
 *
 *   GET  /api/multiplayer/scenarios
 *   POST /api/multiplayer/queue          {scenario_id}
 *   GET  /api/multiplayer/room/<id>/stream   (Server-Sent Events)
 *   POST /api/multiplayer/room/<id>/say  {text}
 *   POST /api/multiplayer/room/<id>/leave
 *
 * Flow:
 *   1. Fetch scenarios on load, render selector cards.
 *   2. User clicks "Find a partner" — we POST to /queue.
 *      • If the response is "matched" we open the SSE stream immediately.
 *      • If "queued" we poll the same endpoint every 3 s until matched.
 *   3. Once paired, the SSE stream pushes messages, join/leave, room_closed.
 *   4. The user types in the input box — POST /say relays to the partner.
 *
 * Multi-state UX: empty / loading / queued / paired / error / closed.
 *
 * Defensive: every DOM write uses textContent (no innerHTML) so untrusted
 * peer text cannot inject markup. The audio_url is sanity-checked to start
 * with ``/api/uploads/`` before being attached to an ``<audio>`` element.
 */

(function () {
  "use strict";

  var state = {
    scenarios: [],
    activeScenarioId: null,
    queuePollTimer: null,
    eventSource: null,
    roomId: null,
    selfAccountId: null,
    inflight: false,
  };

  var elements = {
    scenarios: document.getElementById("mp-scenarios"),
    scenariosEmpty: document.getElementById("mp-scenarios-empty"),
    find: document.getElementById("mp-find"),
    leave: document.getElementById("mp-leave"),
    status: document.getElementById("mp-status"),
    error: document.getElementById("mp-error"),
    history: document.getElementById("mp-history"),
    historyEmpty: document.getElementById("mp-history-empty"),
    form: document.getElementById("mp-form"),
    input: document.getElementById("mp-input"),
    send: document.getElementById("mp-send"),
  };

  function setError(msg) {
    if (!msg) {
      elements.error.hidden = true;
      elements.error.textContent = "";
      return;
    }
    elements.error.hidden = false;
    elements.error.textContent = msg;
  }

  function setStatus(text) {
    elements.status.textContent = text || "";
  }

  function clearChildren(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function renderScenarios() {
    clearChildren(elements.scenarios);
    if (!state.scenarios.length) {
      var empty = document.createElement("li");
      empty.className = "mp-status";
      empty.textContent = "No scenarios configured.";
      elements.scenarios.appendChild(empty);
      return;
    }
    state.scenarios.forEach(function (sc) {
      var li = document.createElement("li");
      li.className =
        "mp-scenario" +
        (state.activeScenarioId === sc.id ? " is-active" : "");
      li.setAttribute("role", "option");
      li.tabIndex = 0;
      li.dataset.scenarioId = sc.id;

      var t = document.createElement("div");
      t.className = "title";
      t.textContent = sc.title || sc.id;
      li.appendChild(t);

      var meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent =
        (sc.location || "") +
        (sc.estimated_duration_minutes
          ? " · ~" + sc.estimated_duration_minutes + " min"
          : "");
      li.appendChild(meta);

      var summary = document.createElement("div");
      summary.className = "meta";
      summary.textContent = sc.summary || "";
      li.appendChild(summary);

      li.addEventListener("click", function () { selectScenario(sc.id); });
      li.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectScenario(sc.id);
        }
      });
      elements.scenarios.appendChild(li);
    });
  }

  function selectScenario(id) {
    if (state.inflight || state.roomId) return;
    state.activeScenarioId = id;
    elements.find.disabled = false;
    setStatus("Selected: " + id + ". Click 'Find a partner' to queue.");
    renderScenarios();
  }

  async function loadScenarios() {
    try {
      var res = await fetch("/api/multiplayer/scenarios", {
        credentials: "same-origin",
      });
      if (res.status === 401) {
        elements.scenariosEmpty.textContent = "Please sign in to use multiplayer.";
        return;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      var payload = await res.json();
      state.scenarios = Array.isArray(payload.scenarios) ? payload.scenarios : [];
      renderScenarios();
    } catch (err) {
      elements.scenariosEmpty.textContent =
        "Could not load scenarios (" + (err.message || "unknown") + ").";
    }
  }

  async function postQueue() {
    var res = await fetch("/api/multiplayer/queue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ scenario_id: state.activeScenarioId }),
    });
    var body = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      var msg = (body && body.error && body.error.message) || ("HTTP " + res.status);
      throw new Error(msg);
    }
    return body;
  }

  async function findPartner() {
    if (!state.activeScenarioId) return;
    if (state.inflight) return;
    state.inflight = true;
    setError("");
    setStatus("Searching for a partner…");
    elements.find.disabled = true;
    try {
      var result = await postQueue();
      if (result.status === "matched" && result.room && result.room.room_id) {
        openRoom(result.room.room_id);
      } else if (result.status === "queued") {
        setStatus("Queued (position " + (result.position || 1) + "). Waiting…");
        state.queuePollTimer = window.setInterval(function () { pollQueue(); }, 3000);
      } else {
        setStatus("Unexpected matchmaker reply.");
      }
    } catch (err) {
      setError("Queue failed: " + (err.message || "unknown"));
    } finally {
      state.inflight = false;
      if (!state.roomId && !state.queuePollTimer) elements.find.disabled = false;
    }
  }

  async function pollQueue() {
    try {
      var result = await postQueue();
      if (result.status === "matched" && result.room && result.room.room_id) {
        window.clearInterval(state.queuePollTimer);
        state.queuePollTimer = null;
        openRoom(result.room.room_id);
      }
    } catch (err) {
      window.clearInterval(state.queuePollTimer);
      state.queuePollTimer = null;
      setError("Queue lost: " + (err.message || "unknown"));
      elements.find.disabled = false;
    }
  }

  function openRoom(roomId) {
    state.roomId = roomId;
    elements.leave.disabled = false;
    elements.find.disabled = true;
    elements.input.disabled = false;
    elements.send.disabled = false;
    elements.historyEmpty.hidden = true;
    setStatus("Paired! Room " + roomId + " — start chatting in Latvian.");
    // Native EventSource handles reconnection and chunk framing.
    var url = "/api/multiplayer/room/" + encodeURIComponent(roomId) + "/stream";
    var es = new EventSource(url, { withCredentials: true });
    state.eventSource = es;
    es.addEventListener("hello", function (e) { onEvent(e, "hello"); });
    es.addEventListener("message", function (e) { onEvent(e, "message"); });
    es.addEventListener("peer_joined", function (e) { onEvent(e, "peer_joined"); });
    es.addEventListener("peer_left", function (e) { onEvent(e, "peer_left"); });
    es.addEventListener("room_opened", function (e) { onEvent(e, "room_opened"); });
    es.addEventListener("room_closed", function (e) { onEvent(e, "room_closed"); });
    es.onerror = function () {
      setError("Stream interrupted. Reconnecting…");
    };
  }

  function onEvent(e, name) {
    var payload;
    try { payload = JSON.parse(e.data || "{}"); } catch (_) { return; }
    if (name === "hello") {
      state.selfAccountId = (payload.you && payload.you.account_id) || null;
      addSystemBubble(
        "You are " +
          ((payload.you && payload.you.role_label) || "a participant") +
          " in scenario '" +
          (payload.scenario_id || "?") +
          "'.",
      );
      return;
    }
    if (name === "message") {
      addMessageBubble(payload);
      return;
    }
    if (name === "peer_joined") {
      addSystemBubble(
        (payload.display_name || "Partner") + " joined the room.",
      );
      return;
    }
    if (name === "peer_left") {
      addSystemBubble(
        (payload.display_name || "Partner") +
          " left the room" +
          (payload.reason === "explicit_leave" ? " (left explicitly)." : "."),
      );
      return;
    }
    if (name === "room_closed") {
      addSystemBubble("Room closed.");
      closeRoom();
      return;
    }
  }

  function addSystemBubble(text) {
    var div = document.createElement("div");
    div.className = "mp-bubble system";
    div.textContent = text;
    elements.history.appendChild(div);
    elements.history.scrollTop = elements.history.scrollHeight;
  }

  function addMessageBubble(payload) {
    var div = document.createElement("div");
    var isMe =
      state.selfAccountId &&
      payload.account_id &&
      payload.account_id === state.selfAccountId;
    div.className = "mp-bubble " + (isMe ? "me" : "peer");

    var author = document.createElement("span");
    author.className = "author";
    author.textContent =
      (payload.display_name || (isMe ? "You" : "Partner")) +
      (payload.role_id ? " · " + payload.role_id : "");
    div.appendChild(author);

    if (payload.text) {
      var t = document.createElement("div");
      t.textContent = payload.text;
      div.appendChild(t);
    }
    if (
      payload.audio_url &&
      typeof payload.audio_url === "string" &&
      payload.audio_url.indexOf("/api/uploads/") === 0
    ) {
      var audio = document.createElement("audio");
      audio.controls = true;
      audio.src = payload.audio_url;
      audio.preload = "none";
      div.appendChild(audio);
    }
    elements.history.appendChild(div);
    elements.history.scrollTop = elements.history.scrollHeight;
  }

  async function sendMessage(text) {
    if (!state.roomId || !text.trim()) return;
    elements.send.disabled = true;
    try {
      var res = await fetch(
        "/api/multiplayer/room/" + encodeURIComponent(state.roomId) + "/say",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ text: text.trim() }),
        },
      );
      if (!res.ok) {
        var body = await res.json().catch(function () { return {}; });
        var msg = (body && body.error && body.error.message) || ("HTTP " + res.status);
        setError("Send failed: " + msg);
      } else {
        elements.input.value = "";
      }
    } catch (err) {
      setError("Network error: " + (err.message || "unknown"));
    } finally {
      elements.send.disabled = !state.roomId;
      elements.input.focus();
    }
  }

  async function leaveRoom() {
    if (!state.roomId) return;
    var roomId = state.roomId;
    elements.leave.disabled = true;
    try {
      await fetch(
        "/api/multiplayer/room/" + encodeURIComponent(roomId) + "/leave",
        { method: "POST", credentials: "same-origin" },
      );
    } catch (_err) {
      /* best-effort */
    }
    closeRoom();
  }

  function closeRoom() {
    if (state.eventSource) {
      state.eventSource.close();
      state.eventSource = null;
    }
    state.roomId = null;
    state.selfAccountId = null;
    elements.leave.disabled = true;
    elements.find.disabled = !state.activeScenarioId;
    elements.input.disabled = true;
    elements.send.disabled = true;
    setStatus("Room ended. Pick a scenario to start again.");
  }

  elements.find.addEventListener("click", findPartner);
  elements.leave.addEventListener("click", leaveRoom);
  elements.form.addEventListener("submit", function (e) {
    e.preventDefault();
    sendMessage(elements.input.value || "");
  });

  document.addEventListener("DOMContentLoaded", loadScenarios);
})();

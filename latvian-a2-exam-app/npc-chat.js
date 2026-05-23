/*
 * T-045 — AI NPC roleplay chat UI.
 *
 * Vanilla JS, no framework dependency. Talks to:
 *   GET  /api/npc                   — list of available NPCs.
 *   GET  /api/npc/<id>              — load one NPC profile (for the header).
 *   POST /api/npc/<id>/turn         — send a message, receive an NPC reply.
 *
 * The conversation_id is held in module-level state and re-sent on every
 * subsequent turn so the server-side persistence keeps the dialogue going
 * across a single session. All string interpolation into the DOM uses
 * ``textContent`` (no innerHTML) so user/server text cannot inject markup.
 *
 * Multi-state UX (per DoD #2): empty, loading, error, success.
 */

(function () {
  "use strict";

  const state = {
    npcs: [],
    activeNpc: null,
    conversationId: null,
    history: [],
    inflight: false,
  };

  const elements = {
    npcList: document.getElementById("npc-list"),
    npcEmpty: document.getElementById("npc-empty"),
    chatTitle: document.getElementById("chat-title"),
    chatMeta: document.getElementById("chat-meta"),
    chatHistory: document.getElementById("chat-history"),
    chatEmpty: document.getElementById("chat-empty"),
    chatError: document.getElementById("chat-error"),
    chatForm: document.getElementById("chat-form"),
    chatInput: document.getElementById("chat-input"),
    chatSend: document.getElementById("chat-send"),
    chatStatus: document.getElementById("chat-status"),
  };

  function setError(message) {
    if (!message) {
      elements.chatError.hidden = true;
      elements.chatError.textContent = "";
      return;
    }
    elements.chatError.hidden = false;
    elements.chatError.textContent = message;
  }

  function setStatus(text) {
    elements.chatStatus.textContent = text || "Quota: —";
  }

  function clearChildren(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function makeCard(npc) {
    const li = document.createElement("li");
    li.className =
      "npc-card" +
      (state.activeNpc && state.activeNpc.id === npc.id ? " is-active" : "");
    li.setAttribute("role", "option");
    li.setAttribute("tabindex", "0");
    li.setAttribute(
      "aria-selected",
      state.activeNpc && state.activeNpc.id === npc.id ? "true" : "false",
    );
    li.dataset.npcId = npc.id;

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = npc.name || npc.id;
    li.appendChild(name);

    const role = document.createElement("div");
    role.className = "role";
    role.textContent = npc.role || "";
    li.appendChild(role);

    const loc = document.createElement("div");
    loc.className = "location";
    loc.textContent = npc.location || "";
    li.appendChild(loc);

    li.addEventListener("click", function () {
      selectNpc(npc.id);
    });
    li.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectNpc(npc.id);
      }
    });
    return li;
  }

  function renderNpcList() {
    if (!state.npcs.length) {
      elements.npcEmpty.textContent =
        "No NPCs available yet. Make sure you are signed in.";
      return;
    }
    clearChildren(elements.npcList);
    state.npcs.forEach(function (npc) {
      elements.npcList.appendChild(makeCard(npc));
    });
  }

  function renderHistory() {
    clearChildren(elements.chatHistory);
    if (!state.history.length) {
      const empty = document.createElement("div");
      empty.className = "chat-empty";
      empty.textContent = state.activeNpc
        ? "Sasveicinies ar " +
          state.activeNpc.name +
          " — say hello to start the roleplay."
        : "Pick an NPC on the left to begin a roleplay in Latvian.";
      elements.chatHistory.appendChild(empty);
      return;
    }
    state.history.forEach(function (turn) {
      const bubble = document.createElement("div");
      bubble.className =
        "chat-message " + (turn.role === "user" ? "user" : "assistant");
      bubble.textContent = turn.content;
      elements.chatHistory.appendChild(bubble);
    });
    elements.chatHistory.scrollTop = elements.chatHistory.scrollHeight;
  }

  async function loadNpcs() {
    try {
      const response = await fetch("/api/npc", { credentials: "same-origin" });
      if (response.status === 401) {
        elements.npcEmpty.textContent = "Please sign in to use NPC roleplay.";
        return;
      }
      if (!response.ok) {
        throw new Error("HTTP " + response.status);
      }
      const payload = await response.json();
      state.npcs = Array.isArray(payload.npcs) ? payload.npcs : [];
      if (!state.npcs.length) {
        elements.npcEmpty.textContent = "No NPCs configured yet.";
        return;
      }
      renderNpcList();
    } catch (error) {
      console.error("npc_list_failed", error);
      elements.npcEmpty.textContent =
        "Could not load NPCs (" + (error.message || "unknown error") + ").";
    }
  }

  function selectNpc(npcId) {
    if (state.inflight) return;
    setError("");
    const npc = state.npcs.find(function (entry) {
      return entry.id === npcId;
    });
    if (!npc) return;
    state.activeNpc = npc;
    state.conversationId = null;
    state.history = [];
    elements.chatTitle.textContent = npc.name + " — " + (npc.role || "");
    elements.chatMeta.textContent = npc.location || "";
    elements.chatInput.disabled = false;
    elements.chatSend.disabled = false;
    elements.chatInput.placeholder =
      "Sasveicinies ar " + npc.name + "… (write in Latvian)";
    renderNpcList();
    renderHistory();
    elements.chatInput.focus();
  }

  async function sendTurn(message) {
    if (!state.activeNpc) return;
    if (state.inflight) return;
    state.inflight = true;
    elements.chatSend.disabled = true;
    elements.chatInput.disabled = true;
    setError("");
    // Optimistically render the user's turn so the UI feels responsive.
    state.history.push({ role: "user", content: message });
    renderHistory();
    try {
      const response = await fetch(
        "/api/npc/" + encodeURIComponent(state.activeNpc.id) + "/turn",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            message: message,
            conversation_id: state.conversationId || undefined,
          }),
        },
      );
      const payload = await response.json().catch(function () {
        return {};
      });
      if (!response.ok) {
        const code =
          (payload && (payload.code || payload.error)) ||
          "HTTP " + response.status;
        const detail =
          (payload && (payload.message || payload.error)) || "Request failed.";
        // Rewind the optimistic user turn so the chat history reflects reality.
        state.history.pop();
        renderHistory();
        setError(code + ": " + detail);
        return;
      }
      const reply = (payload && payload.reply) || "";
      const turnState = (payload && payload.state) || {};
      state.history.push({ role: "assistant", content: reply });
      state.conversationId = turnState.conversation_id || state.conversationId;
      if (turnState.quota_limit !== undefined) {
        setStatus(
          "Quota: " +
            (turnState.quota_used || 0) +
            "/" +
            turnState.quota_limit +
            (turnState.quota_resets_at
              ? " (resets " + turnState.quota_resets_at + ")"
              : ""),
        );
      }
      renderHistory();
    } catch (error) {
      state.history.pop();
      renderHistory();
      setError("Network error: " + (error.message || "unknown"));
    } finally {
      state.inflight = false;
      elements.chatSend.disabled = !state.activeNpc;
      elements.chatInput.disabled = !state.activeNpc;
      elements.chatInput.value = "";
      elements.chatInput.focus();
    }
  }

  elements.chatForm.addEventListener("submit", function (event) {
    event.preventDefault();
    const message = (elements.chatInput.value || "").trim();
    if (!message) return;
    sendTurn(message);
  });

  document.addEventListener("DOMContentLoaded", function () {
    loadNpcs();
  });
})();

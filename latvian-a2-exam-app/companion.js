/*
 * T-053 — AI tutor companion (persistent chat bubble).
 *
 * Self-contained vanilla-JS widget that mounts a floating chat button
 * (bottom-right of any host page) and an expanding panel that talks to:
 *
 *   GET  /api/companion/nudge   — daily, rules-based nudge.
 *   POST /api/companion/chat    — send a message, receive a tutor reply.
 *
 * Persistence lives on the server (the ``companion_memory`` table). The
 * widget keeps only ephemeral DOM state — when the panel is closed the
 * scrollback is forgotten, but the next time the learner opens it the
 * server has the running summary that drives the tutor's continuity.
 *
 * No build step, no framework, no innerHTML — every dynamic insertion
 * uses ``textContent`` so server/user text can never inject markup.
 *
 * Usage on any page: ``<script src="./companion.js" defer></script>``
 * The widget appends itself to ``document.body`` on DOMContentLoaded
 * (or immediately when the script is loaded after parsing).
 */

(function () {
  "use strict";

  if (window.__lvcodexCompanionInstalled) {
    // Defensive — including the script twice should be a no-op.
    return;
  }
  window.__lvcodexCompanionInstalled = true;

  var CHAT_ENDPOINT = "/api/companion/chat";
  var NUDGE_ENDPOINT = "/api/companion/nudge";
  var SESSION_ENDPOINT = "/api/session";
  var MAX_MESSAGE_LEN = 1000;

  var state = {
    open: false,
    inflight: false,
    history: [],
    nudge: null,
    authenticated: false,
    memorySummaryBytes: 0,
    memoryBudget: 2048,
    conversationCount: 0,
  };

  var elements = {};

  function injectStyles() {
    if (document.getElementById("lvcodex-companion-styles")) return;
    var style = document.createElement("style");
    style.id = "lvcodex-companion-styles";
    style.textContent = [
      ".lvcodex-companion-toggle {",
      "  position: fixed; bottom: 1.25rem; right: 1.25rem; z-index: 9990;",
      "  width: 56px; height: 56px; border-radius: 50%; border: 0;",
      "  background: #146b63; color: #fff; font-size: 1.5rem; cursor: pointer;",
      "  box-shadow: 0 6px 18px rgba(0,0,0,0.18);",
      "  display: flex; align-items: center; justify-content: center;",
      "}",
      ".lvcodex-companion-toggle:focus { outline: 3px solid #ffcd00; outline-offset: 2px; }",
      ".lvcodex-companion-toggle .badge {",
      "  position: absolute; top: -4px; right: -4px;",
      "  background: #d4351c; color: #fff;",
      "  font-size: 0.7rem; min-width: 18px; height: 18px;",
      "  border-radius: 9px; padding: 0 4px;",
      "  display: flex; align-items: center; justify-content: center;",
      "}",
      ".lvcodex-companion-panel {",
      "  position: fixed; bottom: 5.5rem; right: 1.25rem; z-index: 9991;",
      "  width: 360px; max-width: calc(100vw - 2.5rem);",
      "  height: 480px; max-height: calc(100vh - 7rem);",
      "  background: #fff; border-radius: 12px; overflow: hidden;",
      "  box-shadow: 0 10px 28px rgba(0,0,0,0.22);",
      "  display: flex; flex-direction: column;",
      "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;",
      "}",
      ".lvcodex-companion-panel[hidden] { display: none !important; }",
      ".lvcodex-companion-header {",
      "  background: #146b63; color: #fff; padding: 0.75rem 1rem;",
      "  display: flex; align-items: center; justify-content: space-between;",
      "}",
      ".lvcodex-companion-header h2 { margin: 0; font-size: 1rem; font-weight: 600; }",
      ".lvcodex-companion-header button {",
      "  background: transparent; border: 0; color: #fff; font-size: 1.4rem;",
      "  cursor: pointer; line-height: 1; padding: 0 0.25rem;",
      "}",
      ".lvcodex-companion-nudge {",
      "  background: #fff7d6; padding: 0.6rem 0.9rem;",
      "  border-bottom: 1px solid #f0e7b5; font-size: 0.85rem;",
      "  color: #4a3c00;",
      "}",
      ".lvcodex-companion-nudge.severity-warn { background: #fff1ef; color: #6b1a10; border-color: #f7c0b8; }",
      ".lvcodex-companion-nudge.severity-celebrate { background: #e6f6e8; color: #0f4a16; border-color: #b9e3bf; }",
      ".lvcodex-companion-nudge[hidden] { display: none !important; }",
      ".lvcodex-companion-nudge .en { display: block; font-size: 0.75rem; opacity: 0.75; margin-top: 0.15rem; }",
      ".lvcodex-companion-history {",
      "  flex: 1; padding: 0.75rem; background: #f6f8fa; overflow-y: auto;",
      "  display: flex; flex-direction: column; gap: 0.5rem;",
      "}",
      ".lvcodex-companion-history .empty {",
      "  text-align: center; color: #57606a; padding: 1.5rem 0.5rem;",
      "  font-size: 0.9rem;",
      "}",
      ".lvcodex-companion-msg {",
      "  max-width: 82%; padding: 0.5rem 0.75rem; border-radius: 12px;",
      "  font-size: 0.9rem; line-height: 1.35; white-space: pre-wrap;",
      "  word-wrap: break-word;",
      "}",
      ".lvcodex-companion-msg.user {",
      "  align-self: flex-end; background: #146b63; color: #fff;",
      "  border-bottom-right-radius: 3px;",
      "}",
      ".lvcodex-companion-msg.assistant {",
      "  align-self: flex-start; background: #fff; border: 1px solid #d0d7de;",
      "  border-bottom-left-radius: 3px;",
      "}",
      ".lvcodex-companion-form {",
      "  padding: 0.5rem 0.75rem; border-top: 1px solid #d0d7de;",
      "  display: flex; gap: 0.4rem;",
      "}",
      ".lvcodex-companion-form input {",
      "  flex: 1; padding: 0.45rem 0.6rem; border: 1px solid #d0d7de;",
      "  border-radius: 6px; font-size: 0.9rem;",
      "}",
      ".lvcodex-companion-form button {",
      "  padding: 0.45rem 0.9rem; border: 0; border-radius: 6px;",
      "  background: #146b63; color: #fff; font-weight: 600; cursor: pointer;",
      "}",
      ".lvcodex-companion-form button[disabled] { opacity: 0.6; cursor: progress; }",
      ".lvcodex-companion-status {",
      "  padding: 0.3rem 0.75rem; font-size: 0.72rem; color: #57606a;",
      "  background: #f6f8fa; border-top: 1px solid #d0d7de;",
      "  display: flex; justify-content: space-between; gap: 0.5rem;",
      "}",
      ".lvcodex-companion-error {",
      "  color: #cf222e; font-size: 0.8rem; padding: 0.4rem 0.75rem;",
      "}",
      ".lvcodex-companion-error[hidden] { display: none !important; }",
      "@media (max-width: 480px) {",
      "  .lvcodex-companion-panel {",
      "    right: 0.5rem; left: 0.5rem; width: auto; bottom: 4.5rem;",
      "  }",
      "}",
    ].join("\n");
    document.head.appendChild(style);
  }

  function buildDom() {
    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "lvcodex-companion-toggle";
    toggle.setAttribute("aria-label", "Open AI companion");
    toggle.setAttribute("aria-haspopup", "dialog");
    toggle.setAttribute("aria-controls", "lvcodex-companion-panel");
    toggle.setAttribute("aria-expanded", "false");
    toggle.textContent = "💬";

    var badge = document.createElement("span");
    badge.className = "badge";
    badge.hidden = true;
    badge.setAttribute("aria-hidden", "true");
    toggle.appendChild(badge);

    var panel = document.createElement("section");
    panel.className = "lvcodex-companion-panel";
    panel.id = "lvcodex-companion-panel";
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "AI tutor companion");

    var header = document.createElement("header");
    header.className = "lvcodex-companion-header";
    var title = document.createElement("h2");
    title.textContent = "Anete — tava skolotāja";
    header.appendChild(title);
    var closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Close companion");
    closeBtn.textContent = "×";
    header.appendChild(closeBtn);
    panel.appendChild(header);

    var nudgeBox = document.createElement("div");
    nudgeBox.className = "lvcodex-companion-nudge";
    nudgeBox.hidden = true;
    nudgeBox.setAttribute("role", "status");
    panel.appendChild(nudgeBox);

    var history = document.createElement("div");
    history.className = "lvcodex-companion-history";
    history.setAttribute("aria-live", "polite");
    history.setAttribute("aria-label", "Conversation history");
    panel.appendChild(history);

    var errorBox = document.createElement("div");
    errorBox.className = "lvcodex-companion-error";
    errorBox.hidden = true;
    errorBox.setAttribute("role", "alert");
    panel.appendChild(errorBox);

    var form = document.createElement("form");
    form.className = "lvcodex-companion-form";
    form.setAttribute("autocomplete", "off");
    var input = document.createElement("input");
    input.type = "text";
    input.placeholder = "Raksti ziņojumu… (Latvian or English)";
    input.maxLength = MAX_MESSAGE_LEN;
    input.setAttribute("aria-label", "Companion message");
    form.appendChild(input);
    var sendBtn = document.createElement("button");
    sendBtn.type = "submit";
    sendBtn.textContent = "Send";
    form.appendChild(sendBtn);
    panel.appendChild(form);

    var statusBar = document.createElement("div");
    statusBar.className = "lvcodex-companion-status";
    var statusLeft = document.createElement("span");
    statusLeft.textContent = "Memory: 0 / 2048 bytes";
    var statusRight = document.createElement("span");
    statusRight.textContent = "Quota: —";
    statusBar.appendChild(statusLeft);
    statusBar.appendChild(statusRight);
    panel.appendChild(statusBar);

    elements = {
      toggle: toggle,
      badge: badge,
      panel: panel,
      closeBtn: closeBtn,
      nudgeBox: nudgeBox,
      history: history,
      errorBox: errorBox,
      form: form,
      input: input,
      sendBtn: sendBtn,
      statusLeft: statusLeft,
      statusRight: statusRight,
    };
  }

  function showError(msg) {
    if (!msg) {
      elements.errorBox.hidden = true;
      elements.errorBox.textContent = "";
      return;
    }
    elements.errorBox.hidden = false;
    elements.errorBox.textContent = msg;
  }

  function renderHistory() {
    while (elements.history.firstChild) {
      elements.history.removeChild(elements.history.firstChild);
    }
    if (!state.history.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = state.authenticated
        ? "Sasveicinies ar Aneti — say hello to start (or write in English)."
        : "Sign in to chat with your AI tutor.";
      elements.history.appendChild(empty);
      return;
    }
    state.history.forEach(function (turn) {
      var bubble = document.createElement("div");
      bubble.className =
        "lvcodex-companion-msg " + (turn.role === "user" ? "user" : "assistant");
      bubble.textContent = turn.content;
      elements.history.appendChild(bubble);
    });
    elements.history.scrollTop = elements.history.scrollHeight;
  }

  function renderNudge() {
    var nudge = state.nudge;
    if (!nudge || !nudge.message_lv) {
      elements.nudgeBox.hidden = true;
      elements.nudgeBox.textContent = "";
      return;
    }
    elements.nudgeBox.hidden = false;
    elements.nudgeBox.className =
      "lvcodex-companion-nudge severity-" + (nudge.severity || "info");
    while (elements.nudgeBox.firstChild) {
      elements.nudgeBox.removeChild(elements.nudgeBox.firstChild);
    }
    var lv = document.createElement("span");
    lv.textContent = nudge.message_lv;
    elements.nudgeBox.appendChild(lv);
    if (nudge.message_en) {
      var en = document.createElement("span");
      en.className = "en";
      en.textContent = nudge.message_en;
      elements.nudgeBox.appendChild(en);
    }
  }

  function renderStatus() {
    elements.statusLeft.textContent =
      "Memory: " +
      state.memorySummaryBytes +
      " / " +
      state.memoryBudget +
      " bytes (" +
      state.conversationCount +
      " turns)";
  }

  function setQuota(quota) {
    if (!quota || quota.limit === undefined) {
      elements.statusRight.textContent = "Quota: —";
      return;
    }
    elements.statusRight.textContent =
      "Quota: " + (quota.used || 0) + "/" + quota.limit;
  }

  function setBadge(text) {
    if (!text) {
      elements.badge.hidden = true;
      elements.badge.textContent = "";
      return;
    }
    elements.badge.hidden = false;
    elements.badge.textContent = text;
  }

  function openPanel() {
    state.open = true;
    elements.panel.hidden = false;
    elements.toggle.setAttribute("aria-expanded", "true");
    setBadge("");
    setTimeout(function () {
      elements.input.focus();
    }, 50);
  }

  function closePanel() {
    state.open = false;
    elements.panel.hidden = true;
    elements.toggle.setAttribute("aria-expanded", "false");
    elements.toggle.focus();
  }

  async function probeSession() {
    try {
      var response = await fetch(SESSION_ENDPOINT, {
        credentials: "same-origin",
      });
      if (!response.ok) {
        state.authenticated = false;
        return;
      }
      var payload = await response.json().catch(function () {
        return null;
      });
      state.authenticated = Boolean(payload && payload.account);
    } catch (error) {
      state.authenticated = false;
    }
  }

  async function loadNudge() {
    if (!state.authenticated) {
      state.nudge = null;
      renderNudge();
      return;
    }
    try {
      var response = await fetch(NUDGE_ENDPOINT, {
        credentials: "same-origin",
      });
      if (!response.ok) {
        state.nudge = null;
        renderNudge();
        return;
      }
      var payload = await response.json();
      state.nudge = payload || null;
      renderNudge();
      // Subtle badge — a celebrate/warn nudge is worth a "1" notification.
      if (state.nudge && state.nudge.severity !== "info" && !state.open) {
        setBadge("1");
      }
    } catch (error) {
      state.nudge = null;
      renderNudge();
    }
  }

  async function sendMessage(message) {
    if (!state.authenticated) {
      showError("Sign in to chat with your AI tutor.");
      return;
    }
    if (state.inflight) return;
    state.inflight = true;
    elements.sendBtn.disabled = true;
    elements.input.disabled = true;
    showError("");
    state.history.push({ role: "user", content: message });
    renderHistory();
    try {
      var response = await fetch(CHAT_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ message: message }),
      });
      var payload = await response.json().catch(function () {
        return {};
      });
      if (!response.ok) {
        state.history.pop();
        renderHistory();
        var label =
          (payload && (payload.code || payload.error)) ||
          "HTTP " + response.status;
        var detail =
          (payload && (payload.message || payload.error)) || "Request failed.";
        showError(label + ": " + detail);
        return;
      }
      var reply = (payload && payload.reply) || "";
      var memory = (payload && payload.memory) || {};
      var quota = (payload && payload.quota) || {};
      state.history.push({ role: "assistant", content: reply });
      state.memorySummaryBytes = Number(memory.summary_bytes || 0);
      state.memoryBudget = Number(memory.summary_budget_bytes || 2048);
      state.conversationCount = Number(memory.conversation_count || 0);
      renderHistory();
      renderStatus();
      setQuota(quota);
    } catch (error) {
      state.history.pop();
      renderHistory();
      showError("Network error: " + (error && error.message ? error.message : "unknown"));
    } finally {
      state.inflight = false;
      elements.sendBtn.disabled = false;
      elements.input.disabled = false;
      elements.input.value = "";
      elements.input.focus();
    }
  }

  function wireEvents() {
    elements.toggle.addEventListener("click", function () {
      if (state.open) {
        closePanel();
      } else {
        openPanel();
      }
    });
    elements.closeBtn.addEventListener("click", closePanel);
    elements.panel.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        event.preventDefault();
        closePanel();
      }
    });
    elements.form.addEventListener("submit", function (event) {
      event.preventDefault();
      var message = (elements.input.value || "").trim();
      if (!message) return;
      if (message.length > MAX_MESSAGE_LEN) {
        message = message.slice(0, MAX_MESSAGE_LEN);
      }
      sendMessage(message);
    });
  }

  async function init() {
    injectStyles();
    buildDom();
    document.body.appendChild(elements.toggle);
    document.body.appendChild(elements.panel);
    wireEvents();
    renderHistory();
    renderStatus();
    await probeSession();
    if (state.authenticated) {
      await loadNudge();
    } else {
      renderNudge();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

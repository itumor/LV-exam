/*
 * T-055 — Procedural story (choose-your-own-adventure) UI.
 *
 * Vanilla JS, no framework. Talks to two endpoints shipped by
 * ``server_app/routes/procedural_story.py``:
 *
 *   GET  /api/stories/state               — load the persisted state
 *   POST /api/stories/generate-chapter    — generate the next chapter
 *
 * Flow:
 *   1. On load, ``GET /api/stories/state`` hydrates the chapter list.
 *   2. If there are no chapters yet, the user clicks "Begin story" and
 *      we ``POST /api/stories/generate-chapter`` with no choice_id.
 *   3. Once a chapter is rendered, each choice button issues another
 *      POST carrying ``{"choice_id": "..."}``. The server records the
 *      selection and returns the *next* chapter atomically.
 *   4. "Reset" sends ``{"reset": true}`` to wipe the row and start over.
 *
 * Multi-state UX: empty (no story), loading, in-progress (chapter +
 * choices), finished (max chapters reached), error.
 *
 * Defensive: every DOM write uses textContent (no innerHTML) so
 * untrusted LLM output cannot inject markup. Choice ids are clamped to
 * a short alphanumeric whitelist before sending to the server.
 */

(function () {
  "use strict";

  var ENDPOINT_STATE = "/api/stories/state";
  var ENDPOINT_GENERATE = "/api/stories/generate-chapter";

  var state = {
    seed: "",
    chapterIndex: 0,
    chapters: [],
    pendingChoice: false,
    isFinished: false,
    quota: null,
    inflight: false,
  };

  var elements = {
    main: document.getElementById("story-main"),
    chapters: document.getElementById("story-chapters"),
    chaptersEmpty: document.getElementById("story-chapters-empty"),
    choicesWrap: document.getElementById("story-choices-wrap"),
    choicesEmpty: document.getElementById("story-choices-empty"),
    choices: document.getElementById("story-choices"),
    finished: document.getElementById("story-finished"),
    begin: document.getElementById("story-begin"),
    reset: document.getElementById("story-reset"),
    progress: document.getElementById("story-progress"),
    quota: document.getElementById("story-quota"),
    error: document.getElementById("story-error"),
  };

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  function setError(message) {
    if (!message) {
      elements.error.hidden = true;
      elements.error.textContent = "";
      return;
    }
    elements.error.hidden = false;
    elements.error.textContent = message;
  }

  function clearChildren(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function sanitiseChoiceId(raw) {
    if (typeof raw !== "string") return "";
    var cleaned = raw.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 8);
    return cleaned.toUpperCase();
  }

  function updateProgress() {
    var label = "Chapter: ";
    if (!state.chapters.length) {
      label += "—";
    } else {
      label += state.chapterIndex + " of up to 12";
    }
    elements.progress.textContent = label;
  }

  function updateQuotaBadge() {
    if (!state.quota) {
      elements.quota.textContent = "Quota: —";
      return;
    }
    elements.quota.textContent =
      "Quota: " + state.quota.used + " / " + state.quota.limit;
  }

  function updateButtons() {
    var hasChapters = state.chapters.length > 0;
    elements.begin.disabled = state.inflight || hasChapters || state.isFinished;
    elements.begin.textContent = hasChapters ? "Story in progress" : "Begin story";
    elements.reset.disabled = state.inflight || !hasChapters;
  }

  function renderChapter(chapter, isCurrent) {
    var card = document.createElement("div");
    card.className = "story-chapter" + (isCurrent ? " is-current" : "");

    var label = document.createElement("div");
    label.className = "chapter-label";
    label.textContent = "Chapter " + chapter.index;
    card.appendChild(label);

    var body = document.createElement("p");
    body.className = "chapter-narrative";
    body.textContent = chapter.narrative || "";
    card.appendChild(body);

    if (chapter.selected_choice_label) {
      var sel = document.createElement("div");
      sel.className = "chapter-selected";
      sel.textContent = "You chose: " + chapter.selected_choice_label;
      card.appendChild(sel);
    }
    return card;
  }

  function renderChapters() {
    clearChildren(elements.chapters);
    if (!state.chapters.length) {
      elements.chapters.appendChild(elements.chaptersEmpty);
      elements.chaptersEmpty.hidden = false;
      return;
    }
    elements.chaptersEmpty.hidden = true;
    for (var i = 0; i < state.chapters.length; i++) {
      var ch = state.chapters[i];
      var isCurrent = i === state.chapters.length - 1;
      elements.chapters.appendChild(renderChapter(ch, isCurrent));
    }
    elements.chapters.scrollTop = elements.chapters.scrollHeight;
  }

  function renderChoices() {
    clearChildren(elements.choices);
    if (state.isFinished) {
      elements.choices.hidden = true;
      elements.choicesEmpty.hidden = true;
      elements.finished.hidden = false;
      return;
    }
    elements.finished.hidden = true;
    if (!state.chapters.length) {
      elements.choices.hidden = true;
      elements.choicesEmpty.hidden = false;
      elements.choicesEmpty.textContent =
        "Press Begin story above to get your first chapter.";
      return;
    }
    var latest = state.chapters[state.chapters.length - 1];
    var choices = (latest && latest.choices) || [];
    if (!choices.length || latest.selected_choice_id) {
      elements.choices.hidden = true;
      elements.choicesEmpty.hidden = false;
      elements.choicesEmpty.textContent =
        latest.selected_choice_id
          ? "Generating next chapter…"
          : "No choices available — try reset.";
      return;
    }
    elements.choicesEmpty.hidden = true;
    elements.choices.hidden = false;
    for (var j = 0; j < choices.length; j++) {
      var choice = choices[j];
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "story-choice";
      btn.disabled = state.inflight;
      btn.dataset.choiceId = sanitiseChoiceId(choice.id);

      var keyNode = document.createElement("span");
      keyNode.className = "key";
      keyNode.setAttribute("aria-hidden", "true");
      keyNode.textContent = (choice.id || "?").toString().slice(0, 2).toUpperCase();
      btn.appendChild(keyNode);

      var labelNode = document.createElement("span");
      labelNode.className = "label";
      labelNode.textContent = choice.label || "";
      btn.appendChild(labelNode);

      btn.addEventListener(
        "click",
        (function (id) {
          return function () { onChoiceClicked(id); };
        })(btn.dataset.choiceId),
      );
      elements.choices.appendChild(btn);
    }
  }

  function render() {
    renderChapters();
    renderChoices();
    updateProgress();
    updateQuotaBadge();
    updateButtons();
  }

  // ------------------------------------------------------------------
  // Network helpers
  // ------------------------------------------------------------------

  function applyState(snapshot) {
    if (!snapshot) return;
    state.seed = snapshot.story_seed || "";
    state.chapterIndex = snapshot.chapter_index || 0;
    state.chapters = Array.isArray(snapshot.chapters) ? snapshot.chapters : [];
    state.pendingChoice = !!snapshot.pending_choice;
    state.isFinished = !!snapshot.is_finished;
  }

  function applyResponse(body) {
    if (!body) return;
    if (body.state) applyState(body.state);
    if (body.quota) state.quota = body.quota;
  }

  function handleError(error) {
    var message = "Could not reach the story server.";
    if (error && typeof error.message === "string" && error.message) {
      message = error.message;
    }
    setError(message);
  }

  async function fetchJson(url, options) {
    var response = await fetch(url, options);
    var text = await response.text();
    var data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = null; }
    if (!response.ok) {
      var msg = (data && (data.message || data.error)) || response.statusText;
      throw new Error(msg || "Request failed");
    }
    return data;
  }

  async function loadState() {
    setError(null);
    try {
      var data = await fetchJson(ENDPOINT_STATE, { credentials: "same-origin" });
      applyState(data);
      render();
    } catch (e) {
      handleError(e);
      render();
    }
  }

  async function postGenerate(body) {
    if (state.inflight) return;
    state.inflight = true;
    setError(null);
    render();
    try {
      var data = await fetchJson(ENDPOINT_GENERATE, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      applyResponse(data);
    } catch (e) {
      handleError(e);
    } finally {
      state.inflight = false;
      render();
    }
  }

  // ------------------------------------------------------------------
  // Event handlers
  // ------------------------------------------------------------------

  function onChoiceClicked(choiceId) {
    var clean = sanitiseChoiceId(choiceId);
    if (!clean) {
      setError("Invalid choice id.");
      return;
    }
    postGenerate({ choice_id: clean });
  }

  function onBeginClicked() {
    postGenerate({});
  }

  function onResetClicked() {
    if (!window.confirm("Reset your story? This deletes the current chapters.")) {
      return;
    }
    postGenerate({ reset: true });
  }

  function attach() {
    elements.begin.addEventListener("click", onBeginClicked);
    elements.reset.addEventListener("click", onResetClicked);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      attach();
      loadState();
    });
  } else {
    attach();
    loadState();
  }
})();

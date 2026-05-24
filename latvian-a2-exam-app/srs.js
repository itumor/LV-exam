/**
 * T-032 — SRS flashcard UI.
 *
 * Drives the spaced-repetition flow against the three backend routes
 * documented by ``server_app/services/srs.py``:
 *
 *   GET  /api/srs/due                       → load today's deck
 *   POST /api/srs/cards                     → enqueue a new card
 *   POST /api/srs/cards/{id}/review {q:0-5} → grade the current card
 *
 * The UI is intentionally simple: one card at a time, "Reveal" first to
 * remove temptation, then six grade buttons that match the SuperMemo-2
 * 0-5 scale. After each grade the card is removed from the local queue
 * and the next card slides in; when the queue empties we render an
 * empty-state with the in-page "Add a card" form so the learner can
 * seed their own vocabulary.
 *
 * Auth is shared with the rest of the app: the request runs against the
 * same cookie/session the user has from ``/api/auth/login``. A 401
 * response surfaces a friendly status line that links back to the main
 * app for sign-in.
 */
(function () {
  "use strict";

  const els = {
    status: document.getElementById("srs-status"),
    card: document.getElementById("srs-card"),
    lv: document.getElementById("srs-card-lv"),
    en: document.getElementById("srs-card-en"),
    meta: document.getElementById("srs-meta"),
    position: document.getElementById("srs-position"),
    due: document.getElementById("srs-due-meta"),
    actions: document.getElementById("srs-actions"),
    revealRow: document.getElementById("srs-reveal-row"),
    reveal: document.getElementById("srs-reveal"),
    grades: document.getElementById("srs-grades"),
    empty: document.getElementById("srs-empty"),
    addForm: document.getElementById("srs-add-form"),
  };

  /** @type {Array<{id:string,lv:string,en:string,lemma:string,next_due:string}>} */
  let queue = [];
  let index = 0;
  let revealed = false;
  let busy = false;

  function setStatus(message, isError) {
    els.status.textContent = message || "";
    els.status.classList.toggle("is-error", Boolean(isError));
  }

  function showQueueState() {
    if (queue.length === 0) {
      els.card.hidden = true;
      els.meta.hidden = true;
      els.actions.hidden = true;
      els.empty.hidden = false;
      setStatus("Queue clear — see you tomorrow.");
      return;
    }
    const card = queue[index];
    els.card.hidden = false;
    els.meta.hidden = false;
    els.actions.hidden = false;
    els.empty.hidden = true;
    els.lv.textContent = card.lv;
    els.en.textContent = card.en;
    els.position.textContent = `Card ${index + 1} of ${queue.length}`;
    els.due.textContent = `next due ${card.next_due}`;
    revealed = false;
    els.card.classList.add("is-hidden");
    els.revealRow.hidden = false;
    els.grades.hidden = true;
  }

  function reveal() {
    if (queue.length === 0) return;
    revealed = true;
    els.card.classList.remove("is-hidden");
    els.revealRow.hidden = true;
    els.grades.hidden = false;
  }

  async function loadDue() {
    setStatus("Loading your due cards…");
    try {
      const res = await fetch("/api/srs/due", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (res.status === 401) {
        setStatus("Please sign in to use SRS.", true);
        return;
      }
      if (!res.ok) {
        setStatus(`Failed to load: ${res.status}`, true);
        return;
      }
      const payload = await res.json();
      queue = Array.isArray(payload.cards) ? payload.cards : [];
      index = 0;
      if (queue.length === 0) {
        showQueueState();
      } else {
        setStatus(`${queue.length} card${queue.length === 1 ? "" : "s"} due.`);
        showQueueState();
      }
    } catch (err) {
      setStatus(`Network error: ${String(err)}`, true);
    }
  }

  async function gradeCurrent(quality) {
    if (busy || queue.length === 0) return;
    const card = queue[index];
    busy = true;
    Array.from(els.grades.children).forEach((b) => (b.disabled = true));
    try {
      const res = await fetch(
        `/api/srs/cards/${encodeURIComponent(card.id)}/review`,
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ quality }),
        }
      );
      if (!res.ok) {
        setStatus(`Review failed (${res.status}).`, true);
        return;
      }
      // Remove the just-graded card from the local queue. The next call
      // to ``loadDue`` will fetch a fresh authoritative list — for now
      // we advance locally so the UI feels responsive.
      queue.splice(index, 1);
      if (index >= queue.length) index = 0;
      showQueueState();
    } catch (err) {
      setStatus(`Network error: ${String(err)}`, true);
    } finally {
      busy = false;
      Array.from(els.grades.children).forEach((b) => (b.disabled = false));
    }
  }

  async function addCard(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const lemma = String(formData.get("lemma") || "").trim();
    const lv = String(formData.get("lv") || "").trim();
    const en = String(formData.get("en") || "").trim();
    if (!lemma || !lv || !en) {
      setStatus("All three fields are required.", true);
      return;
    }
    setStatus("Adding card…");
    try {
      const res = await fetch("/api/srs/cards", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ lemma, lv, en }),
      });
      if (!res.ok) {
        setStatus(`Add failed (${res.status}).`, true);
        return;
      }
      form.reset();
      setStatus("Card added — refreshing queue…");
      await loadDue();
    } catch (err) {
      setStatus(`Network error: ${String(err)}`, true);
    }
  }

  els.reveal.addEventListener("click", reveal);
  Array.from(els.grades.querySelectorAll(".srs-grade")).forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = Number(btn.dataset.q);
      if (!Number.isInteger(q) || q < 0 || q > 5) return;
      gradeCurrent(q);
    });
  });
  els.addForm.addEventListener("submit", addCard);

  // Keyboard shortcuts: space reveals, 0-5 grades.
  document.addEventListener("keydown", (ev) => {
    if (ev.target && ["INPUT", "TEXTAREA"].includes(ev.target.tagName)) {
      return;
    }
    if (ev.key === " " || ev.key === "Enter") {
      if (!revealed) {
        ev.preventDefault();
        reveal();
      }
      return;
    }
    if (!revealed) return;
    const num = Number(ev.key);
    if (Number.isInteger(num) && num >= 0 && num <= 5) {
      ev.preventDefault();
      gradeCurrent(num);
    }
  });

  loadDue();
})();

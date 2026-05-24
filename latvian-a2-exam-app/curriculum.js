/*
 * T-054 — AI curriculum generator (Custom lesson tile + viewer).
 *
 * Standalone vanilla-JS controller for `curriculum.html`. Talks to:
 *
 *   POST /api/curriculum/generate  — produce or cache-fetch a lesson.
 *   GET  /api/curriculum/lessons   — list the learner's cached lessons.
 *
 * Also exposes a `mountTile(targetSelector)` helper so any host page can
 * embed a small "Custom lesson" tile that links here. The tile is also
 * auto-injected at the top of `<main>` on `latvian-a2-exam-app/index.html`
 * when the script loads (see the `autoInjectTile()` call at the bottom).
 *
 * No build step, no framework. Every dynamic insertion uses
 * `textContent` so server / user strings can never inject markup.
 */

(function () {
  "use strict";

  var GENERATE_ENDPOINT = "/api/curriculum/generate";
  var LIST_ENDPOINT = "/api/curriculum/lessons";

  var SKILL_LABELS = {
    listening: "Klausīšanās",
    reading: "Lasīšana",
    writing: "Rakstīšana",
    speaking: "Runāšana",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function setStatus(message, isError) {
    var el = $("lesson-status");
    if (!el) return;
    el.textContent = message;
    if (isError) {
      el.classList.add("is-error");
    } else {
      el.classList.remove("is-error");
    }
  }

  function clearChildren(node) {
    while (node && node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function makeElement(tag, options) {
    var el = document.createElement(tag);
    options = options || {};
    if (options.className) el.className = options.className;
    if (options.text !== undefined && options.text !== null) {
      el.textContent = String(options.text);
    }
    if (options.attrs) {
      Object.keys(options.attrs).forEach(function (key) {
        el.setAttribute(key, options.attrs[key]);
      });
    }
    return el;
  }

  function renderLessonCard(lesson, opts) {
    opts = opts || {};
    var card = makeElement("article", { className: "lvcodex-lesson-card" });

    var content = lesson.content || {};

    var meta = makeElement("div", { className: "lvcodex-lesson-meta" });
    var skillPill = makeElement("span", {
      className: "pill",
      text: SKILL_LABELS[lesson.weak_skill] || lesson.weak_skill || "",
    });
    meta.appendChild(skillPill);
    if (opts.cached) {
      meta.appendChild(
        makeElement("span", { className: "pill is-cached", text: "From cache" })
      );
    }
    if (lesson.expires_at) {
      meta.appendChild(
        makeElement("span", { text: "Expires " + lesson.expires_at })
      );
    }
    card.appendChild(meta);

    card.appendChild(makeElement("h2", { text: content.title || "Lesson" }));
    card.appendChild(
      makeElement("p", {
        className: "objective",
        text: content.objective || "",
      })
    );

    if (Array.isArray(content.vocab) && content.vocab.length) {
      card.appendChild(makeElement("h3", { text: "Vocabulary" }));
      var ul = makeElement("ul", { className: "vocab-list" });
      content.vocab.forEach(function (item) {
        var li = makeElement("li");
        var strong = makeElement("strong", { text: item.lv || "" });
        li.appendChild(strong);
        li.appendChild(document.createTextNode(" — " + (item.en || "")));
        ul.appendChild(li);
      });
      card.appendChild(ul);
    }

    if (Array.isArray(content.drills) && content.drills.length) {
      card.appendChild(makeElement("h3", { text: "Drills" }));
      content.drills.forEach(function (drill, idx) {
        var section = makeElement("div", { className: "drill" });
        section.appendChild(
          makeElement("div", {
            className: "prompt-lv",
            text: idx + 1 + ". " + (drill.prompt_lv || ""),
          })
        );
        section.appendChild(
          makeElement("div", {
            className: "prompt-en",
            text: drill.prompt_en || "",
          })
        );
        var revealBtn = makeElement("button", {
          attrs: { type: "button" },
          text: "Show answer",
        });
        var answer = makeElement("div", { className: "answer" });
        answer.appendChild(
          makeElement("div", { text: "Answer: " + (drill.answer_lv || "") })
        );
        if (drill.rationale_en) {
          answer.appendChild(
            makeElement("div", { text: drill.rationale_en })
          );
        }
        revealBtn.addEventListener("click", function () {
          section.classList.toggle("is-revealed");
          revealBtn.textContent = section.classList.contains("is-revealed")
            ? "Hide answer"
            : "Show answer";
        });
        section.appendChild(revealBtn);
        section.appendChild(answer);
        card.appendChild(section);
      });
    }

    if (content.reflection_prompt_en) {
      card.appendChild(
        makeElement("div", {
          className: "reflection",
          text: content.reflection_prompt_en,
        })
      );
    }

    return card;
  }

  function renderHistory(lessons) {
    var container = $("lesson-history");
    if (!container) return;
    clearChildren(container);
    container.classList.remove("lvcodex-lesson-empty");
    if (!Array.isArray(lessons) || lessons.length === 0) {
      container.classList.add("lvcodex-lesson-empty");
      container.textContent = "No lessons yet.";
      return;
    }
    lessons.forEach(function (lesson) {
      container.appendChild(renderLessonCard(lesson, { cached: true }));
    });
  }

  function refreshHistory() {
    fetch(LIST_ENDPOINT, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (resp) {
        if (!resp.ok) throw new Error("history_unavailable");
        return resp.json();
      })
      .then(function (payload) {
        renderHistory(payload.lessons || []);
      })
      .catch(function () {
        // Silent — history is non-critical.
      });
  }

  function showLesson(lesson) {
    var output = $("lesson-output");
    if (!output) return;
    clearChildren(output);
    output.appendChild(renderLessonCard(lesson, { cached: !!lesson.cached }));
  }

  function setBusy(isBusy) {
    var generate = $("generate-btn");
    var refresh = $("refresh-btn");
    if (generate) generate.disabled = isBusy;
    if (refresh) refresh.disabled = isBusy;
  }

  function generateLesson(forceRefresh) {
    var select = $("weak-skill-select");
    var weakSkill = select ? select.value : "";
    var body = { force_refresh: !!forceRefresh };
    if (weakSkill) body.weak_skill = weakSkill;
    setStatus("Generating your lesson…");
    setBusy(true);
    fetch(GENERATE_ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })
      .then(function (resp) {
        if (resp.status === 401) {
          throw new Error("Please sign in to generate a lesson.");
        }
        if (resp.status === 429) {
          throw new Error("Daily AI quota exhausted — try again tomorrow.");
        }
        if (!resp.ok) {
          throw new Error("Lesson generation failed (" + resp.status + ").");
        }
        return resp.json();
      })
      .then(function (lesson) {
        showLesson(lesson);
        setStatus(
          lesson.cached
            ? "Lesson loaded from cache (no AI quota used)."
            : "Fresh lesson generated.",
          false
        );
        refreshHistory();
      })
      .catch(function (err) {
        setStatus(err.message || "Lesson generation failed.", true);
      })
      .then(function () {
        setBusy(false);
      });
  }

  function mountTile(targetSelector) {
    var target =
      typeof targetSelector === "string"
        ? document.querySelector(targetSelector)
        : targetSelector;
    if (!target || target.querySelector(".lvcodex-custom-lesson-tile")) return;
    var tile = makeElement("a", {
      className: "lvcodex-custom-lesson-tile",
      attrs: {
        href: "./curriculum.html",
        "data-t054-tile": "custom-lesson",
        role: "button",
      },
    });
    tile.style.cssText = [
      "display: flex",
      "align-items: center",
      "gap: 0.75rem",
      "padding: 0.85rem 1rem",
      "background: linear-gradient(135deg, #0969da 0%, #1f6feb 100%)",
      "color: #fff",
      "border-radius: 10px",
      "text-decoration: none",
      "margin: 0.5rem 0 1rem",
      "box-shadow: 0 2px 6px rgba(9, 105, 218, 0.18)",
    ].join("; ");
    var icon = makeElement("span", { text: "✨" });
    icon.style.fontSize = "1.4rem";
    icon.style.flex = "0 0 auto";
    icon.setAttribute("aria-hidden", "true");
    tile.appendChild(icon);
    var label = makeElement("span");
    label.appendChild(
      makeElement("strong", { text: "Custom lesson" })
    );
    label.appendChild(document.createElement("br"));
    label.appendChild(
      makeElement("small", {
        text: "AI-generated micro-lesson personalised to your weakest skill.",
      })
    );
    label.style.lineHeight = "1.3";
    tile.appendChild(label);
    target.insertBefore(tile, target.firstChild);
  }

  function autoInjectTile() {
    // Pick the first reasonable container on the host page.
    var hosts = [
      "#dashboard-output",
      "#runner-output",
      "main.workspace",
      "main",
    ];
    for (var i = 0; i < hosts.length; i++) {
      var node = document.querySelector(hosts[i]);
      if (node) {
        mountTile(node);
        return;
      }
    }
  }

  function init() {
    var generate = $("generate-btn");
    var refresh = $("refresh-btn");
    if (generate) {
      generate.addEventListener("click", function () {
        generateLesson(false);
      });
    }
    if (refresh) {
      refresh.addEventListener("click", function () {
        generateLesson(true);
      });
    }
    if ($("lesson-output")) {
      // We're on the dedicated curriculum page — fetch history.
      refreshHistory();
    } else {
      // We're on a host page — install the tile only.
      autoInjectTile();
    }
  }

  // Expose for host-page integrations + tests.
  window.lvcodexCurriculum = {
    mountTile: mountTile,
    generateLesson: generateLesson,
    refreshHistory: refreshHistory,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

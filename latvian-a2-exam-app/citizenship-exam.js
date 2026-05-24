/* T-071 — Latvian naturalisation (citizenship) exam simulator.
 *
 * Renders the citizenship exam manifest at
 *   /content/exams/NAT/NAT_Exam_01.exam.json
 * (or whichever manifest is exposed via /api/exams/<id>) into a three-section
 * form (history / constitution / language), collects answers, and scores them
 * client-side using the dual-section pass rule:
 *
 *   history + constitution combined >= MIN_HISTORY_CONSTITUTION (default 12/20)
 *   language                          >= MIN_LANGUAGE              (default 9/15)
 *
 * Both thresholds must be met for a PASS. Partial passes (e.g. acing the
 * knowledge sections but failing language) are explicitly rejected — this is
 * the T-071 contract mirrored from
 * server_app/services/citizenship_scoring.py.
 *
 * The JS scorer is a faithful client-side mirror of the Python scorer so the
 * "Submit" experience is instant; the server remains the canonical source of
 * truth when the simulator is wired to the backend.
 */

(function () {
  "use strict";

  const MANIFEST_URL = "/content/exams/NAT/NAT_Exam_01.exam.json";
  const DEFAULT_MIN_HISTORY_CONSTITUTION = 12;
  const DEFAULT_MIN_LANGUAGE = 9;
  const CITIZENSHIP_SECTIONS = ["history", "constitution", "language"];

  let manifest = null;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function fetchManifest() {
    return fetch(MANIFEST_URL, { credentials: "same-origin" })
      .then((r) => {
        if (!r.ok) {
          throw new Error("HTTP " + r.status);
        }
        return r.json();
      });
  }

  function sectionBySkill(skill) {
    if (!manifest || !Array.isArray(manifest.sections)) {
      return null;
    }
    return manifest.sections.find((s) => s.skill === skill) || null;
  }

  function renderMultipleChoiceQuestion(question, sectionSkill, taskKey, prefix) {
    const number = question.number;
    const inputName = `${sectionSkill}__${taskKey}__q${number}`;
    const opts = (question.options || [])
      .map(
        (opt) =>
          `<div class="form-check">
             <input class="form-check-input" type="radio" name="${escapeHtml(inputName)}" id="${escapeHtml(inputName)}_${escapeHtml(opt.label)}" value="${escapeHtml(opt.label)}">
             <label class="form-check-label" for="${escapeHtml(inputName)}_${escapeHtml(opt.label)}">
               <strong>${escapeHtml(opt.label)})</strong> ${escapeHtml(opt.text)}
             </label>
           </div>`
      )
      .join("");
    const passage = question.passage
      ? `<div class="nat-passage">${escapeHtml(question.passage)}</div>`
      : "";
    return `<div class="nat-q" data-section="${escapeHtml(sectionSkill)}" data-task="${escapeHtml(taskKey)}" data-q="${escapeHtml(number)}" data-kind="multiple_choice">
              ${passage}
              <div class="nat-prompt">${prefix}${escapeHtml(number)}. ${escapeHtml(question.prompt || "")}</div>
              ${opts}
            </div>`;
  }

  function renderGapFillQuestion(question, sectionSkill, taskKey) {
    const number = question.number;
    const inputName = `${sectionSkill}__${taskKey}__q${number}`;
    return `<div class="nat-q" data-section="${escapeHtml(sectionSkill)}" data-task="${escapeHtml(taskKey)}" data-q="${escapeHtml(number)}" data-kind="gap_fill">
              <div class="nat-prompt">${escapeHtml(number)}. ${escapeHtml(question.prompt || "")}</div>
              <input type="text" class="form-control" name="${escapeHtml(inputName)}" placeholder="Ievadiet vārdu pareizajā formā" autocomplete="off">
            </div>`;
  }

  function renderSubjectiveQuestion(question, sectionSkill, taskKey) {
    const number = question.number;
    const inputName = `${sectionSkill}__${taskKey}__q${number}`;
    const minWords = question.minimum_words
      ? `<div class="form-text">Vismaz ${escapeHtml(question.minimum_words)} vārdi.</div>`
      : "";
    return `<div class="nat-q" data-section="${escapeHtml(sectionSkill)}" data-task="${escapeHtml(taskKey)}" data-q="${escapeHtml(number)}" data-kind="subjective">
              <div class="nat-prompt">${escapeHtml(question.prompt || "")}</div>
              <textarea class="form-control" name="${escapeHtml(inputName)}" rows="5" placeholder="Rakstiet šeit…"></textarea>
              ${minWords}
            </div>`;
  }

  function renderQuestion(question, sectionSkill, taskKey, prefix) {
    const kind = question.kind || "";
    if (kind === "gap_fill") {
      return renderGapFillQuestion(question, sectionSkill, taskKey);
    }
    if (kind === "subjective" || kind === "subjective_sentence") {
      return renderSubjectiveQuestion(question, sectionSkill, taskKey);
    }
    return renderMultipleChoiceQuestion(question, sectionSkill, taskKey, prefix || "");
  }

  function renderKnowledgeSection(section, containerId) {
    const container = $(containerId);
    if (!container || !section) {
      return;
    }
    const task = (section.tasks || [])[0];
    if (!task) {
      container.innerHTML = "<p class='text-muted'>Šajā sekcijā nav jautājumu.</p>";
      return;
    }
    const instruction = task.instruction
      ? `<p class="text-muted">${escapeHtml(task.instruction)}</p>`
      : "";
    const html = (task.questions || [])
      .map((q) => renderQuestion(q, section.skill, task.task_key, ""))
      .join("");
    container.innerHTML = instruction + html;
  }

  function renderLanguageSection(section) {
    const container = $("nat-language-tasks");
    if (!container || !section) {
      return;
    }
    const html = (section.tasks || [])
      .map((task) => {
        const title = `<h3 class="h5 mt-3">${escapeHtml(task.title || task.task_key)} <span class="text-muted">(${escapeHtml(task.points_max)} punkti)</span></h3>`;
        const instruction = task.instruction
          ? `<p class="text-muted">${escapeHtml(task.instruction)}</p>`
          : "";
        const qs = (task.questions || [])
          .map((q) => renderQuestion(q, section.skill, task.task_key, ""))
          .join("");
        return title + instruction + qs;
      })
      .join("");
    container.innerHTML = html;
  }

  function renderAll() {
    renderKnowledgeSection(sectionBySkill("history"), "nat-history-questions");
    renderKnowledgeSection(sectionBySkill("constitution"), "nat-constitution-questions");
    renderLanguageSection(sectionBySkill("language"));
    $("nat-loading").style.display = "none";
    $("nat-exam-form").style.display = "";
  }

  function collectAnswers() {
    const answers = { history: {}, constitution: {}, language: {} };
    document.querySelectorAll(".nat-q").forEach((el) => {
      const section = el.dataset.section;
      const task = el.dataset.task;
      const q = el.dataset.q;
      const kind = el.dataset.kind;
      if (!section || !task || !q) return;
      if (!answers[section][task]) answers[section][task] = {};

      if (kind === "multiple_choice") {
        const selected = el.querySelector("input[type='radio']:checked");
        if (selected) answers[section][task][q] = selected.value;
      } else if (kind === "gap_fill") {
        const input = el.querySelector("input[type='text']");
        if (input && input.value.trim() !== "") {
          answers[section][task][q] = input.value.trim();
        }
      } else if (kind === "subjective") {
        const ta = el.querySelector("textarea");
        if (ta && ta.value.trim() !== "") {
          answers[section][task][q] = ta.value.trim();
        }
      }
    });
    return answers;
  }

  function normaliseAnswer(v) {
    if (v == null) return "";
    if (typeof v === "boolean") return v ? "true" : "false";
    return String(v).trim().toLowerCase();
  }

  function correctSet(question) {
    let a = question.correct_answers;
    if (!Array.isArray(a) || a.length === 0) {
      if (question.correct_answer == null) return [];
      a = [question.correct_answer];
    }
    return a
      .filter((v) => v != null && String(v).trim() !== "")
      .map(normaliseAnswer);
  }

  /**
   * Mirror of server_app.services.citizenship_scoring.score_citizenship_attempt.
   * Returns the same shape as ``CitizenshipScore.as_dict()``.
   */
  function scoreCitizenshipAttempt(answers) {
    const scoringBlock = (manifest && manifest.scoring) || {};
    const minPerSection = scoringBlock.minimum_per_section || {};
    const minHC = Number(
      minPerSection.history_constitution_combined ||
        DEFAULT_MIN_HISTORY_CONSTITUTION
    );
    const minLang = Number(minPerSection.language || DEFAULT_MIN_LANGUAGE);

    const out = {
      history: 0,
      constitution: 0,
      language: 0,
      subjective_pending_language: 0,
      minimum_history_constitution: minHC,
      minimum_language: minLang,
      items: [],
    };

    (manifest.sections || []).forEach((section) => {
      const skill = section.skill;
      if (CITIZENSHIP_SECTIONS.indexOf(skill) < 0) return;
      const sectionAnswers = (answers || {})[skill] || {};
      let sectionPoints = 0;
      (section.tasks || []).forEach((task) => {
        const taskAnswers = sectionAnswers[task.task_key] || {};
        const scoringMode = task.scoring_mode || "objective";
        let taskPoints = 0;
        (task.questions || []).forEach((q) => {
          const num = q.number;
          const submitted = taskAnswers[num] != null ? taskAnswers[num] : taskAnswers[String(num)];
          const kind = q.kind || "";
          if (scoringMode === "subjective" || kind === "subjective" || kind === "subjective_sentence") {
            out.items.push({
              section: skill,
              task: task.task_key,
              question: num,
              kind: kind,
              correct: null,
              points_max: 1,
              awarded: null,
              subjective_pending: true,
            });
            return;
          }
          const correct = correctSet(q);
          const isCorrect =
            correct.length > 0 && normaliseAnswer(submitted) !== "" &&
            correct.indexOf(normaliseAnswer(submitted)) >= 0;
          const awarded = isCorrect ? 1 : 0;
          taskPoints += awarded;
          out.items.push({
            section: skill,
            task: task.task_key,
            question: num,
            kind: kind,
            correct: isCorrect,
            points_max: 1,
            awarded: awarded,
          });
        });
        if (scoringMode === "subjective") {
          // No subjective awards on the client — record pending capacity.
          if (skill === "language") {
            out.subjective_pending_language += Number(task.points_max || 0);
          }
        }
        sectionPoints += taskPoints;
      });
      const sectionMax = Number(section.points_max || 0);
      if (sectionMax > 0 && sectionPoints > sectionMax) {
        sectionPoints = sectionMax;
      }
      if (skill === "history") out.history = sectionPoints;
      else if (skill === "constitution") out.constitution = sectionPoints;
      else if (skill === "language") out.language = sectionPoints;
    });

    out.history_constitution_combined = out.history + out.constitution;
    out.total = out.history + out.constitution + out.language;
    out.history_constitution_passed =
      out.history_constitution_combined >= out.minimum_history_constitution;
    out.language_passed = out.language >= out.minimum_language;
    out.passed = out.history_constitution_passed && out.language_passed;
    if (out.passed) {
      out.failure_reason = null;
    } else if (!out.history_constitution_passed && !out.language_passed) {
      out.failure_reason = "both_sections_below_minimum";
    } else if (!out.history_constitution_passed) {
      out.failure_reason = "history_constitution_below_minimum";
    } else {
      out.failure_reason = "language_below_minimum";
    }
    return out;
  }

  function renderResult(score) {
    const container = $("nat-result");
    const passed = !!score.passed;
    const statusLabel = passed ? "EKSĀMENS NOKĀRTOTS" : "EKSĀMENS NAV NOKĀRTOTS";
    const reasonText = {
      both_sections_below_minimum:
        "Abas sekcijas zem minimālā sliekšņa (vēsture+Satversme un valoda).",
      history_constitution_below_minimum:
        "Vēsture + Satversme kopā zem minimālā sliekšņa (vajag vismaz " +
        score.minimum_history_constitution +
        "/20).",
      language_below_minimum:
        "Valodas daļa zem minimālā sliekšņa (vajag vismaz " +
        score.minimum_language +
        "/15).",
    };
    const reason = !passed && score.failure_reason
      ? `<p class="text-danger">${escapeHtml(reasonText[score.failure_reason] || score.failure_reason)}</p>`
      : "";

    const subjectiveNote = score.subjective_pending_language > 0
      ? `<p class="text-muted small">Piezīme: rakstīšanas uzdevums (līdz ${escapeHtml(score.subjective_pending_language)} punkti) gaida manuālu / AI vērtējumu un nav iekļauts šajā automātiskajā novērtējumā.</p>`
      : "";

    const hcRowClass = score.history_constitution_passed ? "pass-row" : "fail-row";
    const langRowClass = score.language_passed ? "pass-row" : "fail-row";

    container.innerHTML = `
      <div class="nat-result-card ${passed ? "pass" : "fail"}">
        <div class="nat-result-status ${passed ? "pass" : "fail"}">${escapeHtml(statusLabel)}</div>
        <hr>
        <div class="nat-score-row ${hcRowClass}">
          <span>Vēsture + Satversme (kopā)</span>
          <span>${escapeHtml(score.history_constitution_combined)} / 20 &nbsp;
            <small>(min. ${escapeHtml(score.minimum_history_constitution)})</small>
          </span>
        </div>
        <div class="nat-score-row">
          <span class="text-muted">&nbsp;&nbsp;Vēsture</span>
          <span>${escapeHtml(score.history)} / 10</span>
        </div>
        <div class="nat-score-row">
          <span class="text-muted">&nbsp;&nbsp;Satversme</span>
          <span>${escapeHtml(score.constitution)} / 10</span>
        </div>
        <div class="nat-score-row ${langRowClass}">
          <span>Latviešu valoda</span>
          <span>${escapeHtml(score.language)} / 15 &nbsp;
            <small>(min. ${escapeHtml(score.minimum_language)})</small>
          </span>
        </div>
        <div class="nat-score-row">
          <span><strong>Kopā</strong></span>
          <span><strong>${escapeHtml(score.total)} / 35</strong></span>
        </div>
        ${reason}
        ${subjectiveNote}
        <div class="text-center mt-3">
          <button type="button" class="btn btn-outline-secondary" id="nat-retake">Mēģināt vēlreiz</button>
        </div>
      </div>
    `;
    container.style.display = "";
    container.scrollIntoView({ behavior: "smooth", block: "start" });
    const retake = $("nat-retake");
    if (retake) {
      retake.addEventListener("click", () => {
        $("nat-result").style.display = "none";
        $("nat-result").innerHTML = "";
        $("nat-exam-form").reset();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  function attachSubmit() {
    const form = $("nat-exam-form");
    if (!form) return;
    form.addEventListener("submit", (evt) => {
      evt.preventDefault();
      const answers = collectAnswers();
      const score = scoreCitizenshipAttempt(answers);
      renderResult(score);
    });
  }

  function showError(msg) {
    const loading = $("nat-loading");
    if (loading) {
      loading.innerHTML =
        '<p class="text-danger">Neizdevās ielādēt eksāmenu: ' +
        escapeHtml(msg) +
        "</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    fetchManifest()
      .then((m) => {
        manifest = m;
        if (!manifest || manifest.level !== "CITIZENSHIP") {
          throw new Error(
            "Manifest level is not CITIZENSHIP (got " +
              (manifest && manifest.level) +
              ")"
          );
        }
        renderAll();
        attachSubmit();
      })
      .catch((err) => {
        showError(err && err.message ? err.message : String(err));
      });
  });

  // Expose for tests + console debugging.
  if (typeof window !== "undefined") {
    window.NATExam = {
      scoreCitizenshipAttempt,
      collectAnswers,
      DEFAULT_MIN_HISTORY_CONSTITUTION,
      DEFAULT_MIN_LANGUAGE,
    };
  }
})();

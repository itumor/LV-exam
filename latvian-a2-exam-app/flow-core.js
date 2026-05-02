/* eslint-disable no-var */
(function (global) {
  "use strict";

  function clone(value) {
    return value == null ? value : JSON.parse(JSON.stringify(value));
  }

  function createTimerState(totalSeconds) {
    const total = Math.max(0, Number(totalSeconds) || 0);
    return {
      total,
      remaining: total,
      running: false,
      startedAt: null,
      endsAt: null,
      pausedAt: null,
      completedAt: null,
      locked: false
    };
  }

  function calculateRemaining(timer, now) {
    const current = timer || createTimerState(0);
    if (!current.running || !current.endsAt) {
      return Math.max(0, Number(current.remaining) || 0);
    }
    const remaining = Math.ceil((Number(current.endsAt) - Number(now || Date.now())) / 1000);
    return Math.max(0, remaining);
  }

  function startTimer(timer, now) {
    const current = timer || createTimerState(0);
    const stamp = Number(now || Date.now());
    const remaining = Math.max(0, Number(current.remaining) || 0);
    current.running = remaining > 0 && !current.locked;
    current.startedAt = current.startedAt || stamp;
    current.pausedAt = null;
    current.completedAt = null;
    current.endsAt = current.running ? stamp + (remaining * 1000) : null;
    current.remaining = remaining;
    return current;
  }

  function pauseTimer(timer, now) {
    const current = timer || createTimerState(0);
    current.remaining = calculateRemaining(current, now);
    current.running = false;
    current.pausedAt = Number(now || Date.now());
    current.endsAt = null;
    return current;
  }

  function resetTimer(timer, totalSeconds) {
    const current = timer || createTimerState(totalSeconds);
    const total = Math.max(0, Number(totalSeconds ?? current.total) || 0);
    current.total = total;
    current.remaining = total;
    current.running = false;
    current.startedAt = null;
    current.endsAt = null;
    current.pausedAt = null;
    current.completedAt = null;
    current.locked = false;
    return current;
  }

  function tickTimer(timer, now) {
    const current = timer || createTimerState(0);
    const previous = Math.max(0, Number(current.remaining) || 0);
    const remaining = calculateRemaining(current, now);
    const expired = Boolean(current.running && previous > 0 && remaining === 0);
    current.remaining = remaining;
    if (expired) {
      current.running = false;
      current.completedAt = Number(now || Date.now());
      current.endsAt = null;
    }
    return { expired, remaining };
  }

  function getSkillScore(submission, evaluation, skillKey) {
    const fallbackBySkill = submission?.scoring?.by_skill?.[skillKey] || {};
    const evaluated = evaluation?.scores?.[skillKey] || {};
    const points = Number.isFinite(Number(evaluated.points))
      ? Number(evaluated.points)
      : Math.min(15, Math.max(0, Number(fallbackBySkill.objective_correct || 0)));
    const possible = Number.isFinite(Number(evaluated.max_points))
      ? Number(evaluated.max_points)
      : 15;
    const passed = Boolean(Number.isFinite(Number(evaluated.points)) ? evaluated.passed : points >= 9);
    return {
      key: skillKey,
      title: {
        listening: "Klausīšanās",
        reading: "Lasīšana",
        writing: "Rakstīšana",
        speaking: "Runāšana"
      }[skillKey] || skillKey,
      points,
      possible,
      passed,
      reason: String(evaluated.reason || ""),
      objective_correct: Number(fallbackBySkill.objective_correct || 0),
      objective_possible: Number(fallbackBySkill.objective_possible || 0)
    };
  }

  function deriveRecommendations(skills, evaluation) {
    const feedbackItems = Array.isArray(evaluation?.feedback?.improvements) ? evaluation.feedback.improvements : [];
    const nextPractice = Array.isArray(evaluation?.feedback?.next_practice) ? evaluation.feedback.next_practice : [];
    if (nextPractice.length) {
      return nextPractice.slice(0, 5);
    }
    if (feedbackItems.length) {
      return feedbackItems.slice(0, 5);
    }
    const weakSkills = skills.filter(skill => skill.points < 9).map(skill => skill.title);
    if (weakSkills.length) {
      return [
        `Review ${weakSkills.join(", ").toLowerCase()} with one shorter practice round.`,
        "Re-listen or re-read the full task instructions before answering.",
        "Check writing and speaking answers for clear A2-level vocabulary and grammar."
      ];
    }
    return [
      "Take one timed practice run to confirm section pacing.",
      "Revisit any corrections and rewrite those answers once more.",
      "Keep a short speaking recording for comparison before the next attempt."
    ];
  }

  function buildCandidateReportModel({ submission, evaluation, candidate } = {}) {
    const safeSubmission = submission || {};
    const safeEvaluation = evaluation || {};
    const skills = ["listening", "reading", "writing", "speaking"].map(skillKey => getSkillScore(safeSubmission, safeEvaluation, skillKey));
    const total = Number.isFinite(Number(safeEvaluation?.scores?.total))
      ? Number(safeEvaluation.scores.total)
      : skills.reduce((sum, skill) => sum + skill.points, 0);
    const passed = Boolean(Number.isFinite(Number(safeEvaluation?.scores?.passed))
      ? safeEvaluation.scores.passed
      : skills.every(skill => skill.passed));

    return {
      generated_at: new Date().toISOString(),
      exam_title: safeSubmission.exam_title || "Latvian A2 Exam",
      exam_id: safeSubmission.exam_id || "",
      candidate_name: [candidate?.firstName, candidate?.lastName].filter(Boolean).join(" ").trim() || "Candidate",
      candidate_code: candidate?.code || safeSubmission?.candidate?.code || "",
      submission_id: safeSubmission.submission_id || "",
      level: safeSubmission.level || "A2",
      language: safeSubmission.language || "lv",
      total_points: total,
      total_possible: 60,
      passed,
      disclaimer: "Practice estimate only. This simulator is unofficial and does not produce an official examination result.",
      skills,
      corrections: Array.isArray(safeEvaluation?.corrections) ? clone(safeEvaluation.corrections).slice(0, 12) : [],
      summary: safeEvaluation?.feedback?.summary || "Keep practicing the weaker skills and review the corrected items before retaking the exam.",
      strengths: Array.isArray(safeEvaluation?.feedback?.strengths) ? clone(safeEvaluation.feedback.strengths).slice(0, 5) : [],
      improvements: Array.isArray(safeEvaluation?.feedback?.improvements) ? clone(safeEvaluation.feedback.improvements).slice(0, 5) : [],
      next_practice: deriveRecommendations(skills, safeEvaluation)
    };
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function buildCandidateReportHtml(model) {
    const safe = model || buildCandidateReportModel();
    const skillRows = safe.skills.map(skill => `
      <article class="report-skill-card ${skill.passed ? "passed" : "failed"}">
        <h4>${escapeHtml(skill.title)}</h4>
        <strong>${escapeHtml(skill.points)}/${escapeHtml(skill.possible)}</strong>
        <span>${skill.passed ? "Pass" : "Needs work"}</span>
        <p>${escapeHtml(skill.reason || "")}</p>
      </article>
    `).join("");
    const corrections = safe.corrections.length ? `
      <section class="report-block">
        <h3>Corrections</h3>
        <div class="report-corrections">
          ${safe.corrections.map(item => `
            <article class="report-correction">
              <strong>${escapeHtml(item.skill || "")} ${escapeHtml(item.task || "")}${item.item ? ` #${escapeHtml(item.item)}` : ""}</strong>
              <p><span>Your answer:</span> ${escapeHtml(item.candidate_answer || item.actual || "")}</p>
              <p><span>Suggested:</span> ${escapeHtml(item.suggested_answer || item.expected || "")}</p>
              <p>${escapeHtml(item.comment || "")}</p>
            </article>
          `).join("")}
        </div>
      </section>
    ` : "";
    return `
      <section class="candidate-report-print">
        <header class="report-hero">
          <div>
            <p class="eyebrow">Candidate report</p>
            <h1>${escapeHtml(safe.exam_title)}</h1>
            <p>${escapeHtml(safe.candidate_name)}${safe.candidate_code ? ` · ${escapeHtml(safe.candidate_code)}` : ""}</p>
          </div>
          <div class="report-score-pill">${escapeHtml(safe.total_points)}/60</div>
        </header>
        <section class="report-block">
          <h3>Result</h3>
          <p class="report-result ${safe.passed ? "passed" : "failed"}">${safe.passed ? "Pass" : "Not yet passed"} - ${escapeHtml(safe.total_points)}/60 points</p>
          <p>${escapeHtml(safe.summary)}</p>
        </section>
        <section class="report-skills">
          ${skillRows}
        </section>
        ${corrections}
        <section class="report-block">
          <h3>Next practice</h3>
          <ul>${safe.next_practice.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </section>
        <section class="report-block">
          <h3>Disclaimer</h3>
          <p>${escapeHtml(safe.disclaimer)}</p>
        </section>
      </section>
    `;
  }

  const api = {
    clone,
    createTimerState,
    calculateRemaining,
    startTimer,
    pauseTimer,
    resetTimer,
    tickTimer,
    buildCandidateReportModel,
    buildCandidateReportHtml
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }

  global.LatvianA2FlowCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window);

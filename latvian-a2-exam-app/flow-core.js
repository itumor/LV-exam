/* eslint-disable no-undef */
(function (global) {
  const PART_ORDER = ["listening", "reading", "writing", "speaking"];
  const FLOW_STEPS = [
    { key: "welcome", label: "Welcome" },
    { key: "candidate", label: "Candidate details" },
    { key: "instructions", label: "Instructions" },
    { key: "listening", label: "Listening" },
    { key: "reading", label: "Reading" },
    { key: "writing", label: "Writing" },
    { key: "speaking", label: "Speaking" },
    { key: "results", label: "Results" }
  ];
  const DEFAULT_SKILL_LABELS = {
    listening: "Listening",
    reading: "Reading",
    writing: "Writing",
    speaking: "Speaking"
  };

  function createFlowState(overrides = {}) {
    return {
      screen: "welcome",
      mode: "exam",
      debugMode: false,
      candidate: { code: "", firstName: "", lastName: "" },
      ...overrides
    };
  }

  function shouldShowDebugPanels(debugMode) {
    return Boolean(debugMode);
  }

  function sanitizeSubmissionForLearner(submission) {
    if (!submission) return null;
    const clone = JSON.parse(JSON.stringify(submission));
    delete clone.answer_key;
    delete clone.validation_queue;
    if (clone.scoring && Array.isArray(clone.scoring.items)) {
      clone.scoring.items = clone.scoring.items.map(item => ({
        skill: item.skill,
        task: item.task,
        item: item.item,
        correct: item.correct
      }));
    }
    return clone;
  }

  function clampScore(value, min, max) {
    return Math.min(max, Math.max(min, Number(value) || 0));
  }

  function estimateSkillPoints(score = {}) {
    if (typeof score.points === "number") return clampScore(score.points, 0, 15);
    const correct = Number(score.objective_correct || 0);
    const possible = Math.max(1, Number(score.objective_possible || 0));
    return clampScore(Math.round((correct / possible) * 15), 0, 15);
  }

  function buildResultsSummary({ submission, evaluation, partConfig = [], skillLabels = DEFAULT_SKILL_LABELS }) {
    const evaluationScores = evaluation?.evaluation?.scores || {};
    const scores = partConfig.map(part => {
      const rawScore = evaluationScores[part.key];
      const points = rawScore && typeof rawScore.points === "number"
        ? clampScore(rawScore.points, 0, 15)
        : estimateSkillPoints(submission?.scoring?.by_skill?.[part.key]);
      const passed = rawScore && typeof rawScore.passed === "boolean" ? rawScore.passed : points >= 9;
      return {
        key: part.key,
        label: skillLabels[part.key] || part.title || part.key,
        points,
        possible: 15,
        passed,
        reason: rawScore?.reason || ""
      };
    });
    const total = scores.reduce((sum, item) => sum + item.points, 0);
    const weakAreas = scores.filter(item => item.points < 9).map(item => item.label);
    const nextPractice = [...scores].sort((a, b) => a.points - b.points).slice(0, 2).map(item => item.label);
    return {
      total,
      totalMax: 60,
      passed: scores.every(item => item.passed),
      scores,
      weakAreas,
      nextPractice
    };
  }

  function switchFlowMode(flowState, nextMode) {
    return { ...flowState, mode: nextMode === "practice" ? "practice" : "exam" };
  }

  function getNextPart(partKey, partOrder = PART_ORDER) {
    const index = partOrder.indexOf(partKey);
    if (index === -1 || index >= partOrder.length - 1) return null;
    return partOrder[index + 1];
  }

  function advanceExamOnTimer(flowState, runnerState, partOrder = PART_ORDER) {
    const currentPart = runnerState.activePart || partOrder[0];
    const nextPart = getNextPart(currentPart, partOrder);
    if (flowState.mode !== "exam") {
      return { flow: flowState, runner: runnerState, action: "stay" };
    }
    if (nextPart) {
      return {
        flow: flowState,
        runner: {
          ...runnerState,
          activePart: nextPart,
          timers: {
            ...runnerState.timers,
            [nextPart]: { ...runnerState.timers[nextPart], running: true }
          }
        },
        action: "advance",
        nextPart
      };
    }
    return {
      flow: { ...flowState, screen: "results" },
      runner: {
        ...runnerState,
        timers: Object.fromEntries(Object.entries(runnerState.timers || {}).map(([key, timer]) => [key, { ...timer, running: false }]))
      },
      action: "submit"
    };
  }

  function canSwitchPart(mode, currentPart, nextPart, partOrder = PART_ORDER) {
    if (mode === "practice") return true;
    if (currentPart === nextPart) return true;
    const currentIndex = partOrder.indexOf(currentPart);
    const nextIndex = partOrder.indexOf(nextPart);
    return currentIndex !== -1 && nextIndex === currentIndex + 1;
  }

  // --- Wall-clock timer helpers ---

  function createTimerState(totalSeconds) {
    return { total: totalSeconds, remaining: totalSeconds, running: false, startedAt: null };
  }

  function startTimer(timer, nowMs) {
    timer.startedAt = nowMs;
    timer.running = true;
  }

  function calculateRemaining(timer, nowMs) {
    if (!timer.running || timer.startedAt == null) return timer.remaining;
    const elapsed = Math.floor((nowMs - timer.startedAt) / 1000);
    return Math.max(0, timer.total - elapsed);
  }

  function tickTimer(timer, nowMs) {
    const remaining = calculateRemaining(timer, nowMs);
    timer.remaining = remaining;
    if (remaining === 0) {
      timer.running = false;
    }
    return { expired: remaining === 0 };
  }

  function resetTimer(timer, totalSeconds) {
    timer.total = totalSeconds;
    timer.remaining = totalSeconds;
    timer.running = false;
    timer.startedAt = null;
  }

  // --- Candidate report builders ---

  const SKILL_LABELS_LV = {
    listening: "Klausīšanās",
    reading: "Lasīšana",
    writing: "Rakstīšana",
    speaking: "Runāšana"
  };

  function buildCandidateReportModel({ submission, evaluation, candidate = {} }) {
    const evalScores = (evaluation && evaluation.scores) ? evaluation.scores : {};
    const evalFeedback = (evaluation && evaluation.feedback) ? evaluation.feedback : {};
    const corrections = (evaluation && Array.isArray(evaluation.corrections)) ? evaluation.corrections : [];

    const totalPoints = typeof evalScores.total === "number" ? evalScores.total : 0;
    const passed = typeof evalScores.passed === "boolean" ? evalScores.passed : totalPoints >= 36;

    const skillRows = ["listening", "reading", "writing", "speaking"].map(key => {
      const s = evalScores[key] || {};
      return {
        key,
        label: SKILL_LABELS_LV[key] || key,
        points: typeof s.points === "number" ? s.points : 0,
        max_points: typeof s.max_points === "number" ? s.max_points : 15,
        passed: typeof s.passed === "boolean" ? s.passed : false,
        reason: s.reason || ""
      };
    });

    const summaryText = evalFeedback.summary || "";
    const disclaimer = "Practice estimate only — not an official exam result. Results produced by this simulator are for preparation purposes and carry no legal or academic weight.";

    return {
      submission_id: submission && submission.submission_id ? submission.submission_id : "",
      exam_title: submission && submission.exam_title ? submission.exam_title : "",
      candidate: { firstName: candidate.firstName || "", lastName: candidate.lastName || "", code: candidate.code || "" },
      total_points: totalPoints,
      total_max: 60,
      passed,
      skills: skillRows,
      corrections,
      feedback: {
        summary: summaryText,
        strengths: evalFeedback.strengths || [],
        improvements: evalFeedback.improvements || [],
        next_practice: evalFeedback.next_practice || []
      },
      disclaimer,
      generated_at: new Date().toISOString()
    };
  }

  function buildCandidateReportHtml(report) {
    const skillRows = (report.skills || []).map(s => `
      <tr>
        <td>${s.label}</td>
        <td>${s.points} / ${s.max_points}</td>
        <td class="${s.passed ? "pass" : "fail"}">${s.passed ? "Nokārtots" : "Nav nokārtots"}</td>
        <td>${s.reason || ""}</td>
      </tr>
    `).join("");

    const correctionsHtml = (report.corrections || []).length
      ? `<section class="report-corrections">
          <h3>Labojumi</h3>
          <ul>${(report.corrections).map(c => `<li><strong>${c.skill || ""}/${c.task || ""}</strong>: ${c.comment || ""}</li>`).join("")}</ul>
        </section>`
      : "";

    const strengths = (report.feedback && report.feedback.strengths || []).join(", ");
    const improvements = (report.feedback && report.feedback.improvements || []).join(", ");
    const nextPractice = (report.feedback && report.feedback.next_practice || []).join(", ");

    return `
      <article class="candidate-report">
        <header>
          <h1>Candidate report</h1>
          <p>${report.exam_title || ""}</p>
          <p>Kandidāts: ${report.candidate.firstName} ${report.candidate.lastName} (${report.candidate.code})</p>
        </header>
        <section class="report-scores">
          <h2>Kopējais rezultāts: ${report.total_points} / ${report.total_max}</h2>
          <p class="${report.passed ? "pass" : "fail"}">${report.passed ? "Nokārtots" : "Nav nokārtots"}</p>
          <table>
            <thead><tr><th>Prasme</th><th>Punkti</th><th>Statuss</th><th>Komentārs</th></tr></thead>
            <tbody>${skillRows}</tbody>
          </table>
        </section>
        ${correctionsHtml}
        <section class="report-feedback">
          ${strengths ? `<p><strong>Stiprās puses:</strong> ${strengths}</p>` : ""}
          ${improvements ? `<p><strong>Uzlabojumi:</strong> ${improvements}</p>` : ""}
          ${nextPractice ? `<p><strong>Ieteicamā prakse:</strong> ${nextPractice}</p>` : ""}
          ${report.feedback && report.feedback.summary ? `<p>${report.feedback.summary}</p>` : ""}
        </section>
        <footer class="report-disclaimer">
          <p>${report.disclaimer}</p>
        </footer>
      </article>
    `;
  }

  const api = {
    PART_ORDER,
    FLOW_STEPS,
    createFlowState,
    shouldShowDebugPanels,
    sanitizeSubmissionForLearner,
    buildResultsSummary,
    switchFlowMode,
    getNextPart,
    advanceExamOnTimer,
    canSwitchPart,
    estimateSkillPoints,
    createTimerState,
    startTimer,
    calculateRemaining,
    tickTimer,
    resetTimer,
    buildCandidateReportModel,
    buildCandidateReportHtml
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.ExamFlowCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window);

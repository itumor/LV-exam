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
      candidate: {
        code: "",
        firstName: "",
        lastName: ""
      },
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
    if (clone.scoring && clone.scoring.items) {
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
    if (!score) return 0;
    if (typeof score.points === "number") {
      return clampScore(score.points, 0, 15);
    }
    const correct = Number(score.objective_correct || 0);
    const possible = Math.max(1, Number(score.objective_possible || 0));
    return clampScore(Math.round((correct / possible) * 15), 0, 15);
  }

  function buildResultsSummary({ submission, evaluation, partConfig = [], skillLabels = DEFAULT_SKILL_LABELS }) {
    const evaluationScores = evaluation?.evaluation?.scores || {};
    const resolvedScores = partConfig.map(part => {
      const rawScore = evaluationScores[part.key];
      const points = rawScore && typeof rawScore.points === "number"
        ? clampScore(rawScore.points, 0, 15)
        : estimateSkillPoints(submission?.scoring?.by_skill?.[part.key]);
      const passed = rawScore && typeof rawScore.passed === "boolean"
        ? rawScore.passed
        : points >= 9;
      return {
        key: part.key,
        label: skillLabels[part.key] || part.title || part.key,
        points,
        possible: 15,
        passed,
        reason: rawScore?.reason || ""
      };
    });

    const total = resolvedScores.reduce((sum, item) => sum + item.points, 0);
    const weakAreas = resolvedScores
      .filter(item => item.points < 9)
      .map(item => item.label);
    const sortedByNeed = [...resolvedScores].sort((a, b) => a.points - b.points);
    const nextPractice = sortedByNeed.slice(0, 2).map(item => item.label);

    return {
      total,
      totalMax: 60,
      passed: resolvedScores.every(item => item.passed),
      scores: resolvedScores,
      weakAreas,
      nextPractice
    };
  }

  function switchFlowMode(flowState, nextMode) {
    const mode = nextMode === "practice" ? "practice" : "exam";
    return {
      ...flowState,
      mode
    };
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
      return {
        flow: flowState,
        runner: runnerState,
        action: "stay"
      };
    }

    if (nextPart) {
      return {
        flow: flowState,
        runner: {
          ...runnerState,
          activePart: nextPart,
          timers: {
            ...runnerState.timers,
            [nextPart]: {
              ...runnerState.timers[nextPart],
              running: true
            }
          }
        },
        action: "advance",
        nextPart
      };
    }

    return {
      flow: {
        ...flowState,
        screen: "results"
      },
      runner: {
        ...runnerState,
        timers: Object.fromEntries(
          Object.entries(runnerState.timers || {}).map(([key, timer]) => [
            key,
            { ...timer, running: false }
          ])
        )
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
    estimateSkillPoints
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.ExamFlowCore = api;
})(typeof globalThis !== "undefined" ? globalThis : window);

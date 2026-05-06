const test = require("node:test");
const assert = require("node:assert/strict");

const flowCore = require("../latvian-a2-exam-app/flow-core.js");

const PART_CONFIG = [
  { key: "listening", title: "Klausīšanās" },
  { key: "reading", title: "Lasīšana" },
  { key: "writing", title: "Rakstīšana" },
  { key: "speaking", title: "Runāšana" }
];

test("exam part order follows official section sequence", () => {
  assert.deepEqual(flowCore.PART_ORDER, ["listening", "reading", "writing", "speaking"]);
});

test("mode switching keeps practice and exam states separate", () => {
  const practice = flowCore.switchFlowMode(flowCore.createFlowState(), "practice");
  assert.equal(practice.mode, "practice");

  const exam = flowCore.switchFlowMode(practice, "exam");
  assert.equal(exam.mode, "exam");
});

test("timer expiry advances in exam mode and submits on the final section", () => {
  const baseRunner = {
    activePart: "listening",
    timers: {
      listening: { remaining: 0, running: false },
      reading: { remaining: 1800, running: false },
      writing: { remaining: 2100, running: false },
      speaking: { remaining: 900, running: false }
    }
  };

  const advanced = flowCore.advanceExamOnTimer(
    flowCore.createFlowState({ mode: "exam" }),
    baseRunner
  );
  assert.equal(advanced.action, "advance");
  assert.equal(advanced.runner.activePart, "reading");
  assert.equal(advanced.runner.timers.reading.running, true);

  const finalAdvance = flowCore.advanceExamOnTimer(
    flowCore.createFlowState({ mode: "exam" }),
    {
      activePart: "speaking",
      timers: {
        listening: { remaining: 0, running: false },
        reading: { remaining: 0, running: false },
        writing: { remaining: 0, running: false },
        speaking: { remaining: 0, running: false }
      }
    }
  );
  assert.equal(finalAdvance.action, "submit");
  assert.equal(finalAdvance.flow.screen, "results");
});

test("practice mode allows direct section switching while exam mode stays locked", () => {
  assert.equal(flowCore.canSwitchPart("practice", "listening", "speaking"), true);
  assert.equal(flowCore.canSwitchPart("exam", "listening", "speaking"), false);
  assert.equal(flowCore.canSwitchPart("exam", "listening", "reading"), true);
});

test("results summary returns total, weak areas, and practice suggestions", () => {
  const submission = {
    scoring: {
      by_skill: {
        listening: { objective_correct: 2, objective_possible: 6 },
        reading: { objective_correct: 5, objective_possible: 6 },
        writing: { objective_correct: 1, objective_possible: 4 },
        speaking: { objective_correct: 3, objective_possible: 5 }
      }
    }
  };

  const summary = flowCore.buildResultsSummary({
    submission,
    evaluation: null,
    partConfig: PART_CONFIG
  });

  assert.equal(summary.totalMax, 60);
  assert.equal(summary.scores.length, 4);
  assert(summary.total > 0);
  assert(summary.weakAreas.includes("Listening"));
  assert(summary.nextPractice.length > 0);
});

test("learner submission view redacts answer keys and validation queues", () => {
  const sanitized = flowCore.sanitizeSubmissionForLearner({
    answer_key: { listening: { task1: ["a"] } },
    validation_queue: [{ skill: "listening" }],
    scoring: {
      items: [
        { skill: "listening", task: "task1", item: 1, correct: true, expected: "a", actual: "b" }
      ]
    }
  });

  assert.equal("answer_key" in sanitized, false);
  assert.equal("validation_queue" in sanitized, false);
  assert.deepEqual(sanitized.scoring.items, [
    { skill: "listening", task: "task1", item: 1, correct: true }
  ]);
});

test("debug panels stay hidden unless explicitly enabled", () => {
  assert.equal(flowCore.shouldShowDebugPanels(false), false);
  assert.equal(flowCore.shouldShowDebugPanels(true), true);
});

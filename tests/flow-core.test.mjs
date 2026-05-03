import assert from "node:assert/strict";
import test from "node:test";

import core from "../latvian-a2-exam-app/flow-core.js";

test("timer helpers are deterministic and expire cleanly", () => {
  const timer = core.createTimerState(60);
  core.startTimer(timer, 1_000_000);

  assert.equal(core.calculateRemaining(timer, 1_015_000), 45);

  const tick = core.tickTimer(timer, 1_061_000);
  assert.equal(tick.expired, true);
  assert.equal(timer.running, false);
  assert.equal(timer.remaining, 0);

  core.resetTimer(timer, 90);
  assert.equal(timer.total, 90);
  assert.equal(timer.remaining, 90);
  assert.equal(timer.running, false);
});

test("candidate report includes disclaimers and corrections", () => {
  const submission = {
    submission_id: "a2-01-123",
    exam_title: "A2 Mock Exam 01",
    exam_id: "a2_mock_exam_01",
    scoring: {
      by_skill: {
        listening: { objective_correct: 7, objective_possible: 10 },
        reading: { objective_correct: 5, objective_possible: 8 },
        writing: { objective_correct: 3, objective_possible: 6 },
        speaking: { objective_correct: 4, objective_possible: 5 }
      }
    }
  };

  const evaluation = {
    scores: {
      listening: { points: 12, max_points: 15, passed: true, reason: "Strong comprehension." },
      reading: { points: 11, max_points: 15, passed: true, reason: "Good reading control." },
      writing: { points: 8, max_points: 15, passed: false, reason: "Needs grammar review." },
      speaking: { points: 10, max_points: 15, passed: true, reason: "Clear but brief." },
      total: 41,
      passed: false
    },
    corrections: [
      {
        skill: "writing",
        task: "task3",
        item: 1,
        candidate_answer: "Es rakstu.",
        suggested_answer: "Es rakstu vēstuli.",
        comment: "Add a little more detail."
      }
    ],
    feedback: {
      summary: "Practice estimate only.",
      strengths: ["Clear answers"],
      improvements: ["Expand writing responses"],
      next_practice: ["Repeat a timed speaking set"]
    }
  };

  const report = core.buildCandidateReportModel({
    submission,
    evaluation,
    candidate: { firstName: "Anna", lastName: "Liepa", code: "A123" }
  });
  const html = core.buildCandidateReportHtml(report);

  assert.equal(report.total_points, 41);
  assert.equal(report.passed, false);
  assert.match(report.disclaimer, /Practice estimate/);
  assert.equal(report.corrections.length, 1);
  assert.match(html, /Candidate report/);
  assert.match(html, /Practice estimate only/);
  assert.match(html, /Rakstīšana/);
});

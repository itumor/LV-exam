const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const fixturesDir = path.join(__dirname, "..", "fixtures");
const readJson = name => JSON.parse(fs.readFileSync(path.join(fixturesDir, name), "utf8"));

async function enterExamFlow(page) {
  await page.goto("/latvian-a2-exam-app/");
  await expect(page.getByRole("heading", { name: "Valsts valodas prasmes pārbaude - A2 līmenis" })).toBeVisible();

  await page.getByRole("button", { name: "Sākt pilnu eksāmenu" }).click();
  await page.getByLabel("Kandidāta kods").fill("QA-001");
  await page.getByRole("textbox", { name: "Vārds", exact: true }).fill("Anna");
  await page.getByRole("textbox", { name: "Uzvārds", exact: true }).fill("Bērziņa");
  await page.getByRole("button", { name: "Sākt pārbaudi" }).click();

  await expect(page.getByRole("heading", { name: "Pārbaudes norādījumi" })).toBeVisible();
  await page.getByRole("button", { name: "Saprasts / Atpakaļ" }).click();
  await expect(page.locator('div.task-stack.official-task-stack[data-part="listening"]')).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__a2TestHooks && window.__a2TestHooks.setAnswer));
}

async function submitAndOpenAiScoring(page) {
  await page.locator('button[data-action="submit-exam"]').click();
  await expect(page.getByText("Submitted", { exact: true })).toBeVisible();

  await page.locator('button[data-submission-action="evaluate"]').click();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__A2_TEST_HOOKS__ = true;
  });
});

test("full learner journey reaches submission history and AI scoring", async ({ page }) => {
  const successPayload = readJson("ai-evaluation-success.json");

  await page.route("**/api/evaluate", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successPayload)
    })
  );

  await enterExamFlow(page);

  await page.evaluate(() => {
    window.__a2TestHooks.setAnswer("listening", "task1", 0, "a");
    window.__a2TestHooks.setAnswer("reading", "task1", 0, "b");
    window.__a2TestHooks.setAnswer("writing", "task3", 0, "Es gribu kafiju.");
    window.__a2TestHooks.setAnswer("speaking", "task1", 0, "Es dzīvoju Rīgā.");
  });

  await submitAndOpenAiScoring(page);
  await expect(page.getByText("AI score: 60/60")).toBeVisible();
  await expect(page.getByText("Pass rule met")).toBeVisible();
  await expect(page.locator(".ai-summary")).toHaveText("Fixture evaluation for the regression suite.");

  const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("latvian_a2_exam_submissions") || "[]"));
  expect(stored[0].status).toBe("submitted");
  expect(stored[0].ai_evaluation.evaluation.scores.total).toBe(60);
  expect(stored.some(entry => entry.status === "submitted" && entry.ai_evaluation?.evaluation?.scores?.total === 60)).toBe(true);
});

test("timer expiry zeros listening timer and advances the exam to reading", async ({ page }) => {
  await enterExamFlow(page);

  await page.evaluate(() => {
    window.__a2TestHooks.setTimerRemaining("listening", 1);
    window.__a2TestHooks.startTimer("listening");
  });

  await page.waitForFunction(() => {
    const state = window.__a2TestHooks && window.__a2TestHooks.getState();
    const timer = state && state.runner && state.runner.timers && state.runner.timers.listening;
    return Boolean(timer && timer.remaining === 0 && timer.running === false);
  });

  const snapshot = await page.evaluate(() => {
    const s = window.__a2TestHooks.getState();
    return {
      listening: s.runner.timers.listening,
      activePart: s.runner.activePart
    };
  });
  expect(snapshot.listening.remaining).toBe(0);
  expect(snapshot.listening.running).toBe(false);
  expect(snapshot.activePart).toBe("reading");

  await expect(page.getByRole("heading", { name: "Lasīšana / Reading" })).toBeVisible();
  await expect(page.locator('[data-timer="reading"]')).toBeVisible();
  await expect(page.locator('button[data-action="start"][data-part="reading"]')).toBeDisabled();
});

test("AI scoring shows quota errors, then succeeds on retry", async ({ page }) => {
  const successPayload = readJson("ai-evaluation-success.json");
  const quotaPayload = readJson("ai-evaluation-quota.json");
  let attempt = 0;

  await page.route("**/api/evaluate", route => {
    attempt += 1;
    if (attempt === 1) {
      route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify(quotaPayload)
      });
      return;
    }
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successPayload)
    });
  });

  await enterExamFlow(page);
  await submitAndOpenAiScoring(page);
  await expect(page.locator(".ai-evaluation-panel.error h3")).toHaveText("AI scoring failed");
  await expect(page.locator(".ai-evaluation-panel.error")).toContainText(/rate limit/i);

  await page.locator('button[data-submission-action="evaluate"]').click();
  await expect(page.getByText("AI score: 60/60")).toBeVisible();
  await expect(page.locator(".ai-summary")).toHaveText("Fixture evaluation for the regression suite.");
});

test("AI scoring rejects malformed success payloads", async ({ page }) => {
  const invalidPayload = readJson("ai-evaluation-invalid.json");

  await page.route("**/api/evaluate", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(invalidPayload)
    })
  );

  await enterExamFlow(page);
  await submitAndOpenAiScoring(page);

  await expect(page.locator(".ai-evaluation-panel.error h3")).toHaveText("AI scoring failed");
  await expect(page.locator(".ai-evaluation-panel.error")).toContainText(/invalid/i);
});

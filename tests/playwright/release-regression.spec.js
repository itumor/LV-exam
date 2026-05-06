const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

const fixturesDir = path.join(__dirname, "..", "fixtures");
const readJson = name => JSON.parse(fs.readFileSync(path.join(fixturesDir, name), "utf8"));

async function enterExamFlow(page) {
  await page.goto("/latvian-a2-exam-app/?screen=home");
  await expect(page.getByRole("heading", { name: "State Language Exam - Level A2" })).toBeVisible();

  await page.getByRole("button", { name: "Start Full Exam" }).click();
  await page.getByLabel("Candidate Code").fill("QA-001");
  await page.getByRole("textbox", { name: "First Name", exact: true }).fill("Anna");
  await page.getByRole("textbox", { name: "Last Name", exact: true }).fill("Bērziņa");
  await page.locator("[data-candidate-form] button[type='submit']").click();

  await expect(page.getByRole("heading", { name: "Pārbaudes norādījumi" })).toBeVisible();
  await page.getByRole("button", { name: "Saprasts / Atpakaļ" }).click();
  await expect(page.locator('div.task-stack.official-task-stack[data-part="listening"]')).toBeVisible();
  await page.waitForFunction(() => Boolean(window.__a2TestHooks && window.__a2TestHooks.setAnswer));
}

async function submitAndOpenAiScoring(page) {
  await page.locator('button[data-action="submit-exam"]').click();
  await expect(page.locator("#submission-output").getByText("Submitted", { exact: true })).toBeVisible();

  await page.locator('button[data-submission-action="evaluate"]').click();
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__A2_TEST_HOOKS__ = true;
  });
});

async function mockAuthenticatedShell(page) {
  const account = { id: "acct_mega_nav", email: "mega@example.com", role: "user" };
  const profile = { full_name: "Mega Nav QA", native_language: "en" };
  const summary = {
    attempts_remaining: 3,
    ai_credits_remaining: 2,
    attempts_taken: 1,
    latest_score: 54,
    subscription_status: "active",
    skill_progress: {}
  };

  await page.route("**/api/session", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: true, account, profile })
    })
  );
  await page.route("**/api/dashboard", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ authenticated: true, account, profile, summary, attempts: [] })
    })
  );
  await page.route("**/api/billing/config", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        products: [
          { key: "single_exam", name: "Single Exam", mode: "payment", grants_attempts: 1, grants_ai_credits: 0, price_id: "" },
          { key: "ai_credits", name: "AI Scoring Credits", mode: "payment", grants_attempts: 0, grants_ai_credits: 5, price_id: "" }
        ]
      })
    })
  );
  await page.route("**/api/billing/state**", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        learner_id: "acct_mega_nav",
        state: {
          current_plan: "active",
          free_exam_available: true,
          paid_attempts_remaining: 3,
          attempts_remaining: 3,
          ai_credits_remaining: 2,
          subscription_active: true,
          frozen: false,
          recent_events: []
        }
      })
    })
  );
}

test("mega dropdown opens, changes panels, supports keyboard close, and click-outside close", async ({ page }) => {
  await mockAuthenticatedShell(page);
  await page.goto("/latvian-a2-exam-app/");

  const trigger = page.locator("#mega-menu-trigger");
  const panel = page.locator("#mega-dropdown-panel");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");

  await trigger.click();
  await expect(panel).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");

  await page.getByRole("tab", { name: "Payments" }).hover();
  await expect(panel.getByRole("button", { name: "Purchase", exact: true })).toBeVisible();

  await page.getByRole("tab", { name: "My Account" }).click();
  await expect(panel.getByRole("button", { name: "My Progress" })).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
  await expect(trigger).toBeFocused();

  await trigger.click();
  await expect(panel).toBeVisible();
  await page.mouse.click(12, 760);
  await expect(panel).toBeHidden();

  await trigger.focus();
  await page.keyboard.press("ArrowDown");
  await expect(panel).toBeVisible();
  await expect(page.getByRole("tab", { name: "Exams" })).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "My Account" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();
});

test("mega dropdown navigates to help, billing, and exam runner destinations", async ({ page }) => {
  await mockAuthenticatedShell(page);
  await page.goto("/latvian-a2-exam-app/");
  const panel = page.locator("#mega-dropdown-panel");

  await page.locator("#mega-menu-trigger").click();
  await page.getByRole("tab", { name: "Help" }).click();
  await panel.getByRole("button", { name: "User Manual" }).click();
  await expect(page.locator("#workspace-title")).toHaveText("User Manual");

  await page.locator("#mega-menu-trigger").click();
  await page.getByRole("tab", { name: "Payments" }).click();
  await panel.getByRole("button", { name: "Purchase", exact: true }).click();
  await expect(page.locator("#workspace-title")).toHaveText("Billing");
  await expect(page.getByRole("heading", { name: "Purchase options" })).toBeVisible();

  await page.locator("#mega-menu-trigger").click();
  await page.getByRole("tab", { name: "Exams" }).click();
  await panel.getByRole("button", { name: "Exam Runner" }).click();
  await expect(page.locator("#workspace-title")).toHaveText("Exam Runner");
  await expect(page.locator("#runner-view")).toHaveClass(/active/);
});

test("header shortcuts replace the old sidebar navigation", async ({ page }) => {
  await page.goto("/latvian-a2-exam-app/");

  await expect(page.locator(".sidebar-menu")).toBeHidden();
  await expect(page.locator("#quick-start-exam")).toBeEnabled();

  await page.locator("#quick-start-exam").click();
  await expect(page.locator("#workspace-title")).toHaveText("Exam Runner");
  await expect(page.getByRole("heading", { name: "State Language Exam - Level A2" })).toBeVisible();

  await page.locator("#quick-status").click();
  await expect(page.locator("#workspace-title")).toHaveText("Billing");
  await expect(page.getByRole("heading", { name: "Current access" })).toBeVisible();

  await page.locator("#quick-buy").click();
  await expect(page.locator("#workspace-title")).toHaveText("Billing");
  await expect(page.getByRole("heading", { name: "Purchase options" })).toBeVisible();

  await page.locator("#quick-help").click();
  await expect(page.locator("#workspace-title")).toHaveText("User Manual");
  await expect(page.locator("#help-output")).toContainText(/Lietot|User Manual/i);
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

  await expect(page.getByRole("heading", { name: "Reading / Reading" })).toBeVisible();
  await expect(page.locator('[data-timer="reading"]')).toBeVisible();
  await expect(page.locator('button[data-action="start"][data-part="reading"]')).toBeDisabled();
});

test("reading task 2 keeps the A-L prompt and advertisement bank visible", async ({ page }) => {
  await page.goto("/latvian-a2-exam-app/?exam=01&part=reading&screen=exam");

  await expect(page.getByRole("heading", { name: "Reading / Reading" })).toBeVisible();
  await expect(page.getByText("Uzdevums 2 no 3: Atrodiet, kurš sludinājums (A–L) atbilst katrai situācijai")).toBeVisible();
  await expect(page.locator(".ad-reference-panel")).toHaveCount(0);
  await expect(page.locator(".ad-match-group")).toHaveCount(3);
  await expect(page.locator(".ad-match-group").first()).toContainText("Izīrē 3 istabu dzīvokli ģimenei pie 5. pamatskolas.");
  await expect(page.locator(".ad-match-group").nth(1)).toContainText("Veļas mazgātava “Tīrība” atvērta no 8.00 līdz 20.00.");
  await expect(page.locator(".ad-match-group").last()).toContainText("Bērnu drēbju maiņas tirdziņš svētdien sporta hallē.");
  await expect(page.locator('select[data-answer="reading.task2.0"] option')).toHaveCount(5);
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

test("speaking recorder shows Latvian speech text and syncs the answer", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        getUserMedia: async () => ({
          getTracks: () => [{ stop: () => {} }]
        })
      }
    });

    class MockMediaRecorder extends EventTarget {
      static isTypeSupported() { return true; }
      start() {}
      stop() { this.dispatchEvent(new Event("stop")); }
    }
    window.MediaRecorder = MockMediaRecorder;

    class MockSpeechRecognition {
      start() { window.__mockSpeechRecognition = this; }
      stop() {
        if (this.onend) this.onend();
      }
    }
    window.SpeechRecognition = MockSpeechRecognition;
  });

  await enterExamFlow(page);
  await page.evaluate(() => window.__a2TestHooks.setActivePart("speaking"));

  await page.locator('button[data-action="start-recording"]').first().click();
  await page.evaluate(() => {
    const result = [{ transcript: "Es dzīvoju Rīgā." }];
    result.isFinal = true;
    window.__mockSpeechRecognition.onresult({
      resultIndex: 0,
      results: [result]
    });
  });

  await expect(page.locator('[data-transcript-text="speaking.task1.0"]')).toHaveText("Es dzīvoju Rīgā.");
  await expect(page.locator('[data-answer="speaking.task1.0"]')).toHaveValue("Es dzīvoju Rīgā.");
});

test("admin has unlimited access and AI scoring without credits", async ({ page }) => {
  const successPayload = readJson("ai-evaluation-success.json");

  // Mock all required APIs
  await page.route("**/api/evaluate", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(successPayload)
    })
  );

  await page.route("**/api/session", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        account: { id: "acct_superadmin_seed", email: "superadmin@example.com", role: "superadmin" },
        learner_id: "acct_superadmin_seed"
      })
    })
  );

  await page.route("**/api/dashboard", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        authenticated: true,
        account: { id: "acct_superadmin_seed", email: "superadmin@example.com", role: "superadmin" },
        profile: { full_name: "Super Admin" },
        summary: {
          attempts_remaining: 999,
          ai_credits_remaining: 999,
          attempts_taken: 0,
          latest_score: null,
          subscription_status: "admin_unlimited",
          skill_progress: {}
        },
        attempts: []
      })
    })
  );

  await page.route("**/api/billing/config", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ products: [] })
    })
  );

  await page.route("**/api/billing/state*", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        learner_id: "acct_superadmin_seed",
        state: {
          current_plan: "admin_unlimited",
          paid_attempts_remaining: -1,
          ai_credits_remaining: -1,
          subscription_active: true
        }
      })
    })
  );

  await page.route("**/api/exams/catalog", route =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        exams: [{ id: "01", title: "A2 Mock Exam 01", status: "published" }]
      })
    })
  );

  await page.route("**/codex/A2_Mock_Exam_01.md", route =>
    route.fulfill({
      status: 200,
      contentType: "text/markdown",
      body: "# Mock Exam\n\n## Listening\n\nTask 1: ..."
    })
  );

  await page.goto("/latvian-a2-exam-app/?view=admin");
  await page.waitForLoadState("networkidle");

  await expect(page.locator("#workspace-title")).toHaveText("Admin Console", { timeout: 10000 });

  await enterExamFlow(page);
  await page.evaluate(() => {
    window.__a2TestHooks.setAnswer("listening", "task1", 0, "a");
    window.__a2TestHooks.setAnswer("reading", "task1", 0, "b");
    window.__a2TestHooks.setAnswer("writing", "task3", 0, "Es gribu kafiju.");
    window.__a2TestHooks.setAnswer("speaking", "task1", 0, "Es dzīvoju Rīgā.");
  });

  await submitAndOpenAiScoring(page);
  await expect(page.getByText("AI score: 60/60")).toBeVisible({ timeout: 10000 });
});

const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/playwright",
  fullyParallel: false,
  timeout: 60000,
  expect: {
    timeout: 10000
  },
  use: {
    baseURL: "http://localhost:4173/latvian-a2-exam-app/",
    trace: "on-first-retry"
  },
  webServer: {
    command: "python3 server.py",
    reuseExistingServer: true,
    timeout: 120000,
    url: "http://localhost:4173/latvian-a2-exam-app/",
    // T-015: disable the per-IP / per-session rate limiter ONLY for the E2E
    // run. Every Playwright worker shares 127.0.0.1, which trivially blows
    // through the production-default 60 req/min cap and produces spurious
    // 429s on the regression suite (notably the admin test, which sits last
    // in the spec order). Production deployments must leave this unset.
    env: {
      LVCODEX_RATE_LIMIT_DISABLE: "1"
    }
  }
});

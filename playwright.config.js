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
    url: "http://localhost:4173/latvian-a2-exam-app/"
  }
});

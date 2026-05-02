const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./tests/playwright",
  fullyParallel: false,
  timeout: 60000,
  expect: {
    timeout: 10000
  },
  use: {
    baseURL: "http://127.0.0.1:4273/latvian-a2-exam-app/",
    trace: "on-first-retry"
  },
  webServer: {
    command: "PORT=4273 python3 server.py",
    reuseExistingServer: false,
    timeout: 120000,
    url: "http://127.0.0.1:4273/latvian-a2-exam-app/"
  }
});

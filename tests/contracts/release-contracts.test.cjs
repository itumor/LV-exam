const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "..", "fixtures");
const readJson = name => JSON.parse(fs.readFileSync(path.join(root, name), "utf8"));

test("release checklist records the owner and reviewed date", () => {
  const checklist = fs.readFileSync(path.join(__dirname, "..", "..", "docs", "release-checklist.md"), "utf8");
  assert.match(checklist, /Owner: QA Release Agent/);
  assert.match(checklist, /Last reviewed: 2026-05-01/);
  assert.match(checklist, /no launch unless every must-pass check is green/);
});

test("release checklist covers the required regression gates", () => {
  const checklist = fs.readFileSync(path.join(__dirname, "..", "..", "docs", "release-checklist.md"), "utf8");
  for (const item of [
    "Full learner journey passes in the regression suite.",
    "Real simulation timer expiry is tested.",
    "Auth-protected routes reject anonymous access.",
    "Payment webhook idempotency test passes.",
    "AI scoring timeout, invalid response, and quota tests pass."
  ]) {
    assert.match(checklist, new RegExp(item.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});

test("auth fixture models protected routes and signed-in access", () => {
  const auth = readJson("auth-session.json");
  assert.equal(auth.authenticated, true);
  assert.ok(Array.isArray(auth.protected_routes));
  assert.ok(auth.protected_routes.length > 0);
  assert.ok(auth.protected_routes.every(route => route.startsWith("/")));
});

test("payment fixture models entitlement enforcement and revocation", () => {
  const payment = readJson("payment-entitlement.json");
  assert.equal(payment.entitlement, "paid_exam_access");
  assert.equal(payment.verified, true);
  assert.ok(payment.revoke_events.includes("charge.refunded"));
  assert.ok(payment.revoke_events.includes("charge.dispute.created"));
});

test("stripe webhook fixture is idempotent", () => {
  const webhook = readJson("stripe-webhook-events.json");
  assert.equal(webhook.idempotent, true);
  assert.equal(webhook.unique_event_count, 1);
  assert.equal(webhook.event_id, webhook.duplicate_event_id);
});

test("scoring fixtures cover success, quota, invalid payload, and media upload", () => {
  const success = readJson("ai-evaluation-success.json");
  const quota = readJson("ai-evaluation-quota.json");
  const invalid = readJson("ai-evaluation-invalid.json");
  const media = readJson("media-upload.json");

  assert.equal(success.evaluation.scores.total, 60);
  assert.equal(success.evaluation.scores.passed, true);
  assert.match(quota.error, /rate limit/i);
  assert.equal(invalid.provider, "mock");
  assert.equal(media.stored, true);
  assert.match(media.mime_type, /^audio\//);
});

test("release script is shipped, executable, and references the three risk gates", () => {
  const repoRoot = path.join(__dirname, "..", "..");
  const scriptPath = path.join(repoRoot, "scripts", "release.sh");
  assert.ok(fs.existsSync(scriptPath), "scripts/release.sh must exist");
  const stat = fs.statSync(scriptPath);
  // owner-execute bit (0o100) must be set.
  assert.ok((stat.mode & 0o100) !== 0, "scripts/release.sh must be executable");
  const body = fs.readFileSync(scriptPath, "utf8");
  assert.match(body, /set -euo pipefail/);
  for (const marker of ["T-011", "T-014", "T-016"]) {
    assert.ok(body.includes(marker), `script must reference ${marker}`);
  }
  assert.match(body, /gh pr create/);
});

test("release-process doc documents the cut + rollback workflow", () => {
  const doc = fs.readFileSync(
    path.join(__dirname, "..", "..", "docs", "release-process.md"),
    "utf8"
  );
  assert.match(doc, /scripts\/release\.sh/);
  assert.match(doc, /release\/2026-Q1/);
  assert.match(doc, /Hotfix Workflow/);
  assert.match(doc, /Rollback Guidance/);
});

test("release PR template is present for manual cuts", () => {
  const tmpl = fs.readFileSync(
    path.join(__dirname, "..", "..", ".github", "PULL_REQUEST_TEMPLATE", "release.md"),
    "utf8"
  );
  assert.match(tmpl, /Pre-merge gates/);
  assert.match(tmpl, /T-011/);
  assert.match(tmpl, /T-014/);
  assert.match(tmpl, /T-016/);
});

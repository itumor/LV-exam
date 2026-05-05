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

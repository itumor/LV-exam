# Contributing to lvcodex

This document defines the GitFlow conventions, branching, commit format, and merge gates for the lvcodex repository. It is the canonical reference for both human contributors and LLM coding agents.

For the full 24-month delivery plan, release-train structure, and task-ID index, see `/Users/eramadan/.claude/plans/create-a-detailed-delivery-robust-candle.md`.

## Branch Model (GitFlow)

```
main          ── production. tagged vX.Y.Z. only release/* and hotfix/* merge here.
release/MMM   ── freeze + QA. bug fixes only after cut. merges to main with tag.
develop       ── integration trunk. all feature/* branches merge here.
feature/T-XXX ── task branches off develop. squash-merged back.
hotfix/T-XXX  ── off main. merged to main AND develop.
chore/T-XXX   ── infra/build only.
refactor/T-XXX── non-functional changes.
docs/T-XXX    ── documentation-only changes.
```

### Branch naming

`<type>/T-<task-id>-<kebab-slug>`

Examples:

- `feature/T-014-prometheus-metrics`
- `chore/T-002-ci-split`
- `refactor/T-020-modularize-server`
- `hotfix/T-099-stripe-webhook-idempotency`

The `T-XXX` identifier MUST match a row in the delivery plan task table.

## Commit Messages (Conventional Commits)

Every commit message must follow [Conventional Commits 1.0](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

Allowed types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `style`, `revert`.

Examples:

- `feat(billing): add Stripe Tax for EU VAT`
- `fix(auth): clamp session TTL to 24h`
- `chore(ci): split workflow into pr/develop/release/deploy`

A breaking change uses `!` after the type and a `BREAKING CHANGE:` footer:

```
refactor(api)!: rename /api/attempts to /api/v2/attempts

BREAKING CHANGE: clients pinned to /api/attempts must upgrade.
```

Commit messages are enforced by `commitlint` in a `lefthook` pre-push hook (configured in task T-003).

## Merge Edges & Required Checks

| Source | Target | Required checks |
|---|---|---|
| `feature/*` | `develop` | gitleaks, pip-audit, `test:unit`, `test:contracts`, E2E `@smoke` subset, lint |
| `develop` | `release/*` | full regression (`npm test`), k6 load smoke, OpenAPI contract diff |
| `release/*` | `main` | full regression + manual QA checklist + Fly preview verified |
| `hotfix/*` | `main` | unit + contract + affected E2E. Auto-cherry-pick to `develop` after merge. |

## Pull Request Workflow

1. **Branch off the right base**: `feature/*` off `develop`, `hotfix/*` off `main`, `release/*` off `develop`.
2. **Keep PRs scoped to one task ID.**
3. **Rebase before pushing**: `git fetch origin && git rebase origin/develop`. Never merge `develop` into a feature branch.
4. **Use the PR template** (`.github/PULL_REQUEST_TEMPLATE.md`). Complete every section. The DoD checklist must be 100 % ticked before review.
5. **CI must be green** before requesting review.
6. **At least one reviewer** must approve a merge to `develop`. Two reviewers + release captain are required for `main`.
7. **Squash-merge** is the only allowed merge style for `feature/*` → `develop`. Use **rebase-merge** for `release/*` → `main` to preserve tag history.

## Definition of Done (DoD)

Every PR — regardless of train — must satisfy:

1. Works on desktop and mobile viewports.
2. Empty, loading, error, and success states are present.
3. Accessibility labels are applied where applicable.
4. Unit and contract tests are added. E2E tests cover the happy path.
5. Analytics events are emitted on user-meaningful actions.
6. No debug-only views or panels are reachable by learner accounts.
7. The 9/15 per-skill A2 pass rule is preserved when scoring code is touched.
8. Entitlement enforcement is server-side, never UI-only.
9. `gitleaks` is green; no secrets are committed.
10. `develop`-branch CI is green; the PR is rebased on `develop` tip.
11. Documentation is updated in `docs/` and `USER_MANUAL.md` when learner-visible behavior changes.
12. A Sentry breadcrumb or structured log line is added for any new failure mode.

## LLM Coding Agent Workflow

When an LLM coding agent picks up a task ID, it must follow the canonical 6-stage recipe:

1. **Locate** — `cavecrew-investigator` or `Explore` agent identifies the code touched by the task.
2. **Design** — `Plan` agent writes a per-task design note to `/Users/eramadan/.claude/plans/T-XXX.md`.
3. **Implement** — `cavecrew-builder` for 1–2 file edits, `general-purpose` for larger features.
4. **Validate** — run `npm run test:unit && npm run test:contracts && npm run test:e2e -- --grep @smoke` locally; add new tests for the new behavior.
5. **Review** — `cavecrew-reviewer` for routine diffs; `code-quality-reviewer` for `server.py`, `billing.py`, auth, or infra changes; `security-review` when secrets, CSP, or auth flows are touched.
6. **Deploy** — push the branch, open a PR, wait for CI, request a Fly preview for risky changes, then squash-merge to `develop`.

## File Ownership Matrix (Collision Avoidance)

When three agents work in parallel, the following hot files have a designated owner per release train. Other agents must rebase and post `@lock <file>` in their PR before touching them.

| Hot file | Default owner |
|---|---|
| `server.py` (until T-020 modularizes) | `agent-α` |
| `billing.py` | `agent-β` |
| `latvian-a2-exam-app/app.js` | `agent-γ` |
| `exam_bank.py` | alternating per train |
| `.github/workflows/*.yml` | `agent-β` (release captain) |
| `tests/` | any (append-only per task) |

## Rollback & Hotfix

- A production incident is fixed on `hotfix/T-XXX-…` off `main`.
- One reviewer fast-track is allowed for hotfixes.
- A new tag `vX.Y.Z+1` is cut. The hotfix is cherry-picked to `develop` immediately after merge to `main`.
- Database migrations involved? Invoke the T-013 restore drill on a standby Postgres replica, validate, then promote.

## Quick Reference Commands

```bash
# Start a new task
git fetch origin
git checkout develop
git pull origin develop
git checkout -b feature/T-XXX-my-task

# Keep the branch fresh
git fetch origin
git rebase origin/develop

# Run the gating tests locally
npm run test:unit
npm run test:contracts
npm run test:e2e -- --grep @smoke

# Open the PR
git push -u origin feature/T-XXX-my-task
gh pr create --base develop --title "feat(scope): T-XXX description"
```

## Questions

Open an issue with the `question` template, or contact the repository maintainers via the channel listed in `AGENTS.md`.

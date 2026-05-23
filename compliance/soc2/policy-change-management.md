# Change Management Policy

| Field | Value |
|---|---|
| **Document ID** | SOC2-POL-007 |
| **Owner** | Engineering Lead |
| **Effective date** | 2026-05-23 |
| **Last review** | 2026-05-23 |
| **Next review** | 2027-05-23 |
| **Review cadence** | Annual + on any CI/CD pipeline change |
| **TSC mapping** | CC8.1, CC7.1 |

## 1. Purpose

Ensure that every change to lvcodex production code, infrastructure, or
configuration is authorized, peer-reviewed, automatically tested, and
auditable. The change-management programme is implemented through the
existing GitFlow process documented in `CONTRIBUTING.md`; this policy
formalises that process as the SOC 2 evidence trail.

## 2. Authoritative References

- `CONTRIBUTING.md` — branch model, commit format, merge edges.
- `.github/workflows/` — required CI gates.
- `.github/PULL_REQUEST_TEMPLATE.md` — PR template and DoD checklist.
- The delivery plan at `/Users/eramadan/.claude/plans/create-a-detailed-delivery-robust-candle.md` — task IDs that every PR must reference.

## 3. Change Categories

| Category | Branch type | Approval | Merge target |
|---|---|---|---|
| **Standard feature** | `feature/T-XXX-*` | 1 reviewer | `develop` |
| **Refactor** | `refactor/T-XXX-*` | 1 reviewer | `develop` |
| **Chore / infra** | `chore/T-XXX-*` | 1 reviewer | `develop` |
| **Documentation** | `docs/T-XXX-*` | 1 reviewer | `develop` |
| **Release** | `release/MMM` | 2 reviewers + release captain | `main` |
| **Emergency hotfix** | `hotfix/T-XXX-*` | 1 reviewer fast-track | `main` (cherry-picked to `develop`) |

## 4. Required CI Gates

Every PR targeting `develop` or `main` must pass:

| Gate | Defined in | Purpose |
|---|---|---|
| `npm test` (regression suite) | `package.json` → `scripts/run_regression_suite.sh` | Functional regression. |
| `test:unit` (Python) | `tests/server/` | Unit tests for `server_app/`. |
| `test:contracts` | `tests/contracts/release-contracts.test.cjs` | Release contract guarantees. |
| `test:e2e --grep @smoke` | `tests/e2e/` | Critical-path Playwright smokes. |
| `gitleaks` | `.github/workflows/` | No secrets in diff. |
| `pip-audit` | `.github/workflows/` | No HIGH/CRITICAL Python CVEs. |
| `commitlint` | `lefthook.yml` | Conventional Commits. |

Bypassing any of these gates requires the emergency-change process
described in `policy-incident-response.md` §7.

## 5. Code Review Requirements

- A PR may not be merged by its author.
- Reviewers must verify the **Definition of Done** checklist in the PR template.
- Changes to `server.py`, `billing.py`, `server_app/services/auth.py`, or anything under `.github/workflows/` additionally require **Engineering Lead** or **Security Lead** approval.
- Comments referencing CVEs, secrets, or auth flows must be resolved by the Security Lead before merge.

## 6. Deployment Authorization

- Merges to `develop` deploy automatically to the preview environment on Fly.
- Production deploys happen only via tagged releases off `release/*` → `main`.
- The release captain signs off the production deploy in the release PR.
- Roll-forward and rollback procedures are in `docs/runbooks/deploy.md` (created under T-002).

## 7. Records

Every change produces the following auditable records:

| Record | Location | Retention |
|---|---|---|
| PR + reviews | GitHub | Indefinite |
| CI run logs | GitHub Actions | 90 days (default) — archived for compliance via T-070-followup |
| Production deploy events | Fly + Sentry release tags | 1 year |
| Emergency-change retros | `docs/incidents/` | Indefinite |

## 8. Revision History

| Date | Author | Change |
|---|---|---|
| 2026-05-23 | T-070 | Initial issue. |

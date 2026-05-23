<!--
Pull request template for the lvcodex repository.
See CONTRIBUTING.md for the full workflow.
-->

## Task: T-XXX — <one-line title>

## Source roadmap(s)

<!-- A=roadmap2026.md  B=latvian_a2_exam_platform_2_year_roadmap.md
     C=latvia-life-simulator-roadmap.md  D=BUSINESS_REPORT.md -->

- e.g. A §P2, B Q1.2, D §7.1 P3

## Type

<!-- pick one: feat | fix | chore | refactor | docs | perf | test | ci | build -->

## Depends on

<!-- task IDs of PRs that must merge first; or "none" -->

## Risk

<!-- low | medium | high -->

## Summary

<!-- 1–3 bullets describing what changed and why -->

-
-

## Definition of Done

- [ ] Works on desktop and mobile viewport
- [ ] Empty / loading / error / success states present
- [ ] Accessibility labels applied where applicable
- [ ] Unit tests added (`tests/server/test_*.py` or `tests/contracts/*`)
- [ ] E2E tests added or updated (`tests/playwright/*`) — happy path covered
- [ ] Analytics events emitted on user-meaningful actions
- [ ] No debug-only views reachable by learner accounts
- [ ] 9/15 per-skill A2 rule preserved if scoring code touched
- [ ] Entitlement enforcement is server-side, not UI-only
- [ ] No new secrets committed (gitleaks green)
- [ ] CI green on PR; rebased on `develop` tip
- [ ] Docs updated (`docs/`, `USER_MANUAL.md` when learner-visible)
- [ ] Sentry breadcrumb or structured log line added for new failure modes

## Test plan

<!-- bulleted checklist for the reviewer to walk through -->

- [ ]
- [ ]

## Screenshots / recordings

<!-- attach for UI changes; "n/a" otherwise -->

## Rollback plan

<!-- which commit to revert; whether a DB migration must be undone; whether a hotfix branch is needed -->

---

🤖 If a Claude Code agent authored this PR, leave the Co-Authored-By trailer in the commit message.

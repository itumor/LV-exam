# Release Process

This document is the canonical procedure for cutting a lvcodex release. It is the
human-readable companion to `scripts/release.sh` (task **T-019** in the 24-month
delivery plan).

The GitFlow convention is:

```
main          ← production, deployable, tagged vX.Y.Z
  ↑ FF-merge release/MMM (with tag)
release/MMM   ← freeze + QA, only bugfixes after cut
  ↑ merge from develop
develop       ← integration, always green-on-CI
```

`MMM` is a release-train name, typically `YYYY-Qn` (e.g. `2026-Q1`).

---

## 1. Pre-cut Checklist

Before invoking `scripts/release.sh`, the release captain MUST confirm:

1. `develop` is green on CI (`ci-develop.yml`).
2. Every feature task targeted for this release train has been merged to `develop`.
3. The three risk-gate PRs are merged to `develop`:
   - **T-011** Legal pages (Terms, Privacy, Cookie banner, Refund policy, DPA)
   - **T-014** Observability (Prometheus `/metrics` + Grafana dashboards)
   - **T-016** Stripe Tax + invoice + 7-day self-serve refund
   The script enforces this automatically; the checklist exists so the captain
   surfaces missing items *before* running the script.
4. `docs/release-checklist.md` has a named owner and a current run date for this
   train.
5. The captain's local clone is on `develop`, up-to-date with `origin/develop`,
   with a clean working tree.

Recommended rehearsal: run the script in dry-run mode first.

```bash
scripts/release.sh --name 2026-Q1 --version v1.0.0 --dry-run
```

The dry-run skips the risk-gate pre-flight, the push, the tag push, and the
`gh pr create` call, but exercises argument parsing and the printed plan.

---

## 2. Cutting the Release

```bash
# From a clean develop tip:
git checkout develop
git pull origin develop

scripts/release.sh --name 2026-Q1 --version v1.0.0
```

The script will, in order:

1. Confirm current branch is `develop` and is clean.
2. Verify `develop` matches `origin/develop` (fetch + compare).
3. Run the risk-gate pre-flight (T-011, T-014, T-016). Aborts with a clear
   message if any is missing.
4. Create `release/2026-Q1` from `develop` and push to origin.
5. Run the full regression locally (`npm test`). Fails fast on any failure.
6. Create an annotated tag `v1.0.0` on the release HEAD and push the tag.
7. Open a PR `release/2026-Q1` → `main` via `gh pr create`, with a generated
   body that lists `git log <prev-tag>..HEAD --oneline`.
8. Print the post-cut next-steps summary.

---

## 3. Stabilisation Window (only bugfixes after the cut)

After the cut, the release branch is frozen for everything except bugfixes:

- Bugfix branches off the release branch: `fix/T-XXX-slug` based on
  `release/2026-Q1`. Merged to `release/2026-Q1` via PR.
- Every bugfix that lands on the release branch MUST also be merged back to
  `develop` (cherry-pick or back-merge after the release closes).
- No feature work, no refactors, no non-essential dependency bumps on the
  release branch.
- Manual QA, Fly preview verification, and `docs/release-checklist.md` walk
  happen during this window.

---

## 4. Post-merge: Tag promotion + production deploy

When the release PR is approved and merged to `main`:

1. The merge is **not** a squash — the merge commit must preserve the tagged
   history.
2. `ci-deploy.yml` runs on `main` and deploys to Fly.
3. The tag `vX.Y.Z` now points at the release HEAD; production runs that tag.
4. Back-merge `main` into `develop` so the tag commit and any release-branch
   bugfixes flow back to integration:
   ```bash
   git checkout develop
   git pull origin develop
   git merge --no-ff origin/main
   git push origin develop
   ```

---

## 5. Hotfix Workflow

For a critical production fix that cannot wait for the next release:

1. Branch off `main`: `git checkout -b hotfix/T-XXX-slug main`.
2. Implement, add a regression test, commit using Conventional Commits.
3. Open a PR to `main` (the hotfix lane has its own CI gates per the plan
   §3 table — unit + contract + affected E2E).
4. After merge to `main`, tag a patch release `vX.Y.(Z+1)` on the merge commit.
5. Cherry-pick or back-merge the hotfix into `develop` and any open
   `release/*` branch so the fix is not lost on the next cut.

---

## 6. Rollback Guidance

If a release misbehaves in production:

- **Fastest path:** `flyctl releases list --app latvian-a2-exam` then
  `flyctl releases rollback <prev-version> --app latvian-a2-exam`.
- **Git path:** revert the release PR's merge commit on `main`. The next CI
  deploy on `main` will redeploy the previous tag. Then open a hotfix to fix
  forward.
- **Tag stays:** do not delete the released tag; instead create a new
  `vX.Y.(Z+1)` for the fix-forward.
- Always update `docs/release-checklist.md` with the incident notes and
  whether the gate that should have caught the bug needs a new entry.

---

## 7. Script Reference

```text
scripts/release.sh --help
```

The script enforces the same conventions documented here. Treat the
documentation as the source of truth for human steps; treat the script as
the source of truth for the cut mechanics.

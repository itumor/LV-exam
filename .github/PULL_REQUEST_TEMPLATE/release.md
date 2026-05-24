<!--
Release PR template (T-019).

Used either:
  - automatically by `scripts/release.sh` (which generates a body),
  - or manually for a hand-cut release by appending
    `?template=release.md` to the GitHub PR-create URL.

Keep this file in sync with the body builder in scripts/release.sh.
-->

## Release <vX.Y.Z> — <release-name>

Cut from `develop` for release-train `<release-name>` (e.g. `2026-Q1`).

### Merged tasks since previous tag

<!-- Paste `git log <prev-tag>..HEAD --oneline` here. -->

```
<commits>
```

### Pre-merge gates

- [ ] Risk-gate pre-flight passed (T-011 legal, T-014 observability, T-016 Stripe Tax merged to develop).
- [ ] Full regression (`npm test`) green on `release/<release-name>`.
- [ ] Annotated tag `<vX.Y.Z>` created on release HEAD.
- [ ] OpenAPI contract diff reviewed (no unintended breaks).
- [ ] k6 load smoke (50 vu / 60 s) green on the release branch.

### Required before merging to main

- [ ] Manual QA checklist signed off (`docs/release-checklist.md`).
- [ ] Fly preview app for this release verified.
- [ ] Only bugfix commits landed on `release/<release-name>` since the cut.
- [ ] CI green on this PR.
- [ ] Release captain + 1 reviewer approval.

### Rollback

Revert this PR's merge commit on `main`, then redeploy the previous tag. See
`docs/release-process.md` for the full rollback + hotfix workflow.

---

Generated/used by `scripts/release.sh` for task **T-019**.

# lvcodex public status page (cstate)

This directory is the source of the public status page rendered at
<https://itumor.github.io/LV-exam/status/>. The site is built with
[cstate](https://github.com/cstate/cstate) — a Hugo theme that turns a
small set of YAML config and markdown files into a static status page.

There is **no runtime cost**: incidents are markdown files committed to
the repo, GitHub Actions builds the site, GitHub Pages serves it.

---

## Files in this directory

| Path | Purpose |
|---|---|
| `config.yml` | Hugo + cstate config: site title, brand, systems list, timezone. |
| `content/issues/` | One markdown file per incident (front-matter + body). |
| `incidents/.gitkeep` | Placeholder for the legacy/archive incident directory. |

The build workflow lives at `.github/workflows/status-page.yml` and
re-runs on every push that touches `status/**`.

---

## Recording an incident

> tl;dr — create `status/content/issues/<short-slug>.md`, commit, push.
> CI deploys within ~2 minutes.

### 1. Open an incident

Create a new file in `status/content/issues/` with a slug-style name.
Pick a meaningful, URL-safe slug — it becomes the public permalink.

```
status/content/issues/2026-05-23-ai-scoring-latency.md
```

### 2. Fill in the front-matter

```markdown
---
title: "Elevated AI-scoring latency"
date: 2026-05-23T14:05:00Z
resolved: false
# severity: down | disrupted | notice
severity: disrupted
# Must match a `systems[].name` from config.yml
affected:
  - AI Scoring (Groq)
# Categories from config.yml; usually just one.
section: incident
---

We are seeing p95 latency on `/api/evaluate` exceed 10 s due to elevated
queue depth at Groq. Investigating with the upstream provider.
```

### 3. Post updates as Markdown headings inside the same file

Append a new `## <UTC timestamp>` block per update — newest at the
bottom. cstate renders them chronologically with the most recent
update featured at the top of the incident card.

```markdown
## Update — 2026-05-23 14:35 UTC

Groq confirmed an upstream incident. Scoring is queued; no requests
have been dropped.

## Resolved — 2026-05-23 15:10 UTC

Upstream restored. p95 back under 3 s. Closing.
```

### 4. Mark it resolved

When fully resolved, set `resolved: true` in the front-matter and add
a final `## Resolved` heading with the UTC timestamp.

### 5. Rebuild

The Pages workflow rebuilds automatically on push. To preview locally
before pushing:

```bash
# from the repo root
hugo --config status/config.yml --source status -D server
# then open http://localhost:1313/
```

(Requires Hugo extended ≥ 0.121.0 and the cstate theme cloned into
`status/themes/cstate` — the CI workflow handles both for you.)

---

## Adding or renaming a system

1. Edit `config.yml` → `params.systems`.
2. The `name` field is matched verbatim against the `affected:` array
   in every incident file. Renaming a system also requires a
   find-and-replace across `status/content/issues/`.
3. Commit and push — the site rebuilds and the new system shows green
   until an incident affects it.

See also: `docs/status-page.md` for the user-facing walkthrough.

---

## Subscriptions

cstate produces an **Atom feed** at `/index.xml`. Readers can subscribe
with any feed reader (Feedly, NetNewsWire, Thunderbird, …).

**Email subscriptions are NOT supported** in this iteration — cstate
does not ship a mailer and we have not wired one up. The follow-up task
(T-012b, to be filed) will pick one of:

- Bridge the Atom feed through Buttondown / EmailOctopus.
- Self-host a tiny SMTP worker that consumes `index.xml` and sends
  digests on change.

Flag this gap in any release notes that announce the status page.

---

## Operator quick reference

| Action | Command / file |
|---|---|
| Open an incident | new file in `status/content/issues/` |
| Post an update | append `## <timestamp>` heading in same file |
| Resolve an incident | `resolved: true` + final `## Resolved` heading |
| Schedule maintenance | same as incident, `section: maintenance` |
| Add a system | edit `params.systems` in `config.yml` |
| Preview locally | `hugo --config status/config.yml --source status server` |
| Force rebuild | re-run the `status-page.yml` workflow from the Actions tab |

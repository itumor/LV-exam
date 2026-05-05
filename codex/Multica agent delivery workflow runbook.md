# Multica Agent Delivery Workflow Runbook

## Purpose

- Keep Multica task state, local implementation, and GitHub PRs aligned in one delivery loop.
- Make each change traceable to a Multica issue from start to finish.
- Favor small, reviewable edits with evidence before marking work complete.

## Operating Loop

- Start by checking the live workspace state.
- Inspect the assigned issue and its full comment history.
- Move the issue to `in_progress` before making changes.
- Rename the issue so the title matches the actual work.
- Check out the repository with `multica repo checkout`.
- Read the repo-local `AGENTS.md` and any matching docs before editing.
- Implement the smallest safe change that satisfies the issue.
- Run the relevant validation commands and inspect the results.
- Commit the change on the working branch.
- Open a GitHub PR and verify its checks.
- Post the final outcome back on the Multica issue.
- Move the issue to `in_review` when the work is ready for review.

## Suggested CLI Checks

```bash
multica auth status
multica project list
multica agent list
multica issue list --output json
multica daemon status --output json
multica issue get <issue-id> --output json
multica issue comment list <issue-id> --output json
multica issue status <issue-id> in_progress
multica repo checkout <repo-url>
gh auth status
gh pr checks
gh pr view <pr-number>
```

## Guardrails

- Do not merge without passing checks and a clear scope match.
- Do not expose secrets, tokens, or credentials in comments or notes.
- Do not mark work done without a final result comment in Multica.
- If blocked, record the blocker precisely and move the issue to `blocked`.
- If you discover follow-up work, create a new issue instead of burying it in comments.

## References

- [[AGENTS]]
- [[Codex-Obsidian-Setup]]
- [[Latvian A2 Exam Simulator Roadmap]]
- https://multica.ai/docs/cli

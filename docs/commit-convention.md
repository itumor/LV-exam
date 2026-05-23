# Commit Convention

All commits in this repository must follow [Conventional Commits 1.0](https://www.conventionalcommits.org/). `commitlint` validates the message via a `lefthook` `commit-msg` hook on every commit.

## Allowed types

| Type | When to use |
|---|---|
| `feat` | New user-visible feature or capability |
| `fix` | Bug fix |
| `chore` | Build, tooling, infrastructure, repo metadata |
| `docs` | Documentation only |
| `test` | Test-only changes (add, refactor, fix) |
| `refactor` | Code change that neither adds a feature nor fixes a bug |
| `perf` | Performance improvement |
| `build` | Build system / external dependencies (`requirements.txt`, `package.json`) |
| `ci` | CI / CD configuration |
| `style` | Whitespace, formatting, missing semicolons |
| `revert` | Revert a prior commit |

## Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

- `<scope>` is optional. Use the area touched: `billing`, `auth`, `attempts`, `admin`, `frontend`, etc.
- `<subject>` ≤ 100 characters, no trailing period.
- `<body>` wraps freely (commitlint `body-max-line-length` is disabled).
- `<footer>` for `BREAKING CHANGE:` and `Refs:` / `Closes #N`.

## Examples

```
feat(billing): add Stripe Tax for EU VAT collection

Routes every checkout through Stripe Tax based on the customer's
billing-address country. Falls back to the seller-of-record rate
when the location lookup fails.

Refs: T-016
```

```
fix(auth): clamp session TTL to 24h

Sessions previously inherited a 30-day cookie expiry from a stale
default. This caused the entitlement cache to retain expired grants
for weeks. Clamping to 24h removes the stale-grant window.

Closes #198
```

```
refactor(api)!: rename /api/attempts to /api/v2/attempts

BREAKING CHANGE: clients pinned to /api/attempts must upgrade. The
deprecated path keeps responding through 2026-Q3 then is removed.
```

## Installation

`lefthook` installs the `commit-msg` hook automatically when you run `npm install` (via the `prepare` script). To install manually:

```bash
npx lefthook install
```

To bypass the hook in an emergency (NOT for normal commits):

```bash
LEFTHOOK=0 git commit -m "..."
```

`--no-verify` is forbidden by `CONTRIBUTING.md`. Bypassing the hook for normal work will be rejected at review.

## What commitlint rejects

- Subject longer than 100 characters.
- Missing or unknown type (e.g. `update: …`).
- Mixed-case type (`Feat:` instead of `feat:`).
- Missing colon after the type/scope.

The rule set lives in `.commitlintrc.json`.

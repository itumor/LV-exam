# Avatars + cosmetics catalog (T-051)

This directory ships 20 avatar configurations consumed by
`server_app/services/avatars.py`. Each avatar is a flat JSON document
that pins down four things:

* **identity** — `id`, `display_name`, `description`, `art_ref` (a path
  the frontend resolves; the server treats it as an opaque string).
* **rarity** — `common`, `uncommon`, `rare`, `epic`, `legendary`. Pure
  UX metadata; the server treats it as a sort key only.
* **unlock contract** — exactly one of three tiers:
    - `free` — unlocked for every account on first sight (no XP, no
      payment).
    - `xp` — requires `unlock.xp` lifetime XP (sum from `xp_log`,
      shipped by T-034). The avatars service auto-grants the unlock
      the moment the threshold is crossed.
    - `premium` — gated behind an active subscription (`subscription`
      entitlement, shipped by T-024 / T-041 institutional seats also
      count). Premium avatars cannot be granted by XP — even with
      infinite XP, the account must hold a paid plan.

The catalog is loaded once on first request (process-wide cache) and
re-loaded automatically when the test suite calls the
`_reset_catalog_cache_for_tests` hook.

## Why per-file JSON (not one bundle)?

Same reason `content/npcs/` and `content/exams/B1/` ship one file per
entity: every avatar is an independent content review item, the diff
of "added/removed/renamed avatars" is human-readable in PRs, and the
catalog loader does a single `glob` so adding a 21st avatar tomorrow
is a one-file change.

## Tier breakdown (20 avatars)

* **5 free** — shipped unlocked for every account.
* **10 XP-unlock** — thresholds: 50, 150, 300, 500, 750, 1 000, 1 500,
  2 500, 4 000, 6 000 lifetime XP.
* **5 premium** — require an active subscription.

The XP curve mirrors the canonical T-034 award amounts (10 / mission,
2 / quiz, 50 / mock, 100 / perfect skill) — the first XP avatar is
unlocked after ~5 missions, the last after a sustained study habit.

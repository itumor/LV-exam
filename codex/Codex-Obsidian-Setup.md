# Codex + Obsidian Setup

This vault is ready for three workflows:

1. Use the Codex desktop app directly on the vault.
2. Use the Redstone Copilot community plugin inside Obsidian.
3. Develop custom vault automation as a local Obsidian plugin.

## 1. Codex app on this vault

Checklist:

- Open the Codex desktop app.
- Sign in with your ChatGPT account.
- Choose `/Users/eramadan/GitRepo/lvcodex/codex` as the project folder.
- Keep the vault in Git if you want easy rollback for bulk note edits.
- Start with read-only tasks first, then move to write tasks once the results look right.

Suggested first prompts:

- `Normalize frontmatter across incident notes without changing note titles.`
- `Summarize notes updated in the last 7 days into one operations brief with source links.`
- `Find orphaned runbook notes and suggest wiki-links to connect them.`

Validation:

- Confirm Codex can see `Welcome.md`.
- Ask Codex to list the vault root files before you allow broad edits.
- Review any proposed multi-file change before accepting it.

## 2. Redstone Copilot inside Obsidian

Current reference points:

- OpenAI says the Codex app setup is: sign in with ChatGPT, select a local folder or Git repo, then start a task.
- The Redstone Copilot repository currently describes itself as a Codex CLI-powered Obsidian sidebar, desktop-only, with support for current-note or whole-vault context.
- The repository manifest currently reports version `0.4.3`.

Install path:

1. In Obsidian, open `Settings -> Community plugins`.
2. Disable Safe mode if it is still enabled.
3. Try searching for `Redstone Copilot`.
4. If it is not listed in the Community Plugins browser, install it manually from the latest GitHub release:
   - Create `/Users/eramadan/GitRepo/lvcodex/codex/.obsidian/plugins/redstone-copilot`
   - Copy the release `manifest.json`, `main.js`, and `styles.css` into that folder
5. Reopen Obsidian and enable `Redstone Copilot`.

Validation checklist:

- Open the Redstone sidebar.
- Complete ChatGPT sign-in if prompted by the plugin.
- Set context mode to `Current note` first.
- Ask it to summarize `Welcome.md`.
- Switch to whole-vault mode and ask it to list vault root notes only.
- Leave internet access off until you actually need browsing.

Recommended plugin settings:

- Mode: read-only for first run
- Context: current note, then whole vault
- Internet access: off by default
- AGENTS.md: keep and edit as your vault handbook

## 3. Custom plugin development in this vault

This vault now includes a local scaffold at:

- `/Users/eramadan/GitRepo/lvcodex/codex/.obsidian/plugins/ops-brief-builder`

The scaffold adds a command that creates an operations brief note from recently updated notes tagged like meetings or incidents.
By default it ignores `.obsidian/` content and old generated briefs, and it only includes notes that match configured tags or contain open checkbox tasks.

Local dev loop:

1. Open this vault in Obsidian desktop.
2. Open `Settings -> Community plugins`.
3. Enable `Ops Brief Builder`.
4. Run the command palette action `Ops Brief Builder: Generate ops brief`.
5. Review the generated note under `Operations/`.

What to change first if you customize it:

- Tags used for categorization
- Lookback window
- Output folder
- Brief template structure

## Risks and guardrails

- Community plugins are not first-party integrations, so update behavior can change.
- Whole-vault context is powerful, but it increases blast radius for accidental edits.
- Generated summaries are only as good as note hygiene, tags, and frontmatter quality.

## Sources

- OpenAI Codex setup: https://openai.com/codex/get-started/
- Redstone Copilot repo: https://github.com/madAsket/obsidian-codex
- Redstone Copilot manifest: https://raw.githubusercontent.com/madAsket/obsidian-codex/master/manifest.json

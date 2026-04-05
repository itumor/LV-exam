# Ops Brief Builder

Local Obsidian community plugin scaffold for a concrete workflow:

- scan recently modified notes
- group notes by operational tags
- collect open checkbox tasks
- generate a dated Markdown operations brief

## Commands

- `Ops Brief Builder: Generate ops brief`

## Default behavior

- looks back 7 days
- writes output to `Operations/`
- categorizes notes by tags such as `meeting`, `incident`, `postmortem`, and `action-item`
- ignores notes under `.obsidian/` and previously generated `Operations/` briefs
- skips unrelated notes unless they match configured tags or contain open checkbox tasks

## Good next improvements

- add a modal for choosing date range
- filter by folder in addition to tags
- support templates for brief sections
- add a dry-run preview before writing the note

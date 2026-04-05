# Obsidian Vault Instructions

This repository is an Obsidian vault.

## Editing rules

- Prefer small, reversible edits to Markdown notes.
- Preserve existing wiki-links, tags, and frontmatter keys unless a task explicitly asks to normalize them.
- When creating a new note, prefer placing it in an existing topical folder instead of inventing a new structure.
- Keep note titles human-readable and compatible with Obsidian wiki-links.

## Writing conventions

- Prefer Markdown headings, short paragraphs, and flat bullet lists.
- When summarizing multiple notes, include source links back to the original notes.
- If a note has frontmatter, keep it at the top of the file and preserve unknown fields.

## Operational notes

- `.obsidian/` contains local vault configuration and plugins.
- Community plugin code should live under `.obsidian/plugins/<plugin-id>/`.
- Avoid editing Obsidian workspace state unless the task specifically requires changing the UI layout.

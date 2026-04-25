# Latvian A2 Exam Studio

Static browser app for dynamically rendering the existing `codex/A2_Mock_Exam_01.md` through `codex/A2_Mock_Exam_10.md` files with their audio and image attachments.

## Run

Serve the repository root so the app can fetch the `codex/` Markdown and attachment files:

```sh
python3 -m http.server 4173 --directory /Users/eramadan/GitRepo/lvcodex
```

Then open `http://localhost:4173/latvian-a2-exam-app/`.

## Docker

Build and run the static app image:

```sh
docker build -t lvcodex/latvian-a2-exam-app:local .
docker run --rm -p 4173:80 lvcodex/latvian-a2-exam-app:local
```

Or use Compose:

```sh
docker compose up --build
```

Open `http://localhost:4173/latvian-a2-exam-app/`.

## Scope

- No frontend runtime dependencies.
- Renders exams 1-10 from the Codex vault Markdown.
- Loads MP3 audio attachments for listening and speaking tasks.
- Loads generated PNG image attachments for writing and speaking tasks.
- Exports the current exam as Markdown or JSON.
- Shows local regeneration commands for Piper TTS and Ollama image generation.

# Latvian A2 Exam Studio

Browser exam app for dynamically rendering the existing `codex/A2_Mock_Exam_01.md` through `codex/A2_Mock_Exam_10.md` files with their audio and image attachments. A small local Python server adds secure AI scoring without exposing API keys to the browser.

## Run

Serve the repository root through the local app server so the app can fetch the `codex/` Markdown, attachment files, and use the AI evaluation endpoint:

```sh
python3 server.py
```

Then open `http://localhost:4173/latvian-a2-exam-app/`.

The server also exposes `GET /healthz` for container and load balancer checks.

The legacy static server still renders exams, but AI scoring requires `server.py` because the browser must not hold provider credentials.

## AI scoring

Create `.env` from `.env-example` and choose one provider.

Groq:

```sh
GROQ_API_KEY=<your-groq-key>
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
```

Local Codex CLI:

```sh
LLM_PROVIDER=codex
CODEX_MODEL=gpt-5.2
# Optional.
CODEX_PROFILE=<profile-name>
```

For local OSS scoring through Codex CLI, also set:

```sh
CODEX_OSS=true
CODEX_LOCAL_PROVIDER=ollama
```

The Codex provider expects the `codex` executable to be available to the `server.py` process. If needed, set `CODEX_CLI_PATH=/absolute/path/to/codex`. In non-OSS mode the server defaults to `gpt-5.2` unless `CODEX_MODEL` is set. In OSS mode, Codex uses the local provider default unless `CODEX_MODEL` is set.

In the app, use **Submit Answers**, then **AI Score** or **AI score and corrections**. The frontend sends the current submission and exam Markdown to `/api/evaluate`; the server calls the configured LLM and returns per-skill points, corrections, and feedback.

### Docker with Codex on the host

The Docker container cannot execute the macOS Codex CLI installed on the laptop. To use Docker for the app and Codex CLI from the host, run a small host-local scoring server on a different port:

```sh
CODEX_REMOTE_URL= PORT=4174 LLM_PROVIDER=codex CODEX_MODEL=gpt-5.2 python3 server.py
```

Then set the Docker `.env` to forward scoring to that host server:

```sh
LLM_PROVIDER=codex
CODEX_REMOTE_URL=http://host.docker.internal:4174/api/evaluate
CODEX_MODEL=gpt-5.2
```

Start or restart Docker after changing `.env`:

```sh
docker compose up --build
```

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

Set `APP_PORT` if the host port needs to change:

```sh
APP_PORT=8080 docker compose up --build
```

For cloud Docker Compose, keep secrets in the platform environment or a runtime-only env file, not in the image. Required runtime variables depend on the scoring provider:

```sh
LLM_PROVIDER=groq
GROQ_API_KEY=<your-groq-key>
LLM_MODEL=llama-3.3-70b-versatile
```

or:

```sh
LLM_PROVIDER=codex
CODEX_REMOTE_URL=https://<your-host-scoring-service>/api/evaluate
CODEX_MODEL=gpt-5.2
```

The container listens on port `80`; publish that port from your cloud Compose service or load balancer.

Codex CLI scoring inside Docker requires `CODEX_REMOTE_URL` unless the image is extended to install and authenticate Codex CLI inside the container.

See also:

- `docs/deployment-runbook.md`
- `docs/privacy-policy.md`
- `docs/terms-of-service.md`
- `docs/unofficial-disclaimer.md`
- `docs/security-review.md`

## Scope

- No frontend runtime dependencies.
- Local Python server endpoint for Groq or Codex CLI based AI scoring.
- Renders exams 1-10 from the Codex vault Markdown.
- Loads MP3 audio attachments for listening and speaking tasks.
- Loads generated PNG image attachments for writing and speaking tasks.
- Exports the current exam as Markdown or JSON.
- Shows local regeneration commands for Piper TTS and Ollama image generation.

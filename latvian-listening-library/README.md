# Latvian Listening Library

This folder processes Latvian A1/A2 listening MP3 files into a browsable study library.

## Architecture

- MP3 audio is discovered from `A1_klausisanas/` and `A2_klausisanas/`; this workspace also supports the detected `codex/A1_klausisanas/` and `codex/A2_klausisanas/` locations.
- Groq Whisper transcribes Latvian audio only with `whisper-large-v3-turbo`, `language=lv`, and `temperature=0`.
- Local LibreTranslate translates generated Latvian transcript text from Latvian to English.
- Markdown files are written for Latvian transcripts and English translations.
- JSON metadata, progress state, failed item state, and logs support safe resume.
- `web/` is a static UI for browsing, playing, and reading generated content.

No hosted translation API is used. Groq audio translation is not used.

## Folder Structure

```text
latvian-listening-library/
  requirements.txt
  scripts/
    process_audio.py
    build_catalog.py
    validate_outputs.py
  translation/
    docker-compose.yml
    start_libretranslate.sh
    stop_libretranslate.sh
    check_libretranslate.py
  data/
    A1_klausisanas/
    A2_klausisanas/
  state/
    progress.json
    failed_items.json
  logs/
    processing.log
  web/
    index.html
    styles.css
    app.js
    catalog.json
```

## Setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r latvian-listening-library/requirements.txt
```

The processor loads `.env` from the repository root and checks for a Groq token in this order:

```text
GROQ_API_KEY
GROQ_API_TOKEN
GROQ_KEY
```

Do not put secrets in this folder. Do not commit `.env`.

## Start Local LibreTranslate

Preferred Docker Compose flow:

```bash
cd latvian-listening-library/translation
./start_libretranslate.sh
python check_libretranslate.py
```

LibreTranslate is expected at:

```text
http://localhost:5000
```

To change the host port, edit the left side of the port mapping in `translation/docker-compose.yml`, for example `5001:5000`, then pass:

```bash
python latvian-listening-library/scripts/process_audio.py --libretranslate-url http://localhost:5001
```

Fallback if Docker is unavailable:

```bash
pip install libretranslate
libretranslate
```

Then run the check script again.

## Processing Commands

Dry-run:

```bash
python latvian-listening-library/scripts/process_audio.py --dry-run
```

Process all files with resume and a LibreTranslate readiness check:

```bash
python latvian-listening-library/scripts/process_audio.py --resume --check-libretranslate
```

Resume after a failure:

```bash
python latvian-listening-library/scripts/process_audio.py --resume
```

Translation-only resume after transcripts already exist:

```bash
python latvian-listening-library/scripts/process_audio.py --translate-only --resume
```

Process a small batch:

```bash
python latvian-listening-library/scripts/process_audio.py --resume --limit 5 --check-libretranslate
```

Process one level:

```bash
python latvian-listening-library/scripts/process_audio.py --resume --level A1 --check-libretranslate
python latvian-listening-library/scripts/process_audio.py --resume --level A2 --check-libretranslate
```

Build the web catalog:

```bash
python latvian-listening-library/scripts/build_catalog.py
```

Validate outputs:

```bash
python latvian-listening-library/scripts/validate_outputs.py
```

## Web UI

After processing and building the catalog:

```bash
cd latvian-listening-library/web
python -m http.server 8080
```

Open:

```text
http://localhost:8080
```

The short-form listening feed is available at:

```text
http://localhost:8080/micro.html
```

It turns the catalog into swipeable 15-45 second listening cards with an instant quiz, transcript reveal, and local shadow-speaking recorder.

## Output Locations

- Copied audio: `latvian-listening-library/data/<level>_klausisanas/audio/`
- Latvian transcripts: `latvian-listening-library/data/<level>_klausisanas/transcripts_lv/`
- English translations: `latvian-listening-library/data/<level>_klausisanas/translations_en/`
- Metadata: `latvian-listening-library/data/<level>_klausisanas/metadata/`
- Progress: `latvian-listening-library/state/progress.json`
- Failures: `latvian-listening-library/state/failed_items.json`
- Logs: `latvian-listening-library/logs/processing.log`

## Safety And Resume Behavior

- Source audio files are never deleted.
- Outputs are written atomically through temporary files and then renamed.
- Progress is saved after copy, transcription status changes, translation status changes, metadata writes, and failures.
- Completed items are skipped by default unless `--force` is used.
- Translation failures keep the Latvian transcript and mark translation as failed, allowing `--translate-only --resume`.
- Retryable Groq and LibreTranslate failures are retried up to 3 times with exponential backoff.

## Troubleshooting

- Missing Groq API key: add `GROQ_API_KEY`, `GROQ_API_TOKEN`, or `GROQ_KEY` to the repository root `.env`; rerun with `--resume`.
- Invalid Groq API key: replace the key in `.env`; the script logs an authentication failure without printing the key.
- No Groq credits/quota: add credits or wait for quota reset; rerun with `--resume`.
- Groq rate limit: wait and rerun with `--resume`; completed files will be skipped.
- Large MP3 files: split the audio externally, then rerun; the script logs file-specific failures.
- Empty transcript: verify the MP3 is audible Latvian audio and rerun with `--force` for that batch if needed.
- Corrupt MP3: replace or repair the source file; rerun with `--resume`.
- Docker not installed: use the Python fallback `pip install libretranslate && libretranslate`.
- LibreTranslate not running: start it with `translation/start_libretranslate.sh`.
- LibreTranslate model download issues: check container logs with `docker compose logs -f` from `translation/`; restart after models finish downloading.
- Latvian not available in LibreTranslate: confirm the `lv` model downloaded; restart with `LT_UPDATE_MODELS=true`.
- English not available in LibreTranslate: confirm the `en` model downloaded and `/languages` includes `en`.
- Translation output empty: check `logs/processing.log`, restart LibreTranslate, then rerun `--translate-only --resume`.

## Dependency Notes

`requirements.txt` intentionally stays small:

- `groq`: official Groq Python SDK for Whisper transcription.
- `python-dotenv`: loads the existing root `.env`.
- `tqdm`: progress display for batches.
- `mutagen`: best-effort MP3 duration metadata.
- `requests`: local LibreTranslate HTTP API calls.

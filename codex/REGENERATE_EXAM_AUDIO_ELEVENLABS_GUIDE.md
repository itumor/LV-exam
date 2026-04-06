# Regenerate Exam Audio with ElevenLabs

This guide explains how to run the ElevenLabs-based audio generator and test it safely on Exam 1 without overwriting the current Piper audio.

## What the script does

The script:

- reads `codex/A2_Mock_Exam_*.md`
- extracts listening transcripts from `## Listening Transcripts`
- extracts speaking prompts from `### Runātprasmes pārbaude`
- sends each text block to ElevenLabs Text-to-Speech
- writes separate comparison MP3 files with the suffix `_elevenlabs.mp3`

Script path:

- [regenerate_exam_audio_elevenlabs.py](/Users/eramadan/GitRepo/lvcodex/scripts/regenerate_exam_audio_elevenlabs.py)

## Environment variables

Required:

- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`

Optional:

- `ELEVENLABS_MODEL_ID`
  - default: `eleven_v3`
- `ELEVENLABS_OUTPUT_FORMAT`
  - default: `mp3_44100_128`

## Create a local `.env`

Create a file named `.env` in the repo root.

Example:

```bash
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
ELEVENLABS_MODEL_ID=eleven_v3
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
```

Notes:

- `.env` is ignored by git
- do not commit real secrets
- the script loads `.env` automatically

## Install and run

Create a virtual environment and install dependencies:

```bash
python3.11 -m venv .venv-elevenlabs
source .venv-elevenlabs/bin/activate
```

This script uses only the Python standard library, so no extra package install is required.

## Dry run

Use `--dry-run` to preview extracted text without calling the API:

```bash
python scripts/regenerate_exam_audio_elevenlabs.py --exam A2_Mock_Exam_01.md --dry-run
```

## Run Exam 1 only

```bash
source .venv-elevenlabs/bin/activate
python scripts/regenerate_exam_audio_elevenlabs.py --exam A2_Mock_Exam_01.md
```

## Output files

The script does not overwrite the current MP3s.

For Exam 1 it writes:

- `codex/Attachments/A2_Mock_Exam_01/klausisanas_1_uzdevums_elevenlabs.mp3`
- `codex/Attachments/A2_Mock_Exam_01/klausisanas_2_uzdevums_elevenlabs.mp3`
- `codex/Attachments/A2_Mock_Exam_01/klausisanas_3_uzdevums_elevenlabs.mp3`
- `codex/Attachments/A2_Mock_Exam_01/runasana_1_jautajumi_elevenlabs.mp3`
- `codex/Attachments/A2_Mock_Exam_01/runasana_2_jautajumi_elevenlabs.mp3`
- `codex/Attachments/A2_Mock_Exam_01/runasana_3_jautajumi_elevenlabs.mp3`

## How to switch voices

Update `ELEVENLABS_VOICE_ID` in `.env` and rerun the script.

The script requires an explicit voice ID so you can test different voices without code changes.

## Cost and rate-limit note

- ElevenLabs API usage is billed by character and plan
- Exam 1 is a small test run, but repeated full-deck generation will consume credits
- Eleven v3 has a lower per-request text limit than some other models, so keep each job scoped to the existing exam chunks

## Validate generated files

Check that the MP3 files exist and have valid durations:

```bash
ffprobe codex/Attachments/A2_Mock_Exam_01/klausisanas_1_uzdevums_elevenlabs.mp3
```

If you want to compare with the current Piper version, listen to the original file and the `_elevenlabs.mp3` file side by side.

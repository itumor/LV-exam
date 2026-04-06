# Regenerate Exam Audio Guide

This guide explains how to run [regenerate_exam_audio.py](/Users/eramadan/GitRepo/lvcodex/scripts/regenerate_exam_audio.py) and how to improve the output quality if the audio sounds too quiet, noisy, or unnatural.

## What the script does

- Reads the exam markdown files in `codex/A2_Mock_Exam_*.md`
- Extracts listening transcripts from `## Listening Transcripts`
- Extracts speaking prompts from `### Runātprasmes pārbaude`
- Generates fresh WAV audio with Piper
- Converts the WAV files to MP3 with `ffmpeg`
- Rewrites the existing files in `codex/Attachments/A2_Mock_Exam_*/`

Current default voice:

- `lv_LV-rudolfs-medium`

Current MP3 post-processing:

- `volume=50dB,alimiter=limit=0.85`

## Requirements

- Python `3.11` or `3.12`
- `ffmpeg`
- Internet access the first time, so the Piper model can be downloaded into `~/.cache/lvcodex/piper/`

Check tools:

```bash
python3.11 --version
ffmpeg -version
```

## Setup

Create a virtual environment and install Piper:

```bash
python3.11 -m venv .venv-piper
source .venv-piper/bin/activate
pip install piper-tts==1.4.2
```

## Run for all exams

```bash
source .venv-piper/bin/activate
python scripts/regenerate_exam_audio.py
```

This regenerates all six MP3 files for every `A2_Mock_Exam_*.md`.

## Run for one exam only

```bash
source .venv-piper/bin/activate
python scripts/regenerate_exam_audio.py --exam A2_Mock_Exam_01.md
```

You can repeat `--exam` to target several files:

```bash
python scripts/regenerate_exam_audio.py \
  --exam A2_Mock_Exam_01.md \
  --exam A2_Mock_Exam_02.md
```

## Dry run

Use this to verify what text will be synthesized before changing any MP3 files:

```bash
source .venv-piper/bin/activate
python scripts/regenerate_exam_audio.py --exam A2_Mock_Exam_01.md --dry-run
```

## How to improve audio quality

### 1. Try a better Latvian voice model first

The biggest quality lever is the model itself.

This repo currently defaults to:

- `lv_LV-rudolfs-medium`

If you want to test another model, change these values in [regenerate_exam_audio.py](/Users/eramadan/GitRepo/lvcodex/scripts/regenerate_exam_audio.py):

- `DEFAULT_MODEL_NAME`
- `DEFAULT_MODEL_URL`

Example direction:

- keep `rudolfs` if the output is clear and loud enough
- test another Latvian Piper voice only if you are ready to compare sample clips

### 2. Fix volume problems in the `ffmpeg` filter chain

If the speech is too quiet, harsh, or distorted, adjust the filter in `wav_to_mp3()`:

Current filter:

```text
volume=50dB,alimiter=limit=0.85
```

Useful adjustments:

- Too quiet: increase gain slightly, for example `volume=52dB`
- Too distorted: reduce gain, for example `volume=45dB`
- Too aggressive: lower limiter ceiling, for example `alimiter=limit=0.75`

Example safer variant:

```text
volume=45dB,alimiter=limit=0.80
```

### 3. Tune speech pacing

The script currently adds sentence pauses here:

```python
"--sentence_silence", "0.45"
```

If the audio feels rushed:

- increase to `0.55` or `0.60`

If the audio feels too slow:

- reduce to `0.30` or `0.35`

### 4. Clean the source text before synthesis

Bad punctuation or placeholders can sound unnatural in TTS.

This script already normalizes:

- numbered prompts like `1.`, `2.`
- labels like `paziņojums` and `saruna`
- placeholder text like `... ? ...`

If a specific exam still sounds strange, inspect the extracted text with:

```bash
python scripts/regenerate_exam_audio.py --exam A2_Mock_Exam_01.md --dry-run
```

Then fix the markdown wording or extend `normalize_for_speech()`.

### 5. Validate the loudness after regeneration

Use `ffprobe` and `ffmpeg` to sanity-check one output file:

```bash
ffprobe codex/Attachments/A2_Mock_Exam_01/klausisanas_1_uzdevums.mp3
ffmpeg -i codex/Attachments/A2_Mock_Exam_01/klausisanas_1_uzdevums.mp3 \
  -af astats=metadata=1:reset=0 -f null -
```

What to look for:

- audible voice, not only hiss
- RMS not extremely low
- no obvious clipping

## Recommended workflow for quality improvements

1. Run `--dry-run` for one exam.
2. Regenerate only one exam.
3. Listen to `klausisanas_1_uzdevums.mp3` and `runasana_1_jautajumi.mp3`.
4. Adjust model, gain, limiter, or pause settings.
5. Regenerate all exams only after the sample sounds good.

## Known issue from this repo

We already saw one Latvian Piper setup produce WAV files that were technically valid but far too quiet, which made the MP3s sound like hiss. That is why this repo now:

- defaults to `lv_LV-rudolfs-medium`
- boosts the signal with `volume=50dB`
- applies a limiter during MP3 encoding

If the problem returns, treat it as a waveform-level issue first, not just an MP3 issue.

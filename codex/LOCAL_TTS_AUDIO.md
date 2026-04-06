# Local TTS Audio

The mock exam audio in this repository is generated fully locally with Piper using the Latvian voice `lv_LV-rudolfs-medium`.

## Why this voice

- It runs fully offline.
- It has a real Latvian voice with stronger usable output for exam prompts on this machine.
- It is fast enough to regenerate all exam assets on a laptop without GPU requirements.

## Regenerate audio

Use Python 3.11 or 3.12 for the Piper install.

```bash
python3.11 -m venv .venv-piper
source .venv-piper/bin/activate
pip install piper-tts==1.4.2
python scripts/regenerate_exam_audio.py
```

The script downloads the Piper model into `~/.cache/lvcodex/piper/`, extracts listening transcripts and speaking prompts from the exam markdown, then rewrites the existing MP3 attachments in place.

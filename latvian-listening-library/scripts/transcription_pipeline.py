#!/usr/bin/env python3
"""
Serverless Transcription Pipeline

A modular pipeline for processing Latvian audio files into lessons with transcripts,
translations, vocabulary extraction, and timestamped segments.

Usage:
    python transcription_pipeline.py --input audio.mp3 --output lesson.json
    python transcription_pipeline.py --batch --input-dir data/A1/audio --output-dir output/
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

try:
    import groq
    from dotenv import load_dotenv
except ImportError:
    print("Install dependencies: pip install groq python-dotenv")
    sys.exit(1)

GROQ_API_KEY = (
    os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_TOKEN") or os.getenv("GROQ_KEY")
)

LIBRETRANSLATE_URL = os.getenv("LIBRETRANSLATE_URL", "http://localhost:5000")

REQUIRED_FIELDS = ["id", "level", "original_filename", "audio_url", "status"]


def load_audio(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def transcribe(
    audio_bytes: bytes, language: str = "lv", model: str = "whisper-large-v3-turbo"
) -> dict:
    """
    Stage 2: Transcribe audio using Groq Whisper.
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")

    client = groq.Groq(api_key=GROQ_API_KEY)

    response = client.audio.transcriptions.create(
        model=model,
        file=("audio.mp3", audio_bytes, "audio/mpeg"),
        language=language,
        temperature=0.0,
        response_format="verbose_json",
        timestamp_granularities=["word"],
    )

    return {
        "text": response.text,
        "segments": getattr(response, "segments", []),
        "words": getattr(response, "words", []),
    }


def translate_text(text: str, from_lang: str = "lv", to_lang: str = "en") -> str:
    """
    Stage 4: Translate text using LibreTranslate.
    """
    import requests

    response = requests.post(
        f"{LIBRETRANSLATE_URL}/translate",
        json={
            "q": text,
            "source": from_lang,
            "target": to_lang,
            "format": "text",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("translatedText", "")


def extract_vocabulary(transcript: str, level: str = "A2") -> list:
    """
    Stage 5: Extract vocabulary from transcript.

    Returns a list of vocabulary entries:
        {"latvian": "word", "english": "translation", "level": "A2", "context": "sentence"}
    """
    vocab = []

    common_a1 = {
        "sveiks": "hello",
        "paldies": "thanks",
        "lūdzu": "please",
        "jā": "yes",
        "nē": "no",
        "labdien": "good day",
    }
    common_a2 = {
        "atvainojiet": "excuse me",
        "ļoti": "very",
        "vēl": "still/more",
        "šodien": "today",
        "rīt": "tomorrow",
        "vakar": "yesterday",
    }

    combined = {**common_a1, **common_a2}

    words = transcript.lower().split()
    for word in words:
        clean = word.strip(".,!?;:()")
        if clean in combined:
            vocab.append(
                {
                    "latvian": clean,
                    "english": combined[clean],
                    "level": "A1" if clean in common_a1 else "A2",
                    "source": "common",
                }
            )

    return vocab[:20]


def pipeline(
    input_path: str,
    output_path: Optional[str] = None,
    level: str = "A1",
    dry_run: bool = False,
) -> dict:
    """
    Main pipeline executing all stages.
    """

    audio_bytes = load_audio(input_path)
    filename = Path(input_path).name

    if dry_run:
        print(f"[Dry run] Would process: {filename}")
        return {"status": "dry_run", "filename": filename}

    transcript_result = transcribe(audio_bytes, language="lv")
    transcript_text = transcript_result["text"]

    translation_text = translate_text(transcript_text, "lv", "en")

    vocabulary = extract_vocabulary(transcript_text, level)

    lesson = {
        "id": f"{level}-{hash(filename) % 100000:05d}",
        "level": level,
        "original_filename": filename,
        "audio_url": f"data/{level}_klausisanas/audio/{filename}",
        "lv_text": transcript_text,
        "en_text": translation_text,
        "status": "completed",
        "transcription_status": "transcribed",
        "translation_status": "translated",
        "vocabulary": vocabulary,
        "segments": transcript_result.get("segments", []),
    }

    if dry_run:
        lesson["status"] = "dry_run"

    if output_path:
        with open(output_path, "w") as f:
            json.dump(lesson, f, ensure_ascii=False, indent=2)

    return lesson


def pipeline_from_catalog_entry(entry: dict) -> dict:
    """
    Process a lesson from catalog entry format.
    """
    audio_path = entry.get("audio_url", "")
    if audio_path.startswith("data/"):
        audio_path = audio_path

    level = entry.get("level", "A1")

    return pipeline(audio_path, level=level)


class PipelineBuilder:
    """
    Builder pattern for constructing pipeline with custom stages.
    """

    def __init__(self):
        self.stages = []
        self.config = {}

    def with_transcription(self, provider="groq", model="whisper-large-v3-turbo"):
        self.config["transcription"] = {"provider": provider, "model": model}
        return self

    def with_translation(self, backend="libretranslate"):
        self.config["translation"] = {"backend": backend}
        return self

    def with_vocabulary(self, level="A2"):
        self.config["vocabulary"] = {"level": level}
        return self

    def build(self):
        return Pipeline(self.config)


class Pipeline:
    """
    Configurable pipeline execution.
    """

    def __init__(self, config: dict):
        self.config = config

    def execute(self, input_path: str, output_path: Optional[str] = None):
        return pipeline(input_path, output_path, dry_run=False)


def main():
    parser = argparse.ArgumentParser(
        description="Transcription pipeline for Latvian audio"
    )
    parser.add_argument("--input", help="Input MP3 file")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--batch", action="store_true", help="Batch mode")
    parser.add_argument("--input-dir", help="Input directory for batch processing")
    parser.add_argument("--output-dir", help="Output directory for batch results")
    parser.add_argument("--level", default="A1", help="A1 or A2")
    parser.add_argument(
        "--dry-run", action="store_true", help="Dry run without API calls"
    )

    args = parser.parse_args()

    if args.batch and args.input_dir:
        input_dir = Path(args.input_dir)
        output_dir = (
            Path(args.output_dir) if args.output_dir else input_dir.parent / "output"
        )
        output_dir.mkdir(parents=True, exist_ok=True)

        for mp3_file in input_dir.glob("*.mp3"):
            output_file = output_dir / f"{mp3_file.stem}.json"
            result = pipeline(
                str(mp3_file),
                str(output_file),
                level=args.level,
                dry_run=args.dry_run,
            )
            print(f"Processed: {mp3_file.name} -> {output_file.name}")

    elif args.input:
        result = pipeline(
            args.input,
            args.output,
            level=args.level,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

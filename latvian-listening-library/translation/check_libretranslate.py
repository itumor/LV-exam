#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

import requests


def fail(message: str) -> None:
    print(f"LibreTranslate check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:5000")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    try:
        languages_response = requests.get(f"{base_url}/languages", timeout=10)
        languages_response.raise_for_status()
        languages = languages_response.json()
    except requests.RequestException as exc:
        fail(f"{base_url} is not reachable or /languages failed: {exc}")
    except ValueError as exc:
        fail(f"/languages returned invalid JSON: {exc}")

    codes = {item.get("code") for item in languages if isinstance(item, dict)}
    if "lv" not in codes:
        fail('Latvian source language "lv" is not available.')
    if "en" not in codes:
        fail('English target language "en" is not available.')

    lv_entry = next((item for item in languages if item.get("code") == "lv"), {})
    targets = set(lv_entry.get("targets") or [])
    if targets and "en" not in targets:
        fail("LibreTranslate reports that lv -> en is not supported.")

    try:
        response = requests.post(
            f"{base_url}/translate",
            json={"q": "Labdien! Kā jums klājas?", "source": "lv", "target": "en", "format": "text"},
            timeout=30,
        )
        response.raise_for_status()
        translated = response.json().get("translatedText", "").strip()
    except requests.RequestException as exc:
        fail(f"test translation request failed: {exc}")
    except ValueError as exc:
        fail(f"test translation returned invalid JSON: {exc}")

    if not translated:
        fail("test translation returned empty output.")

    print(f"LibreTranslate is ready at {base_url}. Test translation: {translated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

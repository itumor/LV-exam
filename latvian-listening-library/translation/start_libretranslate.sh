#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH."
  echo "Fallback: pip install libretranslate && libretranslate"
  exit 1
fi

docker compose up -d
echo "LibreTranslate starting at http://localhost:5000"

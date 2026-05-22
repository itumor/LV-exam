#!/bin/sh
set -e
chown -R appuser:appgroup /app/data 2>/dev/null || true
exec su-exec appuser python server.py

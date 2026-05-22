#!/bin/sh
set -e
# Fix volume permissions (Fly.io mounts volume as root-owned)
chown -R appuser:appgroup /app/data 2>/dev/null || true
# Verify appuser can write before dropping privileges; fall back to root if not
if su-exec appuser sh -c "test -w /app/data" 2>/dev/null; then
    exec su-exec appuser python /app/server.py
else
    echo "[entrypoint] Warning: /app/data not writable by appuser, running as root" >&2
    exec python /app/server.py
fi

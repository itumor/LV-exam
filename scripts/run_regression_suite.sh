#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest discover -s tests/server -p 'test_*.py'
node --test tests/contracts/release-contracts.test.cjs
# T-061 — PWA service-worker behaviour (cache routes, LRU eviction,
# offline clip retrieval, stale-while-revalidate).
node --test tests/pwa-sw.test.js
npx playwright test

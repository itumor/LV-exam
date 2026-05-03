#!/usr/bin/env bash
set -euo pipefail

python3 -m unittest discover -s tests/server -p 'test_*.py'
node --test tests/contracts/release-contracts.test.cjs
npx playwright test

#!/usr/bin/env bash
# Start CALS on http://127.0.0.1:8000
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m uvicorn cals.app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" "$@"

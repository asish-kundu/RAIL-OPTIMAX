#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -q -r backend/requirements.txt
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 >/tmp/rail-optimax-occ.log 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
xdg-open http://127.0.0.1:8000 >/dev/null 2>&1 || true
wait "$PID"

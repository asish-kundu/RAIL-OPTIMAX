# RAIL-OPTIMAX OCC Frontend

The dashboard now uses the FastAPI telemetry service as the source of truth for the live corridor schematic.

## Live map flow

1. `backend/services/telemetry.py` owns one simulation clock per backend process.
2. `GET /trains/live` returns an immediate snapshot for first paint / fallback.
3. `WS /ws/live-telemetry` streams one shared corridor update every second.
4. `frontend/js/map.js` maps `current_km` onto the supplied interlocking SVG, draws active possessions on the correct track, and renders every train marker from backend telemetry.
5. Clicking a train shows train number, direction, KM, current/next station, effective speed, delay and block state.

The feed is **project telemetry simulation**, not a connection to Indian Railways' production signalling/interlocking systems or a third-party live train API. This keeps the prototype safe and deterministic while demonstrating the intended OCC workflow.

## Run

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000/`.

## Verify

- `GET /health`
- `GET /trains/live`
- WebSocket: `ws://127.0.0.1:8000/ws/live-telemetry`

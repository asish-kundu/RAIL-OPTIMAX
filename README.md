# RAIL-OPTIMAX — SIH26027 OCC Prototype v13

AI-powered automatic block planning and live railway control-room **decision-support simulation** using the supplied custom corridor data and custom SVG schematic.

## What is live in this build

- **AI-1 PLAN** — maintenance-aware schedule generation with OR-Tools CP-SAT when available and deterministic fallback otherwise.
- **AI-2 ADAPT** — emergency possession injection, safety validation and schedule regeneration.
- **AI-3 MANAGE** — closed-loop real-time controller producing per-train HOLD, SPEED_REGULATION, BLOCK_APPROACH and REROUTE_VIA_LOOP controls.
- **Telemetry** — applies AI-3 controls before each movement tick, then re-evaluates AI-3 after movement.
- **Safety invariants** — active possession protection, directional block approach logic and track-specific signal aspects.
- **Persistence** — atomic JSON runtime snapshot for restart recovery when the host provides persistent storage.
- **WebSocket** — `/ws/live-telemetry` continuously publishes the authoritative OCC snapshot.
- **Frontend** — the supplied custom corridor SVG is preserved; live operational overlays are rendered on top of it.
- **Fallback presentation mode** — if the backend disappears, the existing local presentation simulator can continue the UI demonstration.

## Architecture

```text
Custom JSON Data
      |
      v
Operational State <---- atomic runtime snapshot
      |
      +--> AI-1 PLAN
      |       |
      |       v
      +--> AI-2 ADAPT <---- emergency event
      |       |
      |       v
      +--> AI-3 MANAGE
              |
              v
        Control Decisions
              |
              v
       Telemetry Simulator
              |
              v
        AI-3 re-evaluation
              |
              +---- WebSocket ----> OCC frontend
```

This is a **simulation/decision-support prototype**. It does not connect to Indian Railways signalling, COA, TMS, SMMS, TDMS or live train-location systems and must not be represented as a safety-certified railway control system.

## Local development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`.

## Useful endpoints

- `GET /health` — service/control-loop health
- `GET /api/state` — authoritative OCC snapshot
- `GET /ai/status` — AI-1/2/3 status
- `GET /ai/manage` — current AI-3 evaluation
- `GET /ai/manage/conflicts` — conflict/advisory/control feed
- `GET /ai/manage/health` — AI-3 health
- `POST /ai/plan` — generate AI-1 plan
- `POST /ai/adapt/inject-emergency` — inject simulated emergency maintenance
- `POST /operator/decision` — record operator decision in audit log
- `POST /operator/reset-simulation` — restore custom seed state
- `WS /ws/live-telemetry` — live telemetry stream

## Runtime configuration

`RAILOPTIMAX_STATE_FILE`
: Optional path for the atomic runtime snapshot. Use a persistent mounted path on a host where restart recovery is required.

`RAILOPTIMAX_ALLOWED_ORIGINS`
: Comma-separated browser origins. Default is `*` for prototype/demo use. Set this to the real frontend origin for a restricted deployment.

## Verification

The build includes deterministic tests for:

- AI-3 HOLD control being applied to telemetry.
- Direction-aware block protection: a block behind a train is not treated as an approach.
- Track-specific UP/DN signal aspects.
- Repeated control-loop ticks keeping trains out of active possessions.
- A 1000-tick, 20-train stress simulation.

Run:

```bash
python3 -m unittest discover -s backend/tests -v
python3 -m backend.scripts.stress_simulation
```

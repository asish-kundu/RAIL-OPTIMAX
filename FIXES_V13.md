# RAIL-OPTIMAX v13 — AI-3 Closed-Loop Hardening

## Root causes found in v12

1. **AI-3 was advisory-only in the telemetry loop.** The simulator moved trains from nominal/base speed and did not consume AI-3's per-train recommendation before movement.
2. **Directional block logic was incomplete.** A maintenance block behind a train could still be treated as an approaching block because absolute distance was used.
3. **Track-specific signalling was flattened.** A block on one custom track could make the station signal appear blocked without preserving UP/DN aspect state.
4. **`/ai/manage/conflicts` was disconnected from authoritative runtime state.** The legacy route could fall back to reading the seed JSON instead of the live state.
5. **Runtime state was process-only.** A server restart reset train positions, active blocks and AI state.
6. **Custom maintenance records contained inconsistent block assignments/locations.** Assigned block IDs did not always match the task's KM range.
7. **The health endpoint expected `active_blocks` from an internal state structure that did not contain that field after the persistence refactor.** This caused HTTP 500 during verification.

## v13 changes

- AI-3 now returns a `controls` map keyed by train number.
- Telemetry evaluates AI-3 **before** movement, applies the control, moves the train, then evaluates AI-3 again.
- HOLD, speed regulation, active block protection and loop-routing instructions are enforced in the simulation.
- Predictive same-direction headway uses closing speed and an approximate braking/reaction envelope.
- Block approach uses the correct directional entry point and never flags a block behind the train.
- Loop sections from the custom network data can produce `REROUTE_VIA_LOOP` decisions.
- Signal output now contains separate `UP_LINE` and `DN_LINE` aspects.
- `/ai/manage/conflicts` and `/ai/manage/health` use authoritative runtime state.
- Atomic runtime snapshots allow recovery after process restart when the host provides persistent storage.
- Added simulation reset endpoint.
- Added configurable CORS origins.
- Normalized custom maintenance task/block assignments.
- Added AI-3 visual states to the existing map overlay without replacing the supplied map artwork.
- Added deterministic safety tests and a 1000-tick stress test.

## Verification performed

- Python compilation: PASS
- JavaScript syntax checks: PASS
- 4 deterministic safety/control tests: PASS
- 1000-tick / 20-train stress run: PASS
- FastAPI `/health`: 200
- `/api/state`: 200
- `/ai/status`: 200
- `/ai/manage`: 200
- `/ai/manage/conflicts`: 200
- `/ai/manage/health`: 200
- Emergency injection endpoint: 200; unsafe possession correctly remained `PENDING_SAFETY` when trains were inside the safety envelope.
- WebSocket `/ws/live-telemetry`: verified with 20 trains and AI-3 closed-loop state.
- Restart recovery: verified using the runtime snapshot.

## Scope

This remains a custom-data SIH decision-support simulator. It is not railway signalling software and does not command real trains or connect to operational railway systems.

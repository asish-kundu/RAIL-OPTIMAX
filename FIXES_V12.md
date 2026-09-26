# RAIL-OPTIMAX v12 — Verified Fix Build

## Fixes in this build
- AI-3 conflict cards now use the matching AI-3 advisory action instead of a generic hold message.
- AI-3 separates spatial separation (km) from time headway (minutes).
- AI-3 block-approach logic uses block entry for UP and block exit for DN movements.
- AI-3 advisories are deduplicated per train/action in the backend.
- Dashboard hides a duplicate advisory card when a conflict card already represents the same train.
- Operator ACCEPT / MANUAL OVERRIDE acknowledgements remain hidden until that live conflict clears.
- Train labels on the custom schematic are vertically offset when trains are close together, reducing visual overlap.
- A real local LightGBM prototype model artifact is bundled for AI-1 priority scoring, trained only on deterministic synthetic data.
- AI-1 retains OR-Tools CP-SAT when available and the deterministic fallback when it is unavailable.

## Verification
- FastAPI `/health`: 200
- `/api/state`: 200
- WebSocket `/ws/live-telemetry`: verified; 20 trains, AI-3 conflicts/advisories delivered
- AI-3 engine test: 3 conflicts / 5 advisories on seeded runtime
- LightGBM model load/inference: verified
- JavaScript syntax checks: passed for map.js, dashboard.js, app.js
- Python compilation checks: passed for backend services/routes
- ZIP integrity: verified after packaging

This is a SIH prototype / decision-support simulator, not safety-certified railway signalling software.

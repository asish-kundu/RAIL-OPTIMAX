# RAIL-OPTIMAX — one-URL presentation deployment

## What changed in v9
- One authoritative WebSocket telemetry stream drives the live map and AI-3 panel.
- Removed the initial REST telemetry fetch and the 5-second AI-3 polling loop.
- Management counters and train schedule panel are now telemetry-driven instead of hardcoded.
- Existing custom corridor SVG is preserved; only dynamic overlays are added.
- Backend remains a single FastAPI + static frontend service.
- Presentation fallback remains available if the backend becomes unreachable.

## Cloud presentation
Deploy the repository as a single Docker web service. The container automatically starts FastAPI and serves both frontend and backend from the same URL.

Open that URL during the presentation. Do not open a terminal or run uvicorn manually.

## Local one-click fallback
```bash
./START_PRESENTATION.sh
```
This is only for local development. It creates the environment, installs dependencies, starts FastAPI and opens the browser.

## Presentation mode
The **Presentation** button can deliberately switch to the local deterministic simulator. It is visibly labelled and is not presented as a real railway feed.

## Operational flow
```text
Custom JSON data
   -> Operational State
   -> AI-1 PLAN
   -> AI-2 ADAPT
   -> AI-3 MANAGE
   -> Safety validation
   -> WebSocket telemetry
   -> Existing custom SVG + live overlays
```

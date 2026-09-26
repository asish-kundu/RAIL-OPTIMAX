# RAIL-OPTIMAX presentation mode

## One-time deployment
Deploy this repository as a single Docker web service. The service exposes the frontend and FastAPI backend from the same URL and has a `/health` endpoint.

After deployment, the presentation only needs the browser URL. No terminal, Python environment, uvicorn command or local server startup is required.

## Resilience during the presentation
The frontend has two layers:

1. **Backend LIVE mode** — WebSocket `/ws/live-telemetry` is authoritative. AI-1/AI-2/AI-3 run in the FastAPI process.
2. **Presentation fallback** — if the backend becomes unavailable after the page is loaded, the UI automatically switches to a deterministic local simulation. Trains keep moving, the custom schematic remains unchanged, AI-3 conflicts continue to update, AI-1 plan generation works, and emergency input creates a visible AI-2 event.

This fallback is deliberately labelled `PRESENTATION MODE`; it must never be represented as a real railway data feed.

## Recommended demo sequence
1. Open the deployed URL.
2. Show 20 live trains moving on the custom 2D schematic.
3. Click a train and show KM/speed/station/block state.
4. Click **Generate AI Plan** and show AI-1 output.
5. Enter an emergency KM and duration; submit it and show the block appearing live.
6. Point to AI-3 conflict/advisory cards and signal changes.
7. If the network/server drops, continue the presentation; the UI will visibly switch to `PRESENTATION MODE` rather than freeze.

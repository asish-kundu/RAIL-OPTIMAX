# v24 — physical train/track alignment and route-state consistency

- Fixed loop train rendering to use authoritative `route_control.loop_progress_km` rather than inferring loop position from corridor `current_km`.
- `DIVERSION_PENDING` remains on the main track until loop entry; `ON_LOOP` moves along the lower loop path; `REJOINED` returns to the main-line centerline.
- Train labels now expose HOLD / SPEED REGULATION / ON LOOP state and loop progress.
- Train accessibility labels now identify direction and active route/loop.
- Preserved the uploaded custom corridor SVG and all existing station/route geometry.
- Frontend service-worker cache bumped to v24.
- This remains a simulated/local OCC demonstrator.

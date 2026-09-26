# v21 — 5+5 OCC traffic + visible physical loop routing

- Reduced the simulated corridor to 10 trains total: 5 UP + 5 DN.
- Preserved the original custom corridor SVG/map geometry.
- Made the left train board show 5 UP and 5 DN with group labels and scroll.
- Added deterministic active demo possessions B-106 (DN) and B-108 (UP).
- Added real loop exit points and map coordinates to LOOP-1/LOOP-2.
- AI-3 reroute controls now create a real route-control state and advance the train through a loop before rejoining the main line.
- Frontend renders an ON_LOOP train on the lower loop path rather than leaving it on the main track.
- Reroute overlay is aligned with the same lower loop path used by the train marker.
- Old persisted 20-train runtime state is invalidated by bumping the runtime state schema.
- Fixed frontend script cache-busting to v21.

This remains a simulated/local OCC demonstrator, not a railway signalling/control system.

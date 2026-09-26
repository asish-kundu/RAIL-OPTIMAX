# v22 — canonical 5+5 traffic seed / stale runtime recovery

- Fixed stale persisted runtime state causing the UI to show only 2 trains and 5 stations.
- Runtime schema bumped to 5.
- Persisted state is accepted only when it contains the canonical 10 trains (5 UP + 5 DN) and the full 11-station corridor.
- Any stale safety-test/demo snapshot is rejected and the immutable 10-train seed is restored.
- Preserved physical loop routing for one UP and one DN train so lower loop tracks remain visibly occupied.
- Preserved custom corridor map geometry and AI-3 closed-loop logic.
- Frontend cache version bumped to v22.

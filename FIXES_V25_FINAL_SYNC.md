# RAIL-OPTIMAX v25 Final Sync Fix

- AI-3 dashboard now uses the latest telemetry snapshot as the authoritative physical train state when fresh telemetry is available.
- Stale `/ai/manage` conflict cards are rejected when their leading/trailing order no longer matches the live UP/DN positions.
- AI-3 actual speed displayed in the decision center is taken from the live train state, preventing HOLD/0 km/h vs roster-speed mismatches.
- Persisted runtime snapshots normalize actual/effective/commanded speed on load and reject non-canonical train/station profiles as before.
- The 5-UP + 5-DN roster is compacted so both groups are visible in the left OCC panel without changing the map geometry.
- Service-worker cache version/query strings bumped to v25.
- Original custom corridor SVG and route geometry are unchanged.

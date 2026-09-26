# RAIL-OPTIMAX v14 — AI-3 Dashboard Fix

## Root cause
The AI-3 Decision Center frontend referenced `acknowledgedDecisionIds` without declaring it. Every live telemetry update therefore raised a browser `ReferenceError` inside `updateFromTelemetry()`. The panel stayed on the initial “Scanning live conflicts and generating operator suggestions...” state even though the backend was producing AI-3 controls, conflicts and advisories.

## Fixes
- Declared `const acknowledgedDecisionIds = new Set()`.
- Added an authoritative AI-3 refresh path using `GET /ai/manage`.
- Added a 3-second resilient refresh fallback so the decision center does not depend solely on the map CustomEvent bridge.
- Used `Promise.allSettled()` so an optional AI-1 coordination endpoint failure cannot hide AI-3 suggestions.
- Bumped the service-worker cache and JS asset versions to prevent stale dashboard JavaScript from remaining cached in the browser.

## Backend verification
The backend was started locally and verified:
- `/health` → 200, AI-3 conflicts and controls present.
- `/ai/manage` → 200, returned live controls, conflicts and advisories.
- Python compilation → PASS.
- JavaScript syntax checks → PASS.

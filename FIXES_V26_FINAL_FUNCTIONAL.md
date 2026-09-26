# RAIL-OPTIMAX v26 — Functional OCC planning

- Train Schedule now shows source → destination for every train.
- AI Planning output now renders a train-by-train operational list with source, destination, action, delay, KM, route status and reason.
- AI-3 ACCEPT executes the current live AI-3 control command for the affected train, bounded by the controller safety command, and writes an audit event.
- Original custom map geometry is unchanged.
- Cache version bumped to v26.

- AI-3 controls now carry stable conflict/advisory ids so ACCEPT resolves the exact recommendation.
- ACCEPT returns execution status and the UI reports whether the live command was applied.

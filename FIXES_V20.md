# RAIL-OPTIMAX v20

- Fixed AI-3 reroute logic so a loop must be ahead of the train AND before the protected possession; loops inside/behind a block are rejected.
- Enforced single-loop capacity during each AI-3 evaluation to prevent multiple trains being assigned to the same one-slot loop.
- Added real reroute lifecycle: DIVERSION_PENDING -> ON_LOOP -> REJOINED.
- Telemetry keeps rerouted trains protected from the active possession while they are on the diversion.
- Map now moves the train marker onto the reroute overlay when it reaches the loop entry; it is not just a cosmetic dashed line.
- Reroute overlay shows entry-to-rejoin diversion and train/loop/block labels.
- Fixed braking-distance calculation to use configured reaction time.
- Prioritised affected/rerouted trains in the live train panel so operationally important trains are visible first.
- Preserved the original custom corridor SVG and route/station geometry.

"""Run the custom OCC control loop through repeated ticks without external feeds."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import backend.services.runtime as runtime_module
from backend.services.runtime import OperationalState
from backend.services.telemetry import TelemetrySimulator


async def main() -> None:
    original_state_file = runtime_module.STATE_FILE
    with tempfile.TemporaryDirectory(prefix="railopt-stress-") as td:
        runtime_module.STATE_FILE = Path(td) / "runtime_state.json"
        await OperationalState.reset()
        for tick in range(1000):
            await TelemetrySimulator.step()
            state = await OperationalState.read()
            for train in state["trains"]:
                km = float(train.get("current_km", 0))
                speed = float(train.get("effective_speed_kmh", 0))
                assert 0.0 <= km <= 25.0, (tick, train["train_no"], km)
                assert speed >= 0.0, (tick, train["train_no"], speed)
                for block in state["blocks"]:
                    if block.get("status") != "Active" or block.get("target_track") not in (None, train.get("track")):
                        continue
                    if float(block["location_from_km"]) <= km <= float(block["location_to_km"]):
                        raise AssertionError(f"Train entered active block at tick {tick}: {train['train_no']}")
        print("STRESS_OK ticks=1000 trains=20")
    runtime_module.STATE_FILE = original_state_file


if __name__ == "__main__":
    asyncio.run(main())

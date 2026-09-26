import asyncio
import copy
import json
import tempfile
import unittest
from pathlib import Path

from backend.services.manage import TrafficManagerAI3
from backend.services.runtime import OperationalState
from backend.services.telemetry import TelemetrySimulator


NETWORK = {
    "length_km": 25,
    "stations": [
        {"id": "S-1", "code": "S1", "name": "S-1", "km": 0},
        {"id": "S-2", "code": "S2", "name": "S-2", "km": 2.5},
        {"id": "S-3", "code": "S3", "name": "S-3", "km": 5},
        {"id": "S-4", "code": "S4", "name": "S-4", "km": 7.5},
        {"id": "S-5", "code": "S5", "name": "S-5", "km": 10},
    ],
    "tracks": ["UP_LINE", "DN_LINE"],
    "safety": {"min_headway_km": 1.0},
    "loop_sections": [{"id": "LOOP-1", "station": "S-4", "capacity": 1}],
}


class OperationalSafetyTests(unittest.TestCase):
    def test_block_behind_does_not_trigger_approach(self):
        trains = [{"train_no": "T1", "current_km": 15, "speed_kmh": 60, "effective_speed_kmh": 60, "direction": "UP", "track": "UP_LINE"}]
        blocks = [{"block_id": "B1", "location_from_km": 9, "location_to_km": 10, "target_track": "UP_LINE", "status": "Active"}]
        result = TrafficManagerAI3.evaluate(trains, blocks, NETWORK)
        self.assertFalse(any(a.get("block_id") == "B1" for a in result["advisories"]))

    def test_ai3_hold_is_applied_to_telemetry(self):
        trains = [
            {"train_no": "LEAD", "current_km": 5.5, "speed_kmh": 20, "effective_speed_kmh": 20, "direction": "UP", "track": "UP_LINE"},
            {"train_no": "TRAIL", "current_km": 5.0, "speed_kmh": 80, "effective_speed_kmh": 80, "direction": "UP", "track": "UP_LINE"},
        ]
        result = TrafficManagerAI3.evaluate(trains, [], NETWORK)
        self.assertEqual(result["controls"]["TRAIL"]["action"], "HOLD")

    def test_signal_aspects_are_track_specific(self):
        trains = []
        blocks = [{"block_id": "B1", "location_from_km": 4.5, "location_to_km": 5.5, "target_track": "UP_LINE", "status": "Active"}]
        result = TrafficManagerAI3.evaluate(trains, blocks, NETWORK)
        s3 = next(x for x in result["signals"] if x["station_id"] == "S-3")
        self.assertEqual(s3["aspects"]["UP_LINE"], "RED")
        self.assertNotEqual(s3["aspects"]["DN_LINE"], "RED")

    def test_repeated_simulation_steps_keep_trains_out_of_active_block(self):
        async def scenario():
            old = {
                "loaded": OperationalState._loaded,
                "trains": copy.deepcopy(OperationalState._trains),
                "blocks": copy.deepcopy(OperationalState._blocks),
                "network": copy.deepcopy(OperationalState._network),
                "maintenance": copy.deepcopy(OperationalState._maintenance),
                "events": copy.deepcopy(OperationalState._events),
                "ai1": copy.deepcopy(OperationalState._ai1_plan),
                "ai3": copy.deepcopy(OperationalState._ai3),
                "sequence": OperationalState._sequence,
                "started": OperationalState._started_at,
            }
            try:
                OperationalState._loaded = True
                OperationalState._network = copy.deepcopy(NETWORK)
                OperationalState._blocks = [{"block_id": "B1", "location_from_km": 8, "location_to_km": 9, "target_track": "UP_LINE", "status": "Active"}]
                OperationalState._trains = [{"train_no": "T1", "current_km": 7.0, "speed_kmh": 90, "direction": "UP", "track": "UP_LINE", "delay_minutes": 0}]
                OperationalState._maintenance = []
                OperationalState._events = []
                for _ in range(20):
                    await TelemetrySimulator.step()
                    train = OperationalState._trains[0]
                    self.assertFalse(8 <= float(train["current_km"]) <= 9)
            finally:
                OperationalState._loaded = old["loaded"]
                OperationalState._trains = old["trains"]
                OperationalState._blocks = old["blocks"]
                OperationalState._network = old["network"]
                OperationalState._maintenance = old["maintenance"]
                OperationalState._events = old["events"]
                OperationalState._ai1_plan = old["ai1"]
                OperationalState._ai3 = old["ai3"]
                OperationalState._sequence = old["sequence"]
                OperationalState._started_at = old["started"]

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()

class RuntimeLifecycleTests(unittest.TestCase):
    def test_block_window_handles_expiry_and_cross_midnight(self):
        from datetime import datetime
        cls = OperationalState
        self.assertEqual(cls._window_state("20:30", "21:30", datetime(2026, 9, 25, 22, 47)), "Completed")
        self.assertEqual(cls._window_state("22:00", "23:00", datetime(2026, 9, 25, 22, 47)), "Active")
        self.assertEqual(cls._window_state("23:00", "01:00", datetime(2026, 9, 25, 22, 47)), "Planned")
        self.assertEqual(cls._window_state("23:00", "01:00", datetime(2026, 9, 25, 23, 30)), "Active")
        # A time-only recurring window is active again after midnight; expiry is
        # determined when the next occurrence's end boundary is crossed.
        self.assertEqual(cls._window_state("23:00", "01:00", datetime(2026, 9, 26, 0, 30)), "Active")
        self.assertEqual(cls._window_state("23:00", "01:00", datetime(2026, 9, 26, 1, 30)), "Planned")

    def test_up_line_leader_is_higher_km(self):
        trains = [
            {"train_no": "A", "current_km": 0.9, "speed_kmh": 100, "effective_speed_kmh": 100, "direction": "UP", "track": "UP_LINE"},
            {"train_no": "B", "current_km": 0.7, "speed_kmh": 45, "effective_speed_kmh": 45, "direction": "UP", "track": "UP_LINE"},
        ]
        result = TrafficManagerAI3.evaluate(trains, [], NETWORK)
        conflict = result["conflicts"][0]
        self.assertEqual(conflict["leading_train"], "A")
        self.assertEqual(conflict["trailing_train"], "B")
        self.assertEqual(result["controls"]["B"]["action"], "HOLD")

    def test_ai3_control_updates_actual_speed_fields(self):
        async def scenario():
            old = {
                "loaded": OperationalState._loaded,
                "trains": copy.deepcopy(OperationalState._trains),
                "blocks": copy.deepcopy(OperationalState._blocks),
                "network": copy.deepcopy(OperationalState._network),
                "maintenance": copy.deepcopy(OperationalState._maintenance),
                "events": copy.deepcopy(OperationalState._events),
                "ai1": copy.deepcopy(OperationalState._ai1_plan),
                "ai3": copy.deepcopy(OperationalState._ai3),
                "sequence": OperationalState._sequence,
                "started": OperationalState._started_at,
            }
            try:
                OperationalState._loaded = True
                OperationalState._network = copy.deepcopy(NETWORK)
                OperationalState._blocks = []
                OperationalState._trains = [
                    {"train_no": "LEAD", "current_km": 5.5, "speed_kmh": 20, "effective_speed_kmh": 20, "direction": "UP", "track": "UP_LINE"},
                    {"train_no": "TRAIL", "current_km": 5.0, "speed_kmh": 80, "effective_speed_kmh": 80, "direction": "UP", "track": "UP_LINE"},
                ]
                OperationalState._maintenance = []
                await TelemetrySimulator.step()
                trail = next(t for t in OperationalState._trains if t["train_no"] == "TRAIL")
                self.assertEqual(trail["control_action"], "HOLD")
                self.assertEqual(float(trail["actual_speed_kmh"]), 0.0)
                self.assertEqual(float(trail["effective_speed_kmh"]), 0.0)
                self.assertEqual(float(trail["commanded_speed_kmh"]), 0.0)
            finally:
                OperationalState._loaded = old["loaded"]
                OperationalState._trains = old["trains"]
                OperationalState._blocks = old["blocks"]
                OperationalState._network = old["network"]
                OperationalState._maintenance = old["maintenance"]
                OperationalState._events = old["events"]
                OperationalState._ai1_plan = old["ai1"]
                OperationalState._ai3 = old["ai3"]
                OperationalState._sequence = old["sequence"]
                OperationalState._started_at = old["started"]
        asyncio.run(scenario())

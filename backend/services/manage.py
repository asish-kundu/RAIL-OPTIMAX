"""AI-3 MANAGE: deterministic, safety-first live traffic controller.

The engine is intentionally explainable for the SIH prototype.  It produces
an actionable control for every train that needs intervention; telemetry then
applies that control on the next simulation tick and AI-3 is evaluated again.
"""
from __future__ import annotations

from typing import Any, Dict, List
import math
import networkx as nx


class TrafficManagerAI3:
    DEFAULT_SAFE_SPATIAL_HEADWAY_KM = 1.0
    DEFAULT_WARNING_SPATIAL_HEADWAY_KM = 1.8
    DEFAULT_REACTION_SECONDS = 30.0
    DEFAULT_DECEL_KMH_PER_S = 0.8
    DEFAULT_MAX_CONTROL_SPEED_KMH = 40.0

    @classmethod
    def build_corridor_graph(cls, network: Dict[str, Any]) -> nx.DiGraph:
        graph = nx.DiGraph()
        stations = network.get("stations", [])
        for a, b in zip(stations, stations[1:]):
            dist = float(b["km"]) - float(a["km"])
            graph.add_edge(a["id"], b["id"], distance_km=dist, track="UP_LINE")
            graph.add_edge(b["id"], a["id"], distance_km=dist, track="DN_LINE")
        return graph

    @staticmethod
    def _station_for_km(km: float, stations: List[Dict[str, Any]]) -> Dict[str, Any] | None:
        if not stations:
            return None
        return min(stations, key=lambda s: abs(float(s.get("km", 0)) - km))

    @staticmethod
    def _time_headway_minutes(gap_km: float, speed_kmh: float) -> float | None:
        speed = max(0.0, float(speed_kmh or 0))
        return None if speed <= 0 else (gap_km / speed) * 60.0

    @staticmethod
    def _braking_distance_km(speed_kmh: float, decel_kmh_per_s: float, reaction_seconds: float = DEFAULT_REACTION_SECONDS) -> float:
        """Approximate stopping distance: v*t + v²/(2a), converted to km."""
        v = max(0.0, float(speed_kmh))
        a = max(0.05, float(decel_kmh_per_s))
        reaction_km = v * float(reaction_seconds) / 3600.0
        braking_seconds = v / a
        braking_km = 0.5 * v * braking_seconds / 3600.0
        return reaction_km + braking_km

    @staticmethod
    def _forward_distance(train: Dict[str, Any], point_km: float) -> float:
        km = float(train.get("current_km", 0))
        return point_km - km if train.get("direction", "UP") == "UP" else km - point_km

    @classmethod
    def _choose_loop(cls, train: Dict[str, Any], block: Dict[str, Any], network: Dict[str, Any], trains: List[Dict[str, Any]] | None = None, reserved_loops: set[str] | None = None) -> Dict[str, Any] | None:
        """Choose a loop that is genuinely BEFORE the protected block.

        A loop behind/inside the possession is never a valid diversion. Capacity
        is also respected so two trains cannot be assigned the same single-slot
        loop at the same time.
        """
        loops = network.get("loop_sections", [])
        if not loops:
            return None
        direction = train.get("direction", "UP")
        current_km = float(train.get("current_km", 0))
        entry_km = float(block.get("location_from_km", 0)) if direction == "UP" else float(block.get("location_to_km", 0))
        train_to_block = cls._forward_distance(train, entry_km)
        if train_to_block < 0:
            return None
        occupied = set(reserved_loops or set())
        for other in (trains or []):
            if str(other.get("train_no")) == str(train.get("train_no")):
                continue
            rc = other.get("route_control") or {}
            if rc.get("mode") == "LOOP" and rc.get("via", {}).get("loop_id"):
                occupied.add(rc["via"]["loop_id"])

        candidates = []
        for loop in loops:
            loop_id = loop.get("id")
            if not loop_id or loop_id in occupied:
                continue
            capacity = int(loop.get("capacity", 1) or 1)
            if capacity <= 0:
                continue
            station_id = loop.get("station")
            station = next((s for s in network.get("stations", []) if s.get("id") == station_id), None)
            if not station:
                continue
            loop_km = float(station.get("km", 0))
            to_loop = self_distance = abs(loop_km - current_km)
            forward_to_loop = cls._forward_distance(train, loop_km)
            # Loop must lie strictly between the train and the protected block.
            # Keep a small operational margin from the block entry.
            if forward_to_loop < 0 or forward_to_loop >= max(0.0, train_to_block - 0.5):
                continue
            if loop_km >= float(block.get("location_from_km", 0)) and loop_km <= float(block.get("location_to_km", 0)):
                continue
            candidates.append((forward_to_loop, loop, station))

        if not candidates:
            return None
        distance, loop, station = min(candidates, key=lambda x: x[0])
        entry_loop_km = float(station.get("km", 0))
        exit_km = float(loop.get("exit_km", entry_loop_km))
        # The exit must be beyond the protected possession in the train's travel
        # direction; otherwise this is not a real bypass.
        block_exit = float(block.get("location_to_km", entry_km)) if direction == "UP" else float(block.get("location_from_km", entry_km))
        if direction == "UP" and exit_km <= block_exit:
            return None
        if direction == "DN" and exit_km >= block_exit:
            return None
        return {
            "loop_id": loop.get("id"),
            "station_id": station.get("id"),
            "station_code": station.get("code"),
            "entry_km": round(entry_loop_km, 2),
            "exit_km": round(exit_km, 2),
            "block_entry_km": round(entry_km, 2),
            "distance_km": round(distance, 2),
            "capacity": int(loop.get("capacity", 1) or 1),
            "map_y_up": int(loop.get("map_y_up", 150)),
            "map_y_dn": int(loop.get("map_y_dn", 150)),
        }

    @classmethod
    def evaluate(cls, trains: List[Dict[str, Any]], blocks: List[Dict[str, Any]], network: Dict[str, Any]) -> Dict[str, Any]:
        safety = network.get("safety", {})
        safe_km = max(0.1, float(safety.get("min_headway_km", cls.DEFAULT_SAFE_SPATIAL_HEADWAY_KM)))
        warning_km = max(safe_km + 0.5, float(safety.get("warning_headway_km", cls.DEFAULT_WARNING_SPATIAL_HEADWAY_KM)))
        reaction_seconds = float(safety.get("reaction_time_seconds", cls.DEFAULT_REACTION_SECONDS))
        decel = float(safety.get("deceleration_kmh_per_s", cls.DEFAULT_DECEL_KMH_PER_S))
        stations = network.get("stations", [])
        conflicts: List[Dict[str, Any]] = []
        advisories: List[Dict[str, Any]] = []
        controls: Dict[str, Dict[str, Any]] = {}

        # Same physical line + same direction only. UP and DN are separate
        # custom tracks in this prototype and therefore are not compared as a
        # head-on conflict here.
        for track in ("UP_LINE", "DN_LINE"):
            group = [t for t in trains if t.get("track", "UP_LINE") == track]
            group.sort(key=lambda t: float(t.get("current_km", 0)), reverse=(track == "UP_LINE"))
            for lead, trail in zip(group, group[1:]):
                lead_km = float(lead.get("current_km", 0))
                trail_km = float(trail.get("current_km", 0))
                gap = abs(lead_km - trail_km)
                if gap >= warning_km:
                    continue
                lead_speed = max(0.0, float(lead.get("effective_speed_kmh", lead.get("speed_kmh", 0))))
                trail_speed = max(0.0, float(trail.get("effective_speed_kmh", trail.get("speed_kmh", 0))))
                closing_speed = max(0.0, trail_speed - lead_speed)
                predicted_gap_60s = gap - closing_speed * 60.0 / 3600.0
                braking_km = cls._braking_distance_km(trail_speed, decel, reaction_seconds)
                dynamic_safe_km = max(safe_km, min(3.0, braking_km + 0.25))
                critical = gap < dynamic_safe_km or predicted_gap_60s < safe_km
                severity = "CRITICAL" if critical else "WARNING"
                action = "HOLD" if critical else "SPEED_REGULATION"
                target_speed = 0.0 if critical else min(cls.DEFAULT_MAX_CONTROL_SPEED_KMH, lead_speed)
                station = cls._station_for_km(lead_km, stations)
                conflict_id = f"C-{lead['train_no']}-{trail['train_no']}"
                conflict = {
                    "conflict_id": conflict_id,
                    "track": track,
                    "station": station.get("code") if station else "CONTROL SECTION",
                    "leading_train": lead["train_no"],
                    "trailing_train": trail["train_no"],
                    "headway_km": round(gap, 3),
                    "time_headway_minutes": round(cls._time_headway_minutes(gap, trail_speed), 2) if trail_speed > 0 else None,
                    "safe_min_km": round(dynamic_safe_km, 3),
                    "predicted_headway_60s_km": round(predicted_gap_60s, 3),
                    "closing_speed_kmh": round(closing_speed, 2),
                    "severity": severity,
                    "recommended_action": action,
                    "target_speed_kmh": target_speed,
                    "leading_actual_speed_kmh": round(lead_speed, 1),
                    "trailing_actual_speed_kmh": round(trail_speed, 1),
                }
                conflicts.append(conflict)
                advisory = {
                    "advisory_id": f"A-{conflict_id}",
                    "train_no": trail["train_no"],
                    "leading_train": lead["train_no"],
                    "type": action,
                    "target_speed_kmh": target_speed,
                    "severity": severity,
                    "station": conflict["station"],
                    "headway_km": round(gap, 3),
                    "current_speed_kmh": round(trail_speed, 1),
                    "leading_speed_kmh": round(lead_speed, 1),
                    "reason": f"{action.replace('_', ' ').title()} {trail['train_no']} to protect separation behind {lead['train_no']}.",
                }
                advisories.append(advisory)
                current = controls.get(str(trail["train_no"]))
                if current is None or (action == "HOLD" and current.get("action") != "HOLD"):
                    controls[str(trail["train_no"])] = {
                        "action": action,
                        "target_speed_kmh": target_speed,
                        "source": "AI-3",
                        "reason": advisory["reason"],
                        "conflict_id": conflict_id,
                        "advisory_id": advisory["advisory_id"],
                    }

        # Active maintenance possessions. Direction matters: a block behind a
        # train must never be reported as an approach.
        active_blocks = [b for b in blocks if b.get("status") == "Active"]
        reserved_loops: set[str] = set()
        for train in trains:
            track = train.get("track", "UP_LINE")
            direction = train.get("direction", "UP")
            existing_route = train.get("route_control") or {}
            for block in active_blocks:
                # Once a train has been assigned to a validated diversion, keep
                # that route decision stable until it rejoins the main line.
                if existing_route.get("protected_block_id") == block.get("block_id") and existing_route.get("mode") in {"LOOP", "MAIN"}:
                    via = existing_route.get("via") or {}
                    item = {
                        "advisory_id": f"A-ROUTE-{block['block_id']}-{train['train_no']}",
                        "train_no": train["train_no"],
                        "type": "REROUTE_VIA_LOOP",
                        "target_speed_kmh": 40.0,
                        "severity": "WARNING",
                        "station": via.get("station_code") or train.get("next_station_code") or "CONTROL SECTION",
                        "block_id": block["block_id"],
                        "distance_to_block_km": 0.0,
                        "current_speed_kmh": round(float(train.get("effective_speed_kmh", train.get("speed_kmh", 0))), 1),
                        "route_via": via,
                        "reason": f"{train['train_no']} is committed to {via.get('loop_id', 'loop')} around {block['block_id']}."
                    }
                    advisories.append(item)
                    controls[str(train["train_no"])] = {
                        "action": "REROUTE_VIA_LOOP",
                        "target_speed_kmh": 40.0,
                        "source": "AI-3",
                        "reason": item["reason"],
                        "block_id": block["block_id"],
                        "route_via": via,
                        "advisory_id": item["advisory_id"],
                    }
                    continue
                if block.get("target_track") not in (None, track):
                    continue
                start = block.get("location_from_km")
                end = block.get("location_to_km")
                if start is None or end is None:
                    continue
                start, end = float(start), float(end)
                entry = start if direction == "UP" else end
                distance = cls._forward_distance(train, entry)
                inside = start <= float(train.get("current_km", 0)) <= end
                if distance < 0 and not inside:
                    continue
                if inside:
                    action, speed, severity = "HOLD", 0.0, "CRITICAL"
                elif distance <= 1.5:
                    action, speed, severity = "HOLD", 0.0, "CRITICAL"
                elif distance <= 4.0:
                    action, speed, severity = "SPEED_REGULATION", 30.0, "WARNING"
                elif distance <= 8.0:
                    loop = cls._choose_loop(train, block, network, trains, reserved_loops)
                    if loop:
                        reserved_loops.add(str(loop.get("loop_id")))
                    action, speed, severity = ("REROUTE_VIA_LOOP", 40.0, "WARNING") if loop else ("BLOCK_APPROACH", 30.0, "WARNING")
                else:
                    continue
                item = {
                    "advisory_id": f"A-BLOCK-{block['block_id']}-{train['train_no']}",
                    "train_no": train["train_no"],
                    "type": action,
                    "target_speed_kmh": speed,
                    "severity": severity,
                    "station": train.get("next_station_code") or "CONTROL SECTION",
                    "block_id": block["block_id"],
                    "distance_to_block_km": round(max(0.0, distance), 2),
                    "current_speed_kmh": round(float(train.get("effective_speed_kmh", train.get("speed_kmh", 0))), 1),
                    "reason": f"Protect active possession {block['block_id']} at KM {start:g}-{end:g}.",
                }
                if action == "REROUTE_VIA_LOOP":
                    item["route_via"] = loop
                    item["reason"] = f"Route {train['train_no']} via {loop['loop_id']} before {block['block_id']}."
                advisories.append(item)
                rank = {"HOLD": 4, "SPEED_REGULATION": 3, "REROUTE_VIA_LOOP": 2, "BLOCK_APPROACH": 1}
                current = controls.get(str(train["train_no"]))
                if current is None or rank[action] > rank.get(current.get("action"), 0):
                    controls[str(train["train_no"])] = {
                        "action": action,
                        "target_speed_kmh": speed,
                        "source": "AI-3",
                        "reason": item["reason"],
                        "block_id": block["block_id"],
                        "advisory_id": item["advisory_id"],
                        **({"route_via": loop} if action == "REROUTE_VIA_LOOP" else {}),
                    }

        # Track-specific signal aspects. One blocked UP track must not turn the
        # DN signal red in the custom two-track corridor.
        signals = []
        for station in stations:
            km = float(station["km"])
            aspects = {}
            for track in ("UP_LINE", "DN_LINE"):
                blocked = any(
                    b.get("status") == "Active" and b.get("target_track") in (None, track)
                    and b.get("location_from_km") is not None and b.get("location_to_km") is not None
                    and float(b["location_from_km"]) - 0.25 <= km <= float(b["location_to_km"]) + 0.25
                    for b in active_blocks
                )
                near = any(t.get("track") == track and abs(float(t.get("current_km", 0)) - km) < 1.2 for t in trains)
                aspects[track] = "RED" if blocked else "YELLOW" if near else "GREEN"
            signals.append({"station_id": station["id"], "km": km, "aspects": aspects, "aspect": aspects["UP_LINE"]})

        return {
            "engine": "AI-3 MANAGE",
            "status": "ACTIVE",
            "controls": controls,
            "conflicts": conflicts,
            "advisories": advisories,
            "signals": signals,
            "active_conflicts_count": len(conflicts),
            "active_advisories_count": len(advisories),
            "evaluated_train_count": len(trains),
            "control_count": len(controls),
            "controller_mode": "CLOSED_LOOP_SIMULATION",
        }

    @classmethod
    async def evaluate_live(cls) -> Dict[str, Any]:
        from backend.services.runtime import OperationalState
        state = await OperationalState.read()
        result = cls.evaluate(state["trains"], [b for b in state["blocks"] if b.get("status") == "Active"], state["network"])
        def commit(runtime):
            runtime.set_ai3_unlocked(result)
            runtime.append_event_unlocked({"type": "AI3_EVALUATION", "control_count": len(result["controls"]), "conflict_count": len(result["conflicts"])})
            return result
        await OperationalState.mutate(commit)
        return result

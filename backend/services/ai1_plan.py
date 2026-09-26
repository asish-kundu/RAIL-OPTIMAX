"""AI-1 PLAN: maintenance-aware timetable/block optimization.

The prototype deliberately keeps the model explainable: CP-SAT chooses the
minimum additional operating delay needed to keep trains clear of active
possessions and preserve minimum same-line headway. A deterministic planner is
used when OR-Tools is unavailable.
"""
from __future__ import annotations
from typing import Any, Dict, List
from backend.services.priority_engine import calculate_task_priority_score, model_status
from backend.services.runtime import OperationalState

try:
    from ortools.sat.python import cp_model
    HAS_CP_SAT = True
except Exception:
    cp_model = None
    HAS_CP_SAT = False


class AI1Planner:
    MIN_HEADWAY_KM = 1.0
    SPEED_REGULATION_KMH = 40.0
    MAX_DELAY_MIN = 120

    @staticmethod
    def _distance_to_block(train: Dict[str, Any], block: Dict[str, Any]) -> float:
        km = float(train.get("current_km", 0))
        start = float(block.get("location_from_km", 0))
        end = float(block.get("location_to_km", start))
        return max(0.0, start - km) if train.get("direction") == "UP" else max(0.0, km - end)

    @classmethod
    def _affected(cls, train: Dict[str, Any], block: Dict[str, Any]) -> bool:
        if block.get("target_track") not in (None, train.get("track", "UP_LINE")):
            return False
        distance = cls._distance_to_block(train, block)
        return distance <= 8.0

    @staticmethod
    def _baseline_action(train: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        affected = [b for b in blocks if AI1Planner._affected(train, b)]
        if not affected:
            return {"action": "NORMAL", "required_delay": 0, "reason": "No active possession on route."}
        block = min(affected, key=lambda b: AI1Planner._distance_to_block(train, b))
        distance = AI1Planner._distance_to_block(train, block)
        if distance <= 1.5:
            return {"action": "HOLD", "required_delay": 8, "reason": f"Protect {block['block_id']} before entering its safety envelope.", "block_id": block["block_id"]}
        if distance <= 5:
            return {"action": "SPEED_REGULATION", "required_delay": 3, "reason": f"Regulate speed approaching {block['block_id']}.", "block_id": block["block_id"]}
        return {"action": "ROUTE_ADVISORY", "required_delay": 2, "reason": f"Prepare alternate/loop routing around {block['block_id']}.", "block_id": block["block_id"]}

    @classmethod
    async def generate(cls, reason: str = "SCHEDULE_OPTIMIZATION") -> Dict[str, Any]:
        state = await OperationalState.read()
        trains = state["trains"]
        blocks = [b for b in state["blocks"] if b.get("status") == "Active"]
        maintenance = state["maintenance"]
        for task in maintenance:
            task["priority_score"] = calculate_task_priority_score(task)

        actions: List[Dict[str, Any]] = []
        baselines: Dict[str, Dict[str, Any]] = {}
        for train in trains:
            base = cls._baseline_action(train, blocks)
            baselines[str(train["train_no"])] = base
            actions.append({
                "train_no": train["train_no"],
                "train_name": train.get("name", f"Train {train['train_no']}"),
                "source": train.get("origin", "SDAH"),
                "destination": train.get("destination", "BP"),
                "direction": train.get("direction", "UP"),
                "current_km": round(float(train.get("current_km", 0)), 2),
                "current_speed_kmh": round(float(train.get("actual_speed_kmh", train.get("effective_speed_kmh", train.get("speed_kmh", 0))) or 0), 1),
                "action": base["action"],
                "delay_minutes": int(base["required_delay"]),
                "reason": base["reason"],
                "route_status": (train.get("route_control") or {}).get("status", "MAIN_LINE"),
                "loop_id": ((train.get("route_control") or {}).get("via") or {}).get("loop_id"),
                **({"block_id": base["block_id"]} if base.get("block_id") else {}),
            })

        solver_used = "HEURISTIC_FALLBACK"
        if HAS_CP_SAT and actions:
            model = cp_model.CpModel()
            delay_vars: Dict[str, Any] = {}
            for action in actions:
                tid = str(action["train_no"])
                required = int(action["delay_minutes"])
                delay_vars[tid] = model.NewIntVar(required, cls.MAX_DELAY_MIN, f"delay_{tid}")

            # Same-track trains preserve at least MIN_HEADWAY_KM after planned delay.
            # Delay is represented in seconds at the current train speed.
            for track in ("UP_LINE", "DN_LINE"):
                group = [t for t in trains if t.get("track") == track]
                reverse = track == "UP_LINE"
                group.sort(key=lambda t: float(t.get("current_km", 0)), reverse=reverse)
                for lead, trail in zip(group, group[1:]):
                    gap = abs(float(lead.get("current_km", 0)) - float(trail.get("current_km", 0)))
                    if gap >= cls.MIN_HEADWAY_KM:
                        continue
                    # Additional delay on the trailing train is enough to restore separation.
                    speed = max(20.0, float(trail.get("speed_kmh", 50)))
                    seconds_needed = max(0, int(((cls.MIN_HEADWAY_KM - gap) / speed) * 3600))
                    minutes_needed = (seconds_needed + 59) // 60
                    tid = str(trail["train_no"])
                    model.Add(delay_vars[tid] >= min(cls.MAX_DELAY_MIN, minutes_needed))

            # Penalize delay heavily; route advisory is already encoded in the baseline.
            model.Minimize(sum(delay_vars.values()))
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = 1.5
            solver.parameters.num_search_workers = 1
            status = solver.Solve(model)
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                solver_used = "OR-TOOLS_CP-SAT"
                for action in actions:
                    action["delay_minutes"] = int(solver.Value(delay_vars[str(action["train_no"])]) )

        plan = {
            "engine": "AI-1 PLAN",
            "reason": reason,
            "solver": solver_used,
            "generated_at_sequence": state["sequence"],
            "actions": actions,
            "priority_model": model_status(),
            "summary": {
                "affected_trains": sum(1 for a in actions if a["action"] != "NORMAL"),
                "total_planned_delay_minutes": sum(a["delay_minutes"] for a in actions),
                "active_blocks_considered": len(blocks),
                "maintenance_tasks_considered": len(maintenance),
            },
        }

        def commit(runtime):
            runtime.set_ai1_unlocked(plan)
            runtime.append_event_unlocked({"type": "AI1_PLAN_GENERATED", "reason": reason, "summary": plan["summary"]})
            return plan
        await OperationalState.mutate(commit)
        return plan

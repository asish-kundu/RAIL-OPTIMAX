"""AI-2 ADAPT: event-driven emergency maintenance and traffic adaptation."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from backend.services.runtime import OperationalState
from backend.services.safety import SafetyValidator
from backend.services.ai1_plan import AI1Planner
from backend.services.manage import TrafficManagerAI3


class EmergencyAdaptEngine:
    @classmethod
    async def inject_emergency_disruption(
        cls,
        disruption_type: str,
        location_km: float,
        duration_minutes: int,
        target_track: str = "UP_LINE",
        department: str = "Engineering (Track)",
        asset_type: str = "Track Section",
        location_to_km: float | None = None,
        priority: str = "Critical",
        description: str = "Emergency maintenance input",
        requires_power_block: bool = False,
        requires_traffic_block: bool = True,
        ohe_isolated: bool = False,
    ) -> Dict[str, Any]:
        location_km = max(0.0, min(25.0, float(location_km)))
        end_km = location_to_km if location_to_km is not None else location_km + 1.2
        end_km = max(location_km + 0.1, min(25.0, float(end_km)))
        duration_minutes = max(5, min(360, int(duration_minutes)))
        target_track = target_track if target_track in {"UP_LINE", "DN_LINE"} else "UP_LINE"
        state = await OperationalState.read()

        # Unique IDs survive repeated emergency injections without relying on
        # the maintenance list length.
        existing_ids = [str(x.get("block_id", "")) for x in state.get("blocks", [])]
        seq = max([int("".join(c for c in x.split("-")[-1] if c.isdigit()) or 0) for x in existing_ids] + [100]) + 1
        block_id = f"EMG-{seq}"
        now = OperationalState._now_local()
        end_time = now + timedelta(minutes=duration_minutes)
        task_id = f"EMG-TASK-{seq}"
        task = {
            "query_id": task_id,
            "department": department,
            "location_from_km": round(location_km, 2),
            "location_to_km": round(end_km, 2),
            "asset_type": asset_type,
            "maintenance_type": disruption_type,
            "priority": priority,
            "duration_minutes": duration_minutes,
            "preferred_date": now.strftime("%Y-%m-%d"),
            "preferred_window": f"{now.strftime('%H:%M')} - {end_time.strftime('%H:%M')}",
            "resources": "Emergency Response Team",
            "emergency": True,
            "description": description,
            "status": "PENDING_SAFETY",
            "submitted_on": now.strftime("%d %b %Y"),
            "requires_power_block": bool(requires_power_block),
            "requires_traffic_block": bool(requires_traffic_block),
            "assigned_block_id": block_id,
            "priority_score": 100.0,
        }
        block = {
            "block_id": block_id,
            "section": f"KM {location_km:.1f} - {end_km:.1f}",
            "location_from_km": round(location_km, 2),
            "location_to_km": round(end_km, 2),
            "target_track": target_track,
            "start_time": now.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "duration_minutes": duration_minutes,
            "status": "PENDING_SAFETY",
            "approved": False,
            "disruption_type": disruption_type,
            "maintenance_type": disruption_type,
            "asset_type": asset_type,
            "department": department,
            "emergency": True,
            "power_block_required": bool(requires_power_block),
            "requires_power_block": bool(requires_power_block),
            "requires_traffic_block": bool(requires_traffic_block),
            "ohe_isolated": bool(ohe_isolated),
            "train_impact_delay_minutes": 0,
            "bundled_departments": [department],
            "bundled_tasks": [task_id],
        }

        safe, notes = SafetyValidator.validate_block_possession(block, state["trains"])

        def commit(runtime):
            block_copy = dict(block)
            block_copy["status"] = "Active" if safe else "PENDING_SAFETY"
            block_copy["approved"] = bool(safe)
            task_copy = dict(task)
            task_copy["status"] = "Active" if safe else "PENDING_SAFETY"
            runtime.blocks_unlocked().insert(0, block_copy)
            runtime.maintenance_unlocked().insert(0, task_copy)

            affected = []
            for train in runtime.trains_unlocked():
                if train.get("track") != target_track:
                    continue
                km = float(train.get("current_km", 0))
                forward = (location_km - km) if train.get("direction") == "UP" else (km - end_km)
                inside = location_km <= km <= end_km
                if inside or 0 <= forward <= 8.0:
                    affected.append(str(train["train_no"]))
                    if not safe:
                        train["status"] = "HOLD FOR SAFETY REVIEW"

            runtime.append_event_unlocked({
                "type": "AI2_EMERGENCY",
                "block_id": block_id,
                "query_id": task_id,
                "safe": safe,
                "affected_trains": affected,
                "disruption_type": disruption_type,
                "asset_type": asset_type,
                "department": department,
                "target_track": target_track,
            })
            return affected

        affected = await OperationalState.mutate(commit)

        # AI-1 immediately recalculates the maintenance-aware plan. AI-3 is
        # evaluated immediately as well so the map/control desk does not wait
        # for the next telemetry tick to understand the new emergency.
        plan = await AI1Planner.generate(reason=f"AI-2 emergency adaptation for {block_id}")
        ai3 = await TrafficManagerAI3.evaluate_live()
        latest = await OperationalState.read()
        active_block = next((b for b in latest["blocks"] if b.get("block_id") == block_id), block)
        active_task = next((t for t in latest["maintenance"] if t.get("query_id") == task_id), task)

        return {
            "engine": "AI-2 ADAPT",
            "status": "ACTIVATED" if safe else "PENDING_SAFETY",
            "emergency_block": active_block,
            "maintenance_task": active_task,
            "affected_trains": affected,
            "safety_passed": safe,
            "safety_notes": notes,
            "ai1_replanned_schedule": plan,
            "ai3_live_controls": ai3.get("controls", {}),
            "ai3_conflicts": ai3.get("conflicts", []),
            "ai3_advisories": ai3.get("advisories", []),
            "map_application": {
                "block_visible": bool(active_block),
                "signal_recalculated": True,
                "asset_type": asset_type,
                "target_track": target_track,
                "status": active_block.get("status"),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

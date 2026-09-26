"""Authoritative live telemetry clock for the custom railway simulation."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from backend.services.runtime import OperationalState
from backend.services.manage import TrafficManagerAI3


class TelemetrySimulator:
    TICK_SECONDS = 1.0
    SIM_SECONDS_PER_TICK = 8.0
    CAUTION_BUFFER_KM = 1.5
    CORRIDOR_LENGTH_KM = 25.0

    @classmethod
    def _station_context(cls, train: Dict[str, Any], stations):
        if not stations:
            return ({"name": "CONTROL", "code": "CTRL", "km": 0},) * 2
        km = float(train.get("current_km", 0))
        direction = train.get("direction", "UP")
        if direction == "UP":
            current = max((s for s in stations if float(s["km"]) <= km + 0.05), key=lambda s: float(s["km"]), default=stations[0])
            nxt = min((s for s in stations if float(s["km"]) > km + 0.05), key=lambda s: float(s["km"]), default=stations[-1])
        else:
            current = min((s for s in stations if float(s["km"]) >= km - 0.05), key=lambda s: float(s["km"]), default=stations[-1])
            nxt = max((s for s in stations if float(s["km"]) < km - 0.05), key=lambda s: float(s["km"]), default=stations[0])
        return current, nxt

    @classmethod
    def _block_context(cls, train, blocks):
        km = float(train.get("current_km", 0))
        track = train.get("track", "UP_LINE")
        direction = train.get("direction", "UP")
        for block in blocks:
            if block.get("status") != "Active" or block.get("target_track") not in (None, track):
                continue
            start, end = block.get("location_from_km"), block.get("location_to_km")
            if start is None or end is None:
                continue
            start, end = float(start), float(end)
            inside = start <= km <= end
            forward_distance = start - km if direction == "UP" else km - end
            if inside or 0 <= forward_distance <= cls.CAUTION_BUFFER_KM:
                return {
                    "block_id": block["block_id"],
                    "from_km": start,
                    "to_km": end,
                    "relation": "INSIDE_BLOCK" if inside else "APPROACHING_BLOCK",
                    "disruption_type": block.get("disruption_type", "Maintenance possession"),
                }
        return None

    @classmethod
    def enrich_train(cls, train: Dict[str, Any], blocks, stations) -> None:
        km = max(0.0, min(cls.CORRIDOR_LENGTH_KM, float(train.get("current_km", 0))))
        current, nxt = cls._station_context(train, stations)
        block_ctx = cls._block_context(train, blocks)
        train["current_km"] = round(km, 3)
        train["current_station"] = current["name"]
        train["current_station_code"] = current["code"]
        train["next_station"] = nxt["name"]
        train["next_station_code"] = nxt["code"]
        train["block_context"] = block_ctx
        if block_ctx and block_ctx["relation"] == "INSIDE_BLOCK":
            train["operational_state"] = "BLOCK OCCUPIED"
        elif block_ctx:
            train["operational_state"] = "BLOCK APPROACH"
        else:
            train["operational_state"] = "RUNNING"

    @classmethod
    def _safe_block_stop(cls, train, blocks, proposed):
        km = float(train.get("current_km", 0))
        direction = train.get("direction", "UP")
        track = train.get("track", "UP_LINE")
        best = None
        for block in blocks:
            if block.get("status") != "Active" or block.get("target_track") not in (None, track):
                continue
            start, end = block.get("location_from_km"), block.get("location_to_km")
            if start is None or end is None:
                continue
            start, end = float(start), float(end)
            if direction == "UP" and km < start <= proposed:
                stop = max(km, start - cls.CAUTION_BUFFER_KM)
                best = stop if best is None else min(best, stop)
            elif direction == "DN" and km > end >= proposed:
                stop = min(km, end + cls.CAUTION_BUFFER_KM)
                best = stop if best is None else max(best, stop)
        return best

    @classmethod
    async def step(cls) -> None:
        def mutator(runtime):
            network = runtime.network_unlocked()
            stations = network.get("stations", [])
            blocks = runtime.blocks_unlocked()
            active_blocks = [b for b in blocks if b.get("status") == "Active"]
            trains = runtime.trains_unlocked()
            for train in trains:
                nominal = max(0.0, float(train.get("speed_kmh", 50)))
                train.setdefault("effective_speed_kmh", nominal)
                train.setdefault("actual_speed_kmh", train.get("effective_speed_kmh", nominal))
                train.setdefault("commanded_speed_kmh", train.get("effective_speed_kmh", nominal))
                train.setdefault("control_action", "NORMAL")

            # Closed-loop: calculate AI-3 controls from the current state BEFORE
            # moving trains, so a HOLD/speed command is effective immediately.
            controls_result = TrafficManagerAI3.evaluate(trains, active_blocks, network)
            controls = controls_result.get("controls", {})
            runtime.set_ai3_unlocked(controls_result)

            for train in trains:
                train_id = str(train.get("train_no"))
                control = controls.get(train_id, {})
                nominal = max(0.0, float(train.get("speed_kmh", 50)))
                control_action = control.get("action", "NORMAL")
                target = nominal
                if control_action == "HOLD":
                    target = 0.0
                elif control_action in {"SPEED_REGULATION", "BLOCK_APPROACH", "REROUTE_VIA_LOOP"}:
                    target = min(nominal, max(0.0, float(control.get("target_speed_kmh", 40))))

                # Active possession protection remains an absolute invariant even
                # if an AI-3 control is missing or stale.
                direction = train.get("direction", "UP")
                route_control = train.get("route_control") or {}
                via = control.get("route_via") or route_control.get("via")

                # A validated AI-3 reroute becomes a real route-control state.
                # It is not just an advisory drawn on the map.
                if control_action == "REROUTE_VIA_LOOP" and via and route_control.get("mode") != "LOOP":
                    route_control = {
                        "mode": "LOOP",
                        "status": "DIVERSION_PENDING",
                        "via": via,
                        "protected_block_id": control.get("block_id"),
                        "loop_progress_km": 0.0,
                    }
                    train["route_control"] = route_control

                on_loop = route_control.get("mode") == "LOOP" and route_control.get("status") == "ON_LOOP"
                if route_control.get("mode") == "LOOP" and via:
                    entry_km = float(via.get("entry_km", train.get("current_km", 0)))
                    exit_km = float(via.get("exit_km", entry_km))
                    current_km = float(train.get("current_km", 0))
                    if route_control.get("status") == "DIVERSION_PENDING":
                        reached_entry = current_km >= entry_km if direction == "UP" else current_km <= entry_km
                        if reached_entry:
                            current_km = entry_km
                            route_control["status"] = "ON_LOOP"
                            route_control["loop_progress_km"] = 0.0
                            train["route_control"] = route_control
                            on_loop = True
                        else:
                            on_loop = False

                    if on_loop:
                        loop_total = abs(exit_km - entry_km)
                        step_km = target / 3600.0 * cls.SIM_SECONDS_PER_TICK
                        progress = float(route_control.get("loop_progress_km", 0.0)) + step_km
                        if progress >= loop_total:
                            train["current_km"] = round(exit_km, 3)
                            train["effective_speed_kmh"] = round(target, 1)
                            train["actual_speed_kmh"] = round(target, 1)
                            train["commanded_speed_kmh"] = round(target, 1)
                            train["control_action"] = "REROUTE_VIA_LOOP"
                            route_control["status"] = "REJOINED"
                            route_control["loop_progress_km"] = loop_total
                            train["route_control"] = route_control
                            # Rejoin the main line only after the bypass exit.
                            train["status"] = "AI-3 REJOINED MAIN LINE"
                        else:
                            route_control["loop_progress_km"] = round(progress, 4)
                            sign = 1 if direction == "UP" else -1
                            train["current_km"] = round(entry_km + sign * progress, 3)
                            train["effective_speed_kmh"] = round(target, 1)
                            train["actual_speed_kmh"] = round(target, 1)
                            train["commanded_speed_kmh"] = round(target, 1)
                            train["control_action"] = "REROUTE_VIA_LOOP"
                            train["status"] = "AI-3 ON LOOP"
                        # A train on the physical loop is intentionally exempt from
                        # the blocked main-line possession check for this tick.
                        held = False
                        stop_at = None
                    else:
                        # Pending diversion: continue on the main line until the
                        # designated loop entry, then enter the loop.
                        step_km = target / 3600.0 * cls.SIM_SECONDS_PER_TICK
                        proposed = current_km + (step_km if direction == "UP" else -step_km)
                        if direction == "UP" and proposed >= entry_km:
                            train["current_km"] = round(entry_km, 3)
                            route_control["status"] = "ON_LOOP"
                            route_control["loop_progress_km"] = 0.0
                            train["route_control"] = route_control
                            held = False
                            stop_at = None
                            train["effective_speed_kmh"] = round(target, 1)
                            train["actual_speed_kmh"] = round(target, 1)
                            train["commanded_speed_kmh"] = round(target, 1)
                            train["control_action"] = "REROUTE_VIA_LOOP"
                            train["status"] = "AI-3 ON LOOP"
                        elif direction == "DN" and proposed <= entry_km:
                            train["current_km"] = round(entry_km, 3)
                            route_control["status"] = "ON_LOOP"
                            route_control["loop_progress_km"] = 0.0
                            train["route_control"] = route_control
                            held = False
                            stop_at = None
                            train["effective_speed_kmh"] = round(target, 1)
                            train["actual_speed_kmh"] = round(target, 1)
                            train["commanded_speed_kmh"] = round(target, 1)
                            train["control_action"] = "REROUTE_VIA_LOOP"
                            train["status"] = "AI-3 ON LOOP"
                        else:
                            stop_at = cls._safe_block_stop(train, active_blocks, proposed) if target > 0 else None
                            held = control_action == "HOLD" or stop_at is not None
                            if held:
                                if stop_at is not None:
                                    train["current_km"] = round(stop_at, 3)
                                train["effective_speed_kmh"] = 0.0
                                train["actual_speed_kmh"] = 0.0
                                train["commanded_speed_kmh"] = 0.0
                                train["control_action"] = "HOLD"
                                train["status"] = "HOLD AT SIGNAL"
                                train["_delay_seconds"] = float(train.get("_delay_seconds", 0)) + cls.SIM_SECONDS_PER_TICK
                            else:
                                train["current_km"] = round(proposed, 3)
                                train["effective_speed_kmh"] = round(target, 1)
                                train["actual_speed_kmh"] = round(target, 1)
                                train["commanded_speed_kmh"] = round(target, 1)
                                train["control_action"] = control_action
                                train["status"] = "AI-3 CONTROLLED" if control_action != "NORMAL" else (f"DELAYED +{int(train.get('delay_minutes', 0))}m" if int(train.get('delay_minutes', 0)) > 0 else "ON TIME")
                else:
                    step_km = target / 3600.0 * cls.SIM_SECONDS_PER_TICK
                    proposed = float(train.get("current_km", 0)) + (step_km if direction == "UP" else -step_km)
                    stop_at = cls._safe_block_stop(train, active_blocks, proposed) if target > 0 else None
                    held = control_action == "HOLD" or stop_at is not None
                    if held:
                        if stop_at is not None:
                            train["current_km"] = round(stop_at, 3)
                        train["effective_speed_kmh"] = 0.0
                        train["actual_speed_kmh"] = 0.0
                        train["commanded_speed_kmh"] = 0.0
                        train["control_action"] = "HOLD"
                        train["status"] = "HOLD AT SIGNAL"
                        train["_delay_seconds"] = float(train.get("_delay_seconds", 0)) + cls.SIM_SECONDS_PER_TICK
                    else:
                        if proposed > cls.CORRIDOR_LENGTH_KM:
                            proposed = 0.0
                        elif proposed < 0.0:
                            proposed = cls.CORRIDOR_LENGTH_KM
                        train["current_km"] = round(proposed, 3)
                        train["effective_speed_kmh"] = round(target, 1)
                        train["actual_speed_kmh"] = round(target, 1)
                        train["commanded_speed_kmh"] = round(target, 1)
                        train["control_action"] = control_action
                        train["status"] = "AI-3 CONTROLLED" if control_action != "NORMAL" else (f"DELAYED +{int(train.get('delay_minutes', 0))}m" if int(train.get("delay_minutes", 0)) > 0 else "ON TIME")

                # Once a loop is completed, release the protected block and return
                # the train to normal main-line control on the next evaluation.
                if (train.get("route_control") or {}).get("status") == "REJOINED":
                    rc = train["route_control"]
                    train["route_control"] = {"mode": "MAIN", "status": "REJOINED", "via": rc.get("via")}

                block_ctx = None if (train.get("route_control") or {}).get("mode") == "LOOP" else cls._block_context(train, active_blocks)
                if block_ctx and block_ctx["relation"] == "INSIDE_BLOCK":
                    train["effective_speed_kmh"] = 0.0
                    train["actual_speed_kmh"] = 0.0
                    train["commanded_speed_kmh"] = 0.0
                    train["control_action"] = "HOLD"
                    train["status"] = "HOLD AT SIGNAL"
                accumulated = float(train.get("_delay_seconds", 0))
                if accumulated >= 60:
                    extra_minutes = int(accumulated // 60)
                    train["delay_minutes"] = int(train.get("delay_minutes", 0)) + extra_minutes
                    train["_delay_seconds"] = accumulated - extra_minutes * 60
                cls.enrich_train(train, active_blocks, stations)
                train.pop("_delay_seconds", None) if False else None

            # Re-evaluate after movement and publish the authoritative post-tick
            # controls/conflicts that the frontend sees.
            result = TrafficManagerAI3.evaluate(trains, active_blocks, network)
            # Publish the next command explicitly without overwriting the
            # physical state reached during this tick. This prevents a UI race
            # where AI-3 says "40 km/h" while the train is still physically
            # stopped from the previous safety command.
            for train in trains:
                next_control = result.get("controls", {}).get(str(train.get("train_no")))
                if next_control:
                    train["next_control_action"] = next_control.get("action", "NORMAL")
                    train["next_commanded_speed_kmh"] = float(next_control.get("target_speed_kmh", train.get("actual_speed_kmh", 0)))
                else:
                    train["next_control_action"] = "NORMAL"
                    train["next_commanded_speed_kmh"] = float(train.get("speed_kmh", 0))
            runtime.set_ai3_unlocked(result)
            runtime.append_event_unlocked({
                "type": "TELEMETRY_TICK",
                "train_count": len(trains),
                "conflict_count": len(result["conflicts"]),
                "control_count": len(result.get("controls", {})),
            })
            return True

        await OperationalState.mutate(mutator)


class TelemetryHub:
    _task: Optional[asyncio.Task] = None
    _subscribers: set[asyncio.Queue] = set()
    _lock = asyncio.Lock()

    @classmethod
    async def start(cls):
        await OperationalState.initialize()
        if cls._task is None or cls._task.done():
            await TelemetrySimulator.step()
        async with cls._lock:
            if cls._task is None or cls._task.done():
                cls._task = asyncio.create_task(cls._loop(), name="rail-optimax-telemetry")

    @classmethod
    async def _loop(cls):
        while True:
            await asyncio.sleep(TelemetrySimulator.TICK_SECONDS)
            try:
                await TelemetrySimulator.step()
                payload = await OperationalState.snapshot()
                for q in list(cls._subscribers):
                    try:
                        q.put_nowait(payload)
                    except asyncio.QueueFull:
                        try: q.get_nowait()
                        except asyncio.QueueEmpty: pass
                        try: q.put_nowait(payload)
                        except asyncio.QueueFull: pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                payload = await OperationalState.snapshot()
                payload["degraded"] = True
                payload["error"] = str(exc)
                for q in list(cls._subscribers):
                    try: q.put_nowait(payload)
                    except asyncio.QueueFull: pass

    @classmethod
    async def stop(cls):
        async with cls._lock:
            if cls._task and not cls._task.done():
                cls._task.cancel()
                try: await cls._task
                except asyncio.CancelledError: pass
            cls._task = None
            cls._subscribers.clear()

    @classmethod
    async def subscribe(cls):
        await cls.start()
        q = asyncio.Queue(maxsize=2)
        async with cls._lock:
            cls._subscribers.add(q)
            q.put_nowait(await OperationalState.snapshot())
        return q

    @classmethod
    async def unsubscribe(cls, q):
        async with cls._lock:
            cls._subscribers.discard(q)

    @classmethod
    async def snapshot(cls):
        return await OperationalState.snapshot()

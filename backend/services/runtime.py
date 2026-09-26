"""Authoritative operational state for the simulated OCC.

The custom JSON files are immutable seeds. Runtime state is kept in memory for
fast control-loop decisions and snapshotted atomically to a small JSON state
file so a process restart can recover the simulation when the host provides a
persistent volume. No external railway system is contacted.
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None
from pathlib import Path
from typing import Any, Dict, List

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_FILE = Path(os.getenv("RAILOPTIMAX_STATE_FILE", str(DATA_DIR / "runtime_state.json")))
STATE_SCHEMA = 5
DEFAULT_TIMEZONE = os.getenv("RAILOPTIMAX_TIMEZONE", "Asia/Kolkata")


class OperationalState:
    _lock = asyncio.Lock()
    _loaded = False
    _sequence = 0
    _trains: List[Dict[str, Any]] = []
    _blocks: List[Dict[str, Any]] = []
    _maintenance: List[Dict[str, Any]] = []
    _network: Dict[str, Any] = {}
    _events: List[Dict[str, Any]] = []
    _ai1_plan: Dict[str, Any] = {}
    _ai3: Dict[str, Any] = {"conflicts": [], "advisories": [], "signals": [], "controls": {}}
    _started_at = ""
    _persistence_error: str | None = None


    @classmethod
    def _now_local(cls) -> datetime:
        if ZoneInfo is not None:
            try:
                return datetime.now(ZoneInfo(DEFAULT_TIMEZONE))
            except Exception:
                pass
        return datetime.now().astimezone()

    @staticmethod
    def _minutes_of_day(value: str | None) -> int | None:
        if not value or ":" not in str(value):
            return None
        try:
            hour, minute = (int(x) for x in str(value).split(":", 1))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                return None
            return hour * 60 + minute
        except (TypeError, ValueError):
            return None

    @classmethod
    def _window_state(cls, start_time: str | None, end_time: str | None, now: datetime) -> str | None:
        start = cls._minutes_of_day(start_time)
        end = cls._minutes_of_day(end_time)
        if start is None or end is None:
            return None
        current = now.hour * 60 + now.minute
        if start == end:
            return "Active"
        if start < end:
            if current < start:
                return "Planned"
            if current < end:
                return "Active"
            return "Completed"
        # Cross-midnight window, e.g. 23:00 -> 01:00. Without a date field,
        # the time-of-day tells us whether the current occurrence is the one
        # that starts tonight or the one that started yesterday.
        if current >= start:
            return "Active"
        if current < end:
            return "Active"
        # Between end and start: before today's start is the next occurrence.
        return "Planned"

    @classmethod
    def _reconcile_blocks_unlocked(cls) -> None:
        now = cls._now_local()
        changed = False
        for block in cls._blocks:
            status = str(block.get("status", "Planned"))
            # Safety-pending blocks must be explicitly approved; clock time
            # alone must never activate them.
            if status == "PENDING_SAFETY" or not block.get("approved", False):
                continue
            window = cls._window_state(block.get("start_time"), block.get("end_time"), now)
            if window and window != status and status not in {"CANCELLED", "Completed"}:
                block["status"] = window
                changed = True
        # Keep the maintenance register synchronized with its assigned block.
        # This makes the left Maintenance Schedule an authoritative operational
        # view instead of a static request inbox.
        by_block = {str(b.get("block_id")): b for b in cls._blocks}
        for task in cls._maintenance:
            block_id = task.get("assigned_block_id")
            if not block_id:
                continue
            block = by_block.get(str(block_id))
            if not block:
                continue
            bstatus = str(block.get("status", task.get("status", "Under Review")))
            mapped = {"Active": "Active", "Planned": "Scheduled", "Completed": "Completed", "PENDING_SAFETY": "PENDING_SAFETY"}.get(bstatus, task.get("status", "Under Review"))
            if task.get("status") != mapped:
                task["status"] = mapped
                changed = True
        if changed:
            cls.append_event_unlocked({
                "type": "BLOCK_LIFECYCLE_RECONCILED",
                "timestamp": now.isoformat(),
            })

    @classmethod
    def _read(cls, filename: str, default: Any) -> Any:
        path = DATA_DIR / filename
        try:
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return copy.deepcopy(default)

    @classmethod
    def _seed_state(cls) -> None:
        cls._network = cls._read("network.json", {})
        cls._trains = cls._read("train.json", [])
        cls._blocks = cls._read("block.json", [])
        cls._maintenance = cls._read("maintenance.json", [])
        cls._events = []
        cls._ai1_plan = {}
        cls._ai3 = {"conflicts": [], "advisories": [], "signals": [], "controls": {}}
        cls._sequence = 0
        cls._started_at = datetime.now(timezone.utc).isoformat()

    @classmethod
    def _load_persisted_unlocked(cls) -> bool:
        try:
            if not STATE_FILE.exists():
                return False
            with STATE_FILE.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if payload.get("schema") != STATE_SCHEMA:
                return False
            trains = payload.get("trains", [])
            network = payload.get("network", {})
            # Reject stale/test/corrupted runtime snapshots. The OCC demo
            # must start with the canonical 10-train, 5-UP + 5-DN profile
            # and the full 11-station corridor.
            up_count = sum(1 for t in trains if isinstance(t, dict) and t.get("direction") == "UP")
            dn_count = sum(1 for t in trains if isinstance(t, dict) and t.get("direction") == "DN")
            station_count = len(network.get("stations", [])) if isinstance(network, dict) else 0
            if len(trains) != 10 or up_count != 5 or dn_count != 5 or station_count != 11:
                return False
            cls._sequence = int(payload.get("sequence", 0))
            # Runtime snapshots from older demo builds may contain a stale
            # effective/actual speed pair. The physical simulator treats
            # actual_speed_kmh as authoritative; normalize the three speed
            # fields before exposing the snapshot to AI-3 or the OCC UI.
            for train in trains:
                nominal = max(0.0, float(train.get("speed_kmh", 50) or 0))
                actual = train.get("actual_speed_kmh")
                effective = train.get("effective_speed_kmh")
                if actual is None:
                    actual = effective if effective is not None else nominal
                actual = max(0.0, float(actual))
                if str(train.get("control_action", "")).upper() == "HOLD" or "HOLD" in str(train.get("status", "")).upper():
                    actual = 0.0
                train["actual_speed_kmh"] = round(actual, 1)
                train["effective_speed_kmh"] = round(actual, 1)
                train["commanded_speed_kmh"] = round(float(train.get("commanded_speed_kmh", actual) or actual), 1)
            cls._trains = trains
            cls._blocks = payload.get("blocks", [])
            cls._maintenance = payload.get("maintenance", [])
            cls._network = network
            cls._events = payload.get("events", [])[-100:]
            cls._ai1_plan = payload.get("ai1_plan", {})
            cls._ai3 = payload.get("ai3", {"conflicts": [], "advisories": [], "signals": [], "controls": {}})
            cls._started_at = payload.get("started_at") or datetime.now(timezone.utc).isoformat()
            return isinstance(cls._trains, list) and isinstance(cls._network, dict)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return False

    @classmethod
    def _persist_unlocked(cls) -> None:
        payload = {
            "schema": STATE_SCHEMA,
            "sequence": cls._sequence,
            "trains": cls._trains,
            "blocks": cls._blocks,
            "maintenance": cls._maintenance,
            "network": cls._network,
            "events": cls._events[-100:],
            "ai1_plan": cls._ai1_plan,
            "ai3": cls._ai3,
            "started_at": cls._started_at,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".railopt-state-", suffix=".tmp", dir=str(STATE_FILE.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(temp_name, STATE_FILE)
                cls._persistence_error = None
            finally:
                try:
                    if os.path.exists(temp_name):
                        os.unlink(temp_name)
                except OSError:
                    pass
        except OSError as exc:
            cls._persistence_error = str(exc)

    @classmethod
    async def initialize(cls) -> None:
        async with cls._lock:
            if cls._loaded:
                return
            cls._seed_state()
            if not cls._load_persisted_unlocked():
                cls._persist_unlocked()
            cls._reconcile_blocks_unlocked()
            cls._loaded = True

    @classmethod
    async def reset(cls) -> None:
        async with cls._lock:
            cls._loaded = False
            try:
                STATE_FILE.unlink(missing_ok=True)
            except OSError:
                pass
        await cls.initialize()

    @classmethod
    async def read(cls) -> Dict[str, Any]:
        await cls.initialize()
        async with cls._lock:
            cls._reconcile_blocks_unlocked()
            cls._persist_unlocked()
            return {
                "sequence": cls._sequence,
                "trains": copy.deepcopy(cls._trains),
                "blocks": copy.deepcopy(cls._blocks),
                "maintenance": copy.deepcopy(cls._maintenance),
                "network": copy.deepcopy(cls._network),
                "events": copy.deepcopy(cls._events[-50:]),
                "ai1": copy.deepcopy(cls._ai1_plan),
                "ai3": copy.deepcopy(cls._ai3),
                "started_at": cls._started_at,
                "persistence": {"state_file": str(STATE_FILE), "error": cls._persistence_error},
            }

    @classmethod
    async def mutate(cls, mutator):
        await cls.initialize()
        async with cls._lock:
            cls._reconcile_blocks_unlocked()
            result = mutator(cls)
            cls._sequence += 1
            cls._persist_unlocked()
            return copy.deepcopy(result)

    @classmethod
    def append_event_unlocked(cls, event: Dict[str, Any]) -> None:
        item = dict(event)
        item.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        cls._events.append(item)
        cls._events = cls._events[-100:]

    @classmethod
    def trains_unlocked(cls): return cls._trains
    @classmethod
    def blocks_unlocked(cls): return cls._blocks
    @classmethod
    def network_unlocked(cls): return cls._network
    @classmethod
    def maintenance_unlocked(cls): return cls._maintenance
    @classmethod
    def set_ai1_unlocked(cls, plan): cls._ai1_plan = copy.deepcopy(plan)
    @classmethod
    def set_ai3_unlocked(cls, result): cls._ai3 = copy.deepcopy(result)

    @classmethod
    def public_snapshot_unlocked(cls, include_internal: bool = False) -> Dict[str, Any]:
        network = cls._network
        active_blocks = [b for b in cls._blocks if b.get("status") == "Active"]
        payload = {
            "type": "telemetry",
            "sequence": cls._sequence,
            "server_time": datetime.now(timezone.utc).isoformat(),
            "corridor": {
                "id": network.get("corridor_id", "CORR_SDAH_BP"),
                "name": network.get("name", "Custom OCC Corridor"),
                "length_km": network.get("length_km", 25.0),
                "stations": network.get("stations", []),
                "tracks": network.get("tracks", ["UP_LINE", "DN_LINE"]),
            },
            "trains": copy.deepcopy(cls._trains),
            "active_blocks": copy.deepcopy(active_blocks),
            "planned_blocks": copy.deepcopy([b for b in cls._blocks if b.get("status") == "Planned"]),
            "maintenance": copy.deepcopy(cls._maintenance),
            "ai1": copy.deepcopy(cls._ai1_plan),
            "ai3": copy.deepcopy(cls._ai3),
            "events": copy.deepcopy(cls._events[-25:]),
        }
        if include_internal:
            payload["persistence"] = {"state_file": str(STATE_FILE), "error": cls._persistence_error}
            payload["started_at"] = cls._started_at
        return payload

    @classmethod
    async def snapshot(cls) -> Dict[str, Any]:
        await cls.initialize()
        async with cls._lock:
            return cls.public_snapshot_unlocked()

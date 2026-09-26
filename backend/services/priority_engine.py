"""AI-1 priority scoring: LightGBM inference with deterministic fallback."""
from __future__ import annotations
from pathlib import Path
import json

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except Exception:
    lgb = None
    HAS_LIGHTGBM = False

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "ai1_priority_lgbm.txt"
META_PATH = Path(__file__).resolve().parent.parent / "models" / "ai1_priority_metadata.json"
_MODEL = None

PRIORITY_LEVEL = {"Low": 0.0, "Medium": 1.0, "High": 2.0, "Critical": 3.0}


def _load_model():
    global _MODEL
    if _MODEL is None and HAS_LIGHTGBM and MODEL_PATH.exists():
        try:
            _MODEL = lgb.Booster(model_file=str(MODEL_PATH))
        except Exception:
            _MODEL = False
    return _MODEL if _MODEL is not False else None


def _features(task: dict) -> list[float]:
    priority = PRIORITY_LEVEL.get(str(task.get("priority", "Medium")), 1.0)
    duration = float(task.get("duration_minutes", 60) or 60)
    overdue = float(task.get("overdue_days", 0) or 0)
    location = float(task.get("location_from_km", 12.5) or 12.5)
    resources = str(task.get("resources", ""))
    resource_pressure = float(max(0, min(3, resources.count(",") + (1 if resources else 0))))
    return [
        priority,
        1.0 if task.get("emergency", False) else 0.0,
        duration,
        1.0 if task.get("requires_power_block", False) else 0.0,
        1.0 if task.get("requires_traffic_block", True) else 0.0,
        overdue,
        location,
        resource_pressure,
    ]


def calculate_task_priority_score(task: dict) -> float:
    """Return a 0-100 prototype priority score.

    Runtime inference is local/offline. If the optional LightGBM artifact is
    unavailable, the deterministic fallback preserves service availability.
    """
    model = _load_model()
    if model is not None:
        try:
            score = float(model.predict([_features(task)])[0])
            return round(max(0.0, min(100.0, score)), 2)
        except Exception:
            pass

    base_priority_weights = {"Critical": 40.0, "High": 30.0, "Medium": 20.0, "Low": 10.0}
    score = base_priority_weights.get(task.get("priority", "Medium"), 15.0)
    if task.get("emergency", False): score += 50.0
    if float(task.get("duration_minutes", 60) or 60) > 120: score += 5.0
    if task.get("requires_power_block", False) and task.get("requires_traffic_block", True): score += 5.0
    score += min(20.0, float(task.get("overdue_days", 0) or 0) * 0.9)
    return min(100.0, score)


def model_status() -> dict:
    return {
        "engine": "LightGBM",
        "available": _load_model() is not None,
        "model_path": str(MODEL_PATH.name),
        "metadata": json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {},
    }

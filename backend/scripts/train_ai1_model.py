"""Train the small synthetic LightGBM priority model used by AI-1.
This is prototype-only synthetic training data; no real railway operational labels are used.
"""
from pathlib import Path
import json
import numpy as np
import lightgbm as lgb

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
MODEL_DIR.mkdir(exist_ok=True)

rng = np.random.default_rng(26027)
n = 1600
priority = rng.integers(0, 4, n)  # Low -> Critical
emergency = rng.integers(0, 2, n)
duration = rng.integers(20, 181, n)
power = rng.integers(0, 2, n)
traffic = rng.integers(0, 2, n)
overdue = rng.integers(0, 31, n)
proximity = rng.uniform(0, 25, n)
resource_pressure = rng.integers(0, 4, n)

X = np.column_stack([priority, emergency, duration, power, traffic, overdue, proximity, resource_pressure]).astype(float)
y = (
    priority * 17.0
    + emergency * 30.0
    + np.clip(duration - 60, 0, 120) * 0.08
    + power * 5.0
    + traffic * 7.0
    + np.clip(overdue, 0, 20) * 0.9
    + np.maximum(0, 5.0 - proximity) * 2.5
    + resource_pressure * 2.0
    + rng.normal(0, 2.5, n)
)
y = np.clip(y, 0, 100)

feature_names = [
    "priority_level", "emergency", "duration_minutes", "requires_power_block",
    "requires_traffic_block", "overdue_days", "location_km", "resource_pressure"
]
train = lgb.Dataset(X, label=y, feature_name=feature_names)
params = {
    "objective": "regression",
    "metric": "l2",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "min_data_in_leaf": 20,
    "verbosity": -1,
    "seed": 26027,
}
booster = lgb.train(params, train, num_boost_round=90)
booster.save_model(str(MODEL_DIR / "ai1_priority_lgbm.txt"))
(MODEL_DIR / "ai1_priority_metadata.json").write_text(json.dumps({
    "model": "LightGBM regression",
    "version": "synthetic-v1",
    "training_samples": n,
    "feature_names": feature_names,
    "label": "prototype_priority_score_0_100",
    "note": "Synthetic prototype model. Not trained on real railway operational data and not safety-certified."
}, indent=2), encoding="utf-8")
print(MODEL_DIR / "ai1_priority_lgbm.txt")

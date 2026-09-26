import json
from pathlib import Path
from typing import List, Dict, Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

class DataStore:
    @staticmethod
    def read_json(filename: str) -> Any:
        file_path = DATA_DIR / filename
        if not file_path.exists():
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def write_json(filename: str, data: Any) -> None:
        file_path = DATA_DIR / filename
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

def detect_coordination_opportunities() -> List[Dict[str, Any]]:
    maintenance_tasks = DataStore.read_json("maintenance.json")
    blocks = DataStore.read_json("block.json")

    opportunities = []
    spatial_clusters: Dict[str, List[Dict[str, Any]]] = {}
    for task in maintenance_tasks:
        key = f"KM {task['location_from_km']:.1f} - {task['location_to_km']:.1f}"
        spatial_clusters.setdefault(key, []).append(task)

    for section, tasks in spatial_clusters.items():
        departments = list({t["department"] for t in tasks})
        if len(tasks) >= 2 and len(departments) >= 2:
            matched_block = next((b for b in blocks if b["section"] == section or b["block_id"] == "B-104"), blocks[0])
            opportunities.append({
                "opportunity_id": f"OPP-{len(opportunities) + 1}",
                "section": section,
                "departments": departments,
                "task_count": len(tasks),
                "tasks": [t["query_id"] for t in tasks],
                "suggested_block": matched_block["block_id"],
                "duration_min": matched_block["duration_minutes"],
                "train_impact_delay_min": matched_block["train_impact_delay_minutes"],
                "blocks_saved": max(1, len(tasks) - 1),
                "approved": matched_block.get("approved", False)
            })

    return opportunities
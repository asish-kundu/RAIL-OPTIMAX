from fastapi import APIRouter
from backend.services.ai1_plan import AI1Planner
from backend.services.manage import TrafficManagerAI3
from backend.services.runtime import OperationalState
from backend.services.priority_engine import calculate_task_priority_score

router = APIRouter(prefix="/ai", tags=["AI Engine"])

@router.get("/status")
async def ai_status():
    state = await OperationalState.read()
    return {
        "ai1": {"status": "READY", "solver": "OR-TOOLS CP-SAT + heuristic fallback"},
        "ai2": {"status": "READY", "mode": "EVENT_DRIVEN"},
        "ai3": {"status": "LIVE", "mode": state["ai3"].get("controller_mode", "CLOSED_LOOP_SIMULATION"), "conflicts": state["ai3"].get("active_conflicts_count", 0), "controls": len(state["ai3"].get("controls", {}))},
    }

@router.get("/coordination-opportunities")
async def get_coordination_opportunities():
    state = await OperationalState.read()
    tasks = state["maintenance"]
    groups = {}
    for t in tasks:
        key = (round(float(t.get("location_from_km", 0)), 1), round(float(t.get("location_to_km", 0)), 1))
        groups.setdefault(key, []).append(t)
    opportunities = []
    for (a,b), items in groups.items():
        deps = sorted({x.get("department", "Unknown") for x in items})
        if len(items) >= 2 and len(deps) >= 2:
            opportunities.append({"opportunity_id": f"OPP-{len(opportunities)+1}", "section": f"KM {a} - {b}", "departments": deps, "tasks": [x.get("query_id") for x in items], "task_count": len(items)})
    return opportunities

@router.post("/plan")
async def generate_plan():
    return await AI1Planner.generate()

@router.post("/optimize")
async def run_optimization():
    return await AI1Planner.generate(reason="MANUAL_OCC_OPTIMIZE")

@router.get("/manage")
async def manage_live():
    return await TrafficManagerAI3.evaluate_live()

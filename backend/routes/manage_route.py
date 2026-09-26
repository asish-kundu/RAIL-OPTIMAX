from fastapi import APIRouter
from backend.services.manage import TrafficManagerAI3
from backend.services.runtime import OperationalState

router = APIRouter(prefix="/ai/manage", tags=["AI-3 MANAGE"])


@router.get("/conflicts")
async def get_conflicts():
    result = await TrafficManagerAI3.evaluate_live()
    return {
        "status": "success",
        "engine": "AI-3 MANAGE",
        "conflict_count": len(result.get("conflicts", [])),
        "threshold_km": result.get("conflicts", [{}])[0].get("safe_min_km", 1.0) if result.get("conflicts") else 1.0,
        "conflicts": result.get("conflicts", []),
        "advisories": result.get("advisories", []),
        "controls": result.get("controls", {}),
    }


@router.get("/health")
async def manage_health():
    state = await OperationalState.read()
    ai3 = state.get("ai3", {})
    return {
        "status": "online",
        "engine": "AI-3 MANAGE",
        "controller_mode": ai3.get("controller_mode", "CLOSED_LOOP_SIMULATION"),
        "control_count": len(ai3.get("controls", {})),
        "conflict_count": len(ai3.get("conflicts", [])),
    }

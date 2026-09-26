from fastapi import APIRouter
from pydantic import BaseModel, Field
from backend.services.adapt import EmergencyAdaptEngine

router = APIRouter(prefix="/ai/adapt", tags=["AI-2 Adapt"])


class EmergencyEventPayload(BaseModel):
    department: str = "Engineering (Track)"
    asset_type: str = "Track Section"
    disruption_type: str = "Emergency Maintenance"
    location_km: float = Field(default=12.0, ge=0, le=25)
    location_to_km: float | None = Field(default=None, ge=0, le=25)
    duration_minutes: int = Field(default=45, ge=5, le=360)
    target_track: str = "UP_LINE"
    priority: str = "Critical"
    description: str = "Emergency maintenance input"
    requires_power_block: bool = False
    requires_traffic_block: bool = True
    ohe_isolated: bool = False


@router.post("/inject-emergency")
async def trigger_emergency_adaptation(payload: EmergencyEventPayload):
    return await EmergencyAdaptEngine.inject_emergency_disruption(
        disruption_type=payload.disruption_type,
        location_km=payload.location_km,
        duration_minutes=payload.duration_minutes,
        target_track=payload.target_track,
        department=payload.department,
        asset_type=payload.asset_type,
        location_to_km=payload.location_to_km,
        priority=payload.priority,
        description=payload.description,
        requires_power_block=payload.requires_power_block,
        requires_traffic_block=payload.requires_traffic_block,
        ohe_isolated=payload.ohe_isolated,
    )


@router.get("/events")
async def events():
    from backend.services.runtime import OperationalState
    state = await OperationalState.read()
    return [e for e in state["events"] if e.get("type", "").startswith("AI2")]

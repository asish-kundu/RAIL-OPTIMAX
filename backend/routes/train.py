from fastapi import APIRouter
from backend.services.runtime import OperationalState
from backend.services.telemetry import TelemetryHub

router = APIRouter(prefix="/trains", tags=["Trains"])

@router.get("/")
async def get_all_trains():
    return (await OperationalState.snapshot())["trains"]

@router.get("/live")
async def get_live_telemetry():
    return await TelemetryHub.snapshot()

@router.get("/corridors")
async def get_corridors():
    return (await OperationalState.snapshot())["corridor"]

from pydantic import BaseModel
from typing import Optional

class MaintenanceTask(BaseModel):
    query_id: Optional[str] = None
    department: str
    location_from_km: float
    location_to_km: float
    asset_type: str
    maintenance_type: str
    priority: str
    duration_minutes: int
    preferred_date: str
    preferred_window: str
    resources: str
    emergency: bool = False
    description: str
    status: str = "Under Review"
    submitted_on: Optional[str] = None
    requires_power_block: bool = False
    requires_traffic_block: bool = True
    assigned_block_id: Optional[str] = None
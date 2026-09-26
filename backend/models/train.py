from pydantic import BaseModel
from typing import Optional

class Train(BaseModel):
    train_no: str
    name: str
    type: str
    origin: str
    destination: str
    current_km: float
    speed_kmph: float
    status: str
    delay_minutes: int
    direction: str
    scheduled_departure: str
    scheduled_arrival: str
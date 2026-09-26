from pydantic import BaseModel
from typing import List, Optional

class BlockWindow(BaseModel):
    block_id: str
    section: str
    corridor_id: str
    status: str
    start_time: str
    end_time: str
    duration_minutes: int
    suggested_block: str
    bundled_departments: List[str]
    bundled_tasks: List[str]
    train_impact_delay_minutes: int
    blocks_saved: int
    approved: bool = False
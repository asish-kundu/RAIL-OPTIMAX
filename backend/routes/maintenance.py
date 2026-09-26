from fastapi import APIRouter
from datetime import datetime
from backend.models.maintenance import MaintenanceTask
from backend.services.runtime import OperationalState
from backend.services.priority_engine import calculate_task_priority_score

router=APIRouter(prefix="/maintenance",tags=["Maintenance"])

@router.get("/")
async def get_all_queries(): return (await OperationalState.read())["maintenance"]

@router.post("/")
async def create_query(task: MaintenanceTask):
    state=await OperationalState.read(); task_id=f"TASK-{len(state['maintenance'])+1001}"
    item=task.model_dump(); item.update({"query_id":task_id,"submitted_on":datetime.now().strftime("%d %b %Y"),"status":"Under Review","priority_score":calculate_task_priority_score(item)})
    def commit(runtime):
        runtime.maintenance_unlocked().append(item)
        runtime.append_event_unlocked({"type":"MAINTENANCE_SUBMITTED","query_id":task_id,"department":item["department"]})
        return item
    result=await OperationalState.mutate(commit)
    return {"message":"Query submitted successfully","query_id":task_id,"task":result}

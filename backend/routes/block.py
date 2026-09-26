from fastapi import APIRouter, HTTPException
from backend.services.runtime import OperationalState
from backend.services.safety import SafetyValidator

router = APIRouter(prefix="/blocks", tags=["Blocks"])

@router.get("/")
async def get_blocks():
    state = await OperationalState.read()
    return state["blocks"]

@router.post("/approve/{block_id}")
async def approve_block(block_id: str):
    state = await OperationalState.read()
    block = next((b for b in state["blocks"] if b.get("block_id") == block_id), None)
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    safe, notes = SafetyValidator.validate_block_possession(block, state["trains"])
    if not safe:
        raise HTTPException(status_code=409, detail={"message": "Safety validation failed", "violations": notes})
    def commit(runtime):
        for b in runtime.blocks_unlocked():
            if b.get("block_id") == block_id:
                b["approved"] = True
                window = runtime._window_state(b.get("start_time"), b.get("end_time"), runtime._now_local())
                b["status"] = window or "Planned"
        runtime.append_event_unlocked({"type": "BLOCK_APPROVED", "block_id": block_id})
        return True
    await OperationalState.mutate(commit)
    current = await OperationalState.read()
    current_block = next(b for b in current["blocks"] if b.get("block_id") == block_id)
    return {"status": current_block.get("status", "Planned"), "block_id": block_id}

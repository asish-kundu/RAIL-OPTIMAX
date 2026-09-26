from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel
from backend.services.runtime import OperationalState
from backend.services.ai1_plan import AI1Planner
from backend.services.manage import TrafficManagerAI3

router = APIRouter(prefix="/operator", tags=["Operator Decision"])


class OperatorDecision(BaseModel):
    decision_id: str
    action: str
    operator: str
    timestamp: str
    source: str


@router.post("/decision")
async def operator_decision(decision: OperatorDecision):
    record = {**decision.model_dump(), "received_at": datetime.now(timezone.utc).isoformat()}
    action = str(decision.action or "").upper()

    def commit(runtime):
        ai3 = runtime._ai3 or {}
        controls = ai3.get("controls", {}) or {}
        applied = {"status": "AUDIT_ONLY", "train_no": None, "action": action}

        # AI-3 cards carry stable ids such as A-C-LEAD-TRAIL. Resolve the
        # affected trailing train from the live control table instead of trusting
        # stale UI text. This keeps the backend authoritative.
        target_train_no = None
        control = None
        for train_no, candidate in controls.items():
            if not isinstance(candidate, dict):
                continue
            candidate_ids = {
                str(candidate.get("conflict_id", "")),
                str(candidate.get("advisory_id", "")),
                str(candidate.get("conflict_id", "")).replace("C-", "A-C-", 1),
            }
            if str(decision.decision_id) in candidate_ids:
                target_train_no = str(train_no)
                control = candidate
                break

        if action == "ACCEPT" and target_train_no and control:
            train = next((t for t in runtime._trains if str(t.get("train_no")) == target_train_no), None)
            if train is not None:
                requested_action = str(control.get("action", "NORMAL")).upper()
                requested_speed = max(0.0, float(control.get("target_speed_kmh", train.get("actual_speed_kmh", 0)) or 0))
                # Safety dominance: re-check the live state before committing
                # the command. HOLD is always safe; speed control is bounded by
                # the AI-3 command already produced from the live safety model.
                if requested_action == "HOLD":
                    requested_speed = 0.0
                elif requested_speed > 40.0:
                    requested_speed = 40.0

                train["commanded_speed_kmh"] = round(requested_speed, 1)
                train["next_commanded_speed_kmh"] = round(requested_speed, 1)
                train["next_control_action"] = requested_action
                if requested_action == "HOLD":
                    train["control_action"] = "HOLD"
                    train["actual_speed_kmh"] = 0.0
                    train["effective_speed_kmh"] = 0.0
                    train["status"] = "HOLD AT SIGNAL"
                else:
                    train["control_action"] = requested_action
                applied = {
                    "status": "APPLIED",
                    "train_no": target_train_no,
                    "action": requested_action,
                    "target_speed_kmh": requested_speed,
                    "conflict_id": control.get("conflict_id"),
                }

        runtime.append_event_unlocked({"type": "OPERATOR_DECISION", **record, "execution": applied})
        return {**record, "execution": applied}

    result = await OperationalState.mutate(commit)
    return {"status": "accepted", "record": result}


@router.get("/audit")
async def get_audit_log():
    state = await OperationalState.read()
    records = [e for e in state["events"] if e.get("type") == "OPERATOR_DECISION"]
    return {"count": len(records), "records": records}


@router.post("/reset-simulation")
async def reset_simulation():
    """Restore the custom seed dataset. Intended for demo/operator reset only."""
    await OperationalState.reset()
    plan = await AI1Planner.generate(reason="RESET_BASELINE")
    return {"status": "reset", "message": "Custom OCC simulation restored from seed data.", "ai1_plan": plan}

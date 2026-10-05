from fastapi import APIRouter, HTTPException
from typing import Literal
from models.schemas import BookingRequest, TaskState
from services.task_session_service import publish_task_plan

router = APIRouter(prefix="/api/travel/tasks", tags=["旅行任务"])

def services():
    from api import mcp_manager
    runtime = mcp_manager.get("travel_runtime")
    if runtime is None:
        raise HTTPException(503, "旅行 Runtime 尚未初始化")
    return runtime, mcp_manager["session_store"]

def detail(runtime, task_id):
    return {**runtime.detail(task_id), "events": runtime.store.list_events(task_id),
            "checkpoint": runtime.store.get_latest_checkpoint(task_id),
            "tool_calls": runtime.store.list_tool_calls(task_id),
            "tokens_used": runtime.store.tokens_used(task_id)}

@router.get("/{task_id}")
async def get_task(task_id: str):
    runtime, _ = services()
    try:
        return detail(runtime, task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))

@router.post("/{task_id}/resume")
async def resume_task(task_id: str):
    runtime, sessions = services()
    try:
        task = await runtime.resume(task_id)
        if task.state == TaskState.COMPLETED:
            # Approved/rejected booking can belong to an older immutable plan.
            cp = runtime.store.get_latest_checkpoint(task_id)
            if not cp or "action" not in cp.state_json:
                publish_task_plan(runtime, sessions, task)
        return detail(runtime, task_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

@router.post("/{task_id}/booking-proposal")
async def propose(task_id: str, request: BookingRequest):
    runtime, _ = services()
    try:
        return await runtime.propose_booking(task_id, request)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

@router.post("/{task_id}/approvals/{approval_id}/{decision}")
async def decide(task_id: str, approval_id: str, decision: Literal["approve", "reject"]):
    runtime, _ = services()
    try:
        return await runtime.decide(task_id, approval_id, decision == "approve")
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(409, str(exc))

"""Publish a completed plan to its owning session without overwriting a newer version."""
from fastapi import HTTPException
from models.schemas import TripPlan, ModifyRequest
from services.plan_session_service import build_initial_session, apply_modified_plan

def publish_task_plan(runtime, sessions, task):
    if not task.result or "plan" not in task.result:
        return None
    plan = TripPlan.model_validate(task.result["plan"])
    session = sessions.get_session(task.session_id)
    checkpoint = runtime.store.get_latest_checkpoint(task.task_id)
    snapshot = checkpoint.state_json if checkpoint else {}
    if session and session.current_task_id == task.task_id:
        return session
    if "source_plan" in snapshot:
        if not session:
            raise HTTPException(409, "原会话不存在；任务结果已保留，不能自动发布")
        if session.current_task_id != task.parent_task_id:
            raise HTTPException(409, "会话已有更新方案；旧任务结果已保留，未覆盖当前方案")
        session = apply_modified_plan(session, ModifyRequest(session_id=task.session_id,
                                      instruction=snapshot["instruction"]), plan)
    elif session:
        raise HTTPException(409, "该会话已有其他方案，未覆盖")
    else:
        session = build_initial_session(task.session_id, task.request, plan)
    session.current_task_id = task.task_id
    if not sessions.save_session(session):
        raise HTTPException(500, "任务已完成，但会话保存失败；可恢复任务重试保存")
    return session

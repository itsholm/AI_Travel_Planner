import os
import sys
import asyncio
import time
import uuid
import json
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from llm_client import HelloAgentLLM
from models.schemas import ModifyRequest, TripPlan, TripRequest, TaskState, BookingRequest
from observability import EventType, external_service_instrumentor, observer
from observability.api_endpoints import router as observability_router
from observability.http_observer import http_instrumentor, setup_http_observability

from services.budget_service import calculate_budget
from services.plan_session_service import apply_modified_plan, build_initial_session
from services.session_store import get_session_store
from services.user_memory_service import get_user_memory_service
from trip_planner import TripMaster
from runtime.travel_runtime import TravelPlanningRuntime, TravelTaskStore, TravelToolGateway, register_travel_tools
from mcp_gateway.registry import GatewayToolRegistry
from services.task_session_service import publish_task_plan
from runtime.travel_routes import router as travel_router

load_dotenv()

app = FastAPI(title="智能旅行规划助手")
setup_http_observability(app)
app.include_router(observability_router)
app.include_router(travel_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mcp_manager = {
    "amap_session": None,
    "unsplash_session": None,
    "master": None,


    "exit_stack": None,
    "session_store": None,
    "user_memory_service": None,
}


def get_observed_total_tokens() -> int:
    """从统一可观测存储中读取当前累计 Token 数。"""
    counters = observer.get_metrics().get("counters", {})
    return int(counters.get("tokens_total", 0))


@app.on_event("startup")
async def startup_event():
    """启动时初始化 MCP 客户端、规划器和持久化服务。"""
    from contextlib import AsyncExitStack

    stack = AsyncExitStack()
    mcp_manager["exit_stack"] = stack

    amap_params = StdioServerParameters(
        command=sys.executable,
        args=["services/amap_mcp_service.py"],
        env={"AMAP_API_KEY": os.getenv("AMAP_API_KEY")},
    )
    a_read, a_write = await stack.enter_async_context(stdio_client(amap_params))
    amap_session = await stack.enter_async_context(ClientSession(a_read, a_write))
    await amap_session.initialize()
    mcp_manager["amap_session"] = amap_session

    unsplash_params = StdioServerParameters(
        command=sys.executable,
        args=["services/unsplash_mcp_service.py"],
        env={"UNSPLASH_ACCESS_KEY": os.getenv("UNSPLASH_ACCESS_KEY")},
    )
    u_read, u_write = await stack.enter_async_context(stdio_client(unsplash_params))
    unsplash_session = await stack.enter_async_context(ClientSession(u_read, u_write))
    await unsplash_session.initialize()
    mcp_manager["unsplash_session"] = unsplash_session

    llm = HelloAgentLLM()
    master = TripMaster(llm, amap_session, os.getenv("PLANNING_MODE", "multi_agent"))
    await master.initialize_team()


    mcp_manager["master"] = master


    mcp_manager["session_store"] = get_session_store("sessions.db")
    mcp_manager["user_memory_service"] = get_user_memory_service("sessions.db")

    store = TravelTaskStore("travel_tasks.db")
    registry = GatewayToolRegistry()
    register_travel_tools(master, registry)
    mcp_manager["travel_runtime"] = TravelPlanningRuntime(store, TravelToolGateway(registry, store), master)
    print(f"Service startup complete. Planning mode: {master.planning_mode}")


@app.post("/api/plan")
async def create_plan(request: TripRequest):
    """生成新的旅行规划，保存短期会话，并更新长期用户记忆。"""
    master = mcp_manager["master"]

    session_store = mcp_manager["session_store"]
    if not master:
        raise HTTPException(status_code=500, detail="System is not initialized")

    start_time = time.time()
    session_id = str(uuid.uuid4())
    observer.record_counter("planning_requests_total", 1, {"endpoint": "/api/plan"})
    observer.record_event(EventType.PLANNING_START, {
        "session_id": session_id,
        "city": request.city,
        "travel_days": request.travel_days,
        "endpoint": "/api/plan",
    })

    try:

        user_memory_service = mcp_manager.get("user_memory_service")
        memory_context = (
            user_memory_service.build_memory_context("default")
            if user_memory_service
            else ""
        )
        task = await mcp_manager["travel_runtime"].create(request, session_id=session_id, memory_context=memory_context)
        if task.state != TaskState.COMPLETED:
            raise HTTPException(502, detail={"task_id": task.task_id, "session_id": session_id, "error": task.error})
        plan_object = TripPlan.model_validate(task.result["plan"])
        plan_object.budget = calculate_budget(plan_object)
        session = build_initial_session(session_id, request, plan_object)
        session.current_task_id = task.task_id
        if not session_store.save_session(session):
            raise HTTPException(500, detail={"task_id": task.task_id, "error": "会话保存失败，可恢复任务重试保存"})
        if user_memory_service:
            user_memory_service.update_from_request(request, "default")

        duration = time.time() - start_time
        tokens_used = mcp_manager["travel_runtime"].store.tokens_used(task.task_id)

        response = plan_object.model_dump()
        response["session_id"] = session_id
        response["task_id"] = task.task_id
        response["performance_metrics"] = {
            "duration_seconds": round(duration, 3),
            "tokens_used": tokens_used,
            "is_optimized": task.planning_mode == "multi_agent",
            "optimization_type": task.planning_mode,
        }
        observer.record_histogram("planning_total_duration", duration, {"endpoint": "/api/plan"})
        observer.record_histogram("planning_tokens_used", tokens_used, {"endpoint": "/api/plan"})
        observer.record_event(EventType.PLANNING_COMPLETE, {
            "session_id": session_id,
            "success": True,
            "duration": duration,
            "tokens_used": tokens_used,
            "endpoint": "/api/plan",
        })
        return response
    except HTTPException as exc:
        duration = time.time() - start_time
        observer.record_counter("planning_errors_total", 1, {
            "endpoint": "/api/plan",
            "error_type": "HTTPException",
        })
        observer.record_histogram("planning_total_duration", duration, {"endpoint": "/api/plan"})
        observer.record_event(EventType.PLANNING_COMPLETE, {
            "session_id": session_id,
            "success": False,
            "duration": duration,
            "error_type": "HTTPException",
            "error": str(exc.detail),
            "endpoint": "/api/plan",
        })
        raise
    except Exception as exc:
        duration = time.time() - start_time
        observer.record_counter("planning_errors_total", 1, {
            "endpoint": "/api/plan",
            "error_type": type(exc).__name__,
        })
        observer.record_histogram("planning_total_duration", duration, {"endpoint": "/api/plan"})
        observer.record_event(EventType.PLANNING_COMPLETE, {
            "session_id": session_id,
            "success": False,
            "duration": duration,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "endpoint": "/api/plan",
        })
        print(f"Plan Error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/poi/photo")
async def poi_photo_api(name: str):
    """通过 Unsplash MCP 服务代理查询景点图片。"""
    session = mcp_manager["unsplash_session"]
    if not session:
        return {"success": False, "error": "Visual service unavailable"}

    record = external_service_instrumentor.start_call(
        "unsplash_mcp",
        "get_poi_photo",
        request_size=len(name.encode("utf-8")),
    )
    try:
        result = await session.call_tool("get_poi_photo", arguments={"name": name})
        img_url = result.content[0].text if result.content else ""
        external_service_instrumentor.end_call(
            record,
            success=True,
            response_size=len(img_url.encode("utf-8")),
        )
        return {"success": True, "data": {"photo_url": img_url}}
    except Exception as exc:
        external_service_instrumentor.end_call(
            record,
            success=False,
            status_code=getattr(exc, "status_code", 500),
            error_message=str(exc),
        )
        print(f"Unsplash Call Error: {exc}")
        return {"success": False, "error": str(exc)}


@app.post("/api/modify")
async def modify_plan(request: ModifyRequest):
    """基于会话上下文修改已保存的旅行计划。"""
    master = mcp_manager["master"]
    session_store = mcp_manager["session_store"]

    if not master or not session_store:
        raise HTTPException(status_code=500, detail="System is not initialized")

    session = session_store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        runtime = mcp_manager["travel_runtime"]
        memory = mcp_manager.get("user_memory_service")
        task = await runtime.revise(session.user_request, session.current_plan, request.instruction,
            session_id=session.session_id, parent_task_id=session.current_task_id,
            memory_context=memory.build_memory_context("default") if memory else "")
        if task.state != TaskState.COMPLETED:
            raise HTTPException(502, detail={"task_id": task.task_id, "session_id": session.session_id, "error": task.error})
        published = publish_task_plan(runtime, session_store, task)
        response = published.current_plan.model_dump()
        response.update(session_id=published.session_id, task_id=task.task_id)
        return response
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Modify Error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """返回已保存的会话详情。"""
    session_store = mcp_manager["session_store"]
    if not session_store:
        raise HTTPException(status_code=500, detail="System is not initialized")

    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session.model_dump()


@app.post("/api/session/{session_id}/reset-runtime")
async def reset_session_runtime(session_id: str):
    """清空短期运行时状态，同时保留已持久化的规划结果。"""
    session_store = mcp_manager["session_store"]
    master = mcp_manager["master"]
    if not session_store:
        raise HTTPException(status_code=500, detail="System is not initialized")

    success = session_store.clear_runtime_state(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or reset failed")

    if master and hasattr(master, "reset_agent_histories"):
        master.reset_agent_histories()

    return {
        "success": True,
        "session_id": session_id,
        "message": "Runtime state reset",
    }


@app.get("/api/user-memory")
async def get_user_memory():
    """返回当前默认用户的长期结构化记忆。"""
    user_memory_service = mcp_manager.get("user_memory_service")
    if not user_memory_service:
        raise HTTPException(status_code=500, detail="System is not initialized")

    return {
        "success": True,
        "profile": user_memory_service.get_profile("default"),
        "context": user_memory_service.build_memory_context("default"),
    }


@app.post("/api/user-memory/reset")
async def reset_user_memory():
    """清空当前默认用户的长期结构化记忆。"""
    user_memory_service = mcp_manager.get("user_memory_service")
    if not user_memory_service:
        raise HTTPException(status_code=500, detail="System is not initialized")

    user_memory_service.reset_profile("default")
    return {"success": True, "message": "User memory reset"}


@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """兼容旧路径，返回 HTTP 性能指标。"""
    summary = http_instrumentor.get_summary()
    return {
        "status": "success",
        "data": summary,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/performance/export")
async def export_performance_metrics():
    """兼容旧路径，导出 HTTP 性能指标。"""
    filename = http_instrumentor.export_metrics()
    return {
        "status": "success",
        "message": "Performance metrics exported",
        "filename": filename,
    }


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """删除已保存的会话。"""
    session_store = mcp_manager["session_store"]
    if not session_store:
        raise HTTPException(status_code=500, detail="System is not initialized")

    success = session_store.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or delete failed")

    return {"success": True, "message": "Session deleted"}


@app.on_event("shutdown")
async def shutdown_event():
    """释放 MCP 资源并关闭持久化连接。"""
    stack = mcp_manager["exit_stack"]
    if stack:
        await stack.aclose()

    session_store = mcp_manager.get("session_store")
    if session_store:
        session_store.close()

    user_memory_service = mcp_manager.get("user_memory_service")
    if user_memory_service:
        user_memory_service.close()

    runtime = mcp_manager.get("travel_runtime")
    if runtime:
        runtime.store.close()
    print("System shutdown complete.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

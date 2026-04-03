
import os
import re
import json
import time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from datetime import datetime
from models.schemas import TripRequest, TripPlan, Budget, Session, ModifyRequest, ConversationMessage
from metrics import metrics_collector
from performance_middleware import PerformanceMiddleware


# 导入你之前的组件
from trip_planner import TripMaster
from llm_client import HelloAgentLLM
from parallel_planner import ParallelTripPlanner
from dotenv import load_dotenv
import uuid
from services.session_store import get_session_store
#import traceback
load_dotenv()

# 创建FastAPI应用
app = FastAPI(title="智能旅行规划助手")

# 添加性能监控中间件
app.add_middleware(PerformanceMiddleware)

# 配置允许跨域的列表
origins = [
    "http://localhost:5173", # 你的 Vue 开发环境地址
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # 允许这些来源
    allow_credentials=True,
    allow_methods=["*"],        # 允许所有方法 (GET, POST 等)
    allow_headers=["*"],        # 允许所有请求头
)

# 全局变量，用于在不同请求间复用
#MCP 服务进程在整个 API 运行期间只启动一次。所有的用户请求都会复用这个已有的连接

mcp_manager = {
    "amap_session": None,
    "unsplash_session": None, # 👈 新增 Unsplash 会话
    "master": None,
    "exit_stack": None,
    "session_store": None  # 会话存储
}

@app.on_event("startup")
async def startup_event():
    """应用启动时：建立两个 MCP 连接"""
    from contextlib import AsyncExitStack
    stack = AsyncExitStack()
    mcp_manager["exit_stack"] = stack

    # --- 连接高德服务 ---
    amap_params = StdioServerParameters(
        command="python",
        args=["services/amap_mcp_service.py"],
        env={"AMAP_API_KEY": os.getenv("AMAP_API_KEY")}
    )
    a_read, a_write = await stack.enter_async_context(stdio_client(amap_params))
    amap_session = await stack.enter_async_context(ClientSession(a_read, a_write))
    await amap_session.initialize()
    mcp_manager["amap_session"] = amap_session

    # --- 💡 新增：连接 Unsplash 服务 ---
    unsplash_params = StdioServerParameters(
        command="python",
        args=["services/unsplash_mcp_service.py"], # 👈 确保文件名和路径正确
        env={"UNSPLASH_ACCESS_KEY": os.getenv("UNSPLASH_ACCESS_KEY")}
    )
    u_read, u_write = await stack.enter_async_context(stdio_client(unsplash_params))
    unsplash_session = await stack.enter_async_context(ClientSession(u_read, u_write))
    await unsplash_session.initialize()
    mcp_manager["unsplash_session"] = unsplash_session

    # 3. 初始化 TripMaster (传入高德会话供 Agent 使用)
    llm = HelloAgentLLM()
    master = TripMaster(llm, amap_session)
    await master.initialize_team()

    # 4. 初始化并行规划器
    parallel_planner = ParallelTripPlanner(master)
    mcp_manager["master"] = master
    mcp_manager["parallel_planner"] = parallel_planner

    # 4. 初始化会话存储
    mcp_manager["session_store"] = get_session_store("sessions.db")

    print("🚀 服务初始化完成：高德(地图数据) & Unsplash(视觉增强) & 会话存储 已就绪。")

@app.post("/api/plan")  #高度解耦，它不需要知道MCP存在，也不知道工具有多少
async def create_plan(request: TripRequest):
    """
    接收用户旅行需求，调用并行 TripMaster 进行规划，并创建新会话
    """
    master = mcp_manager["master"]
    parallel_planner = mcp_manager["parallel_planner"]
    session_store = mcp_manager["session_store"]
    if not master or not parallel_planner:
        raise HTTPException(status_code=500, detail="系统尚未初始化完成")

    # 性能监控：开始计时
    start_time = time.time()

    # 记录开始时的Token统计
    initial_tokens = metrics_collector.get_summary_stats().get("total_tokens", 0)

    try:
        # 1. 生成会话 ID
        session_id = str(uuid.uuid4())

        # 2. 直接传递对象，不再传递拼凑的字符串
        plan_object = await parallel_planner.create_plan_optimized(request)
        # 2. 💡 核心逻辑：利用对象属性进行数学计算
        # 使用列表推导式优雅地累加各项支出
        calc_attractions = sum(attr.ticket_price for day in plan_object.days for attr in day.attractions)
        calc_hotels = sum(day.hotel.estimated_cost for day in plan_object.days if day.hotel)
        calc_meals = sum(meal.estimated_cost for day in plan_object.days for meal in day.meals)

        # 交通费：根据天数计算固定预估值（或保留模型预估值）
        calc_transportation = 50.0 * plan_object.travel_days

        # 3. 更新对象的 budget 属性
        # 实例化新的 Budget 对象并赋值给 plan.budget
        plan_object.budget = Budget(
            total_attractions=int(calc_attractions),
            total_hotels=int(calc_hotels),
            total_meals=int(calc_meals),
            total_transportation=int(calc_transportation),
            total=int(calc_attractions + calc_hotels + calc_meals + calc_transportation)
        )

        # 4. 创建并保存会话
        session = Session(
            session_id=session_id,
            user_request=request,
            current_plan=plan_object,
            messages=[
                ConversationMessage(
                    role="assistant",
                    content=f"已为{request.city}生成{request.travel_days}天行程",
                    timestamp=datetime.now().isoformat()
                )
            ],
            summary=f"用户计划去{request.city}旅行{request.travel_days}天",
            updated_at=datetime.now().isoformat()
        )
        session_store.save_session(session)

        # 5. 计算性能指标
        duration = time.time() - start_time
        final_tokens = metrics_collector.get_summary_stats().get("total_tokens", 0)
        tokens_used = final_tokens - initial_tokens if initial_tokens > 0 else 0

        # 5. 返回结果（包含性能指标）
        result = plan_object.model_dump()
        result["session_id"] = session_id
        result["performance_metrics"] = {
            "duration_seconds": round(duration, 3),
            "tokens_used": tokens_used,
            "is_optimized": True,  # 标记为优化后的版本
            "optimization_type": "parallel_processing"
        }

        print(f"✅ 并行规划完成: {duration:.2f}s, 使用tokens: {tokens_used}")
        return result

    except Exception as e:
        print(f"Plan Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/poi/photo")
async def poi_photo_api(name: str):
    """
    前端异步调用此接口。它不再直接运行函数，而是通过 MCP 协议向 Unsplash 服务发起调用。
    """
    session = mcp_manager["unsplash_session"]
    if not session:
        return {"success": False, "error": "视觉服务未就绪"}

    try:
        # 👈 核心修复：使用 call_tool 按照协议名称调用
        result = await session.call_tool("get_poi_photo", arguments={"name": name})
        # MCP 返回的是 content 列表，提取其中的 text (即图片 URL)
        img_url = result.content[0].text if result.content else ""

        return {
            "success": True,
            "data": { "photo_url": img_url }
        }
    except Exception as e:
        print(f"Unsplash Call Error: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/modify")
async def modify_plan(request: ModifyRequest):
    """
    修改行程 - 多轮交互的核心接口

    Args:
        request: 包含 session_id 和修改指令

    Returns:
        更新后的行程（包含 session_id）
    """
    master = mcp_manager["master"]
    session_store = mcp_manager["session_store"]

    if not master or not session_store:
        raise HTTPException(status_code=500, detail="系统尚未初始化完成")

    # 1. 获取会话
    session = session_store.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        # 2. 构建包含上下文的 Prompt
        current_plan_json = session.current_plan.model_dump_json(ensure_ascii=False)
        context_prompt = f"""
【当前行程】
{current_plan_json}

【用户修改要求】
{request.instruction}

请根据用户要求修改行程，返回完整的 TripPlan JSON 格式。
必须保持原有的数据结构，只修改用户指定的部分。
"""

        # 3. 调用规划专家进行修改
        updated_plan = await master.agents["trip_planner"].run_structured(
            context_prompt,
            TripPlan
        )

        # 4. 重新计算预算
        calc_attractions = sum(attr.ticket_price for day in updated_plan.days for attr in day.attractions)
        calc_hotels = sum(day.hotel.estimated_cost for day in updated_plan.days if day.hotel)
        calc_meals = sum(meal.estimated_cost for day in updated_plan.days for meal in day.meals)
        calc_transportation = 50.0 * updated_plan.travel_days

        updated_plan.budget = Budget(
            total_attractions=int(calc_attractions),
            total_hotels=int(calc_hotels),
            total_meals=int(calc_meals),
            total_transportation=int(calc_transportation),
            total=int(calc_attractions + calc_hotels + calc_meals + calc_transportation)
        )

        # 5. 更新会话
        session.current_plan = updated_plan
        session.messages.append(
            ConversationMessage(
                role="user",
                content=request.instruction,
                timestamp=datetime.now().isoformat()
            )
        )
        session.messages.append(
            ConversationMessage(
                role="assistant",
                content="已根据您的要求修改行程",
                timestamp=datetime.now().isoformat()
            )
        )

        # 历史摘要压缩（每10条消息压缩一次）
        if len(session.messages) >= 10:
            summary = f"用户计划去{session.user_request.city}旅行{session.user_request.travel_days}天，已进行多次修改"
            session.summary = summary
            # 只保留最近5条完整消息
            session.messages = session.messages[-5:]

        session.updated_at = datetime.now().isoformat()
        session_store.save_session(session)

        # 6. 返回结果
        result = updated_plan.model_dump()
        result["session_id"] = session.session_id
        return result

    except Exception as e:
        print(f"Modify Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """
    获取会话详情

    Args:
        session_id: 会话ID

    Returns:
        会话信息
    """
    session_store = mcp_manager["session_store"]
    if not session_store:
        raise HTTPException(status_code=500, detail="系统尚未初始化完成")

    session = session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return session.model_dump()

@app.get("/api/performance/metrics")
async def get_performance_metrics():
    """
    获取API性能指标

    Returns:
        性能监控数据
    """
    # 获取中间件实例
    middleware = app.middleware_stack
    performance_middleware = None

    # 查找性能监控中间件
    for layer in middleware:
        if hasattr(layer.app, 'get_performance_summary'):
            performance_middleware = layer.app
            break

    if not performance_middleware:
        return {"error": "性能监控中间件未找到"}

    summary = performance_middleware.get_performance_summary()
    return {
        "status": "success",
        "data": summary,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/performance/export")
async def export_performance_metrics():
    """
    导出性能指标数据

    Returns:
        导出结果
    """
    # 获取中间件实例
    middleware = app.middleware_stack
    performance_middleware = None

    # 查找性能监控中间件
    for layer in middleware:
        if hasattr(layer.app, 'export_metrics'):
            performance_middleware = layer.app
            break

    if not performance_middleware:
        raise HTTPException(status_code=500, detail="性能监控中间件未找到")

    filename = performance_middleware.export_metrics()
    return {
        "status": "success",
        "message": "性能指标已导出",
        "filename": filename
    }

@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """
    删除会话

    Args:
        session_id: 会话ID

    Returns:
        删除结果
    """
    session_store = mcp_manager["session_store"]
    if not session_store:
        raise HTTPException(status_code=500, detail="系统尚未初始化完成")

    success = session_store.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在或删除失败")

    return {"success": True, "message": "会话已删除"}

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时：释放 MCP 连接资源和数据库连接"""
    stack = mcp_manager["exit_stack"]
    if stack:
        await stack.aclose()

    # 关闭数据库连接
    session_store = mcp_manager.get("session_store")
    if session_store:
        session_store.close()

    print("👋 系统已安全关闭，资源已释放。")

    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
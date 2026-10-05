"""Travel planning orchestration; optional writes operate on an immutable plan snapshot.

Single-process demo: per-task locks serialize resume/approval; not a distributed scheduler.
"""
import asyncio
import copy
from datetime import date, timedelta
import uuid

from SimpleAgent import SimpleAgent
from mcp_gateway.executor import ToolGateway
from models.schemas import (
    ApprovalDecision, BookingRequest, Budget, TaskState, ToolCallRecord,
    ToolCallStatus, ToolRiskLevel, TravelPlanningTask, TripPlan, TripRequest,
)
from parallel_planner import ParallelTripPlanner
from services.task_store import TaskStore
from tools.business_travel import MockBusinessTravelTool
from observability import observer, EventType
from observability.execution_context import execution_scope
from services.planner_prompt_service import build_single_agent_planner_prompt
from services.budget_service import calculate_budget as build_budget
from runtime.revision_harness import RevisionGuard


class TravelTaskStore(TaskStore):
    task_model = TravelPlanningTask
    request_model = TripRequest

    def _init_db(self):
        super()._init_db()
        self.conn.execute("""CREATE TABLE IF NOT EXISTS travel_task_context (
            task_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, parent_task_id TEXT NOT NULL,
            planning_mode TEXT NOT NULL, memory_context TEXT NOT NULL)""")
        self.conn.commit()

    def create_task(self, request, goal, user_id="demo-user", *, session_id="",
                    parent_task_id="", planning_mode="multi_agent", memory_context=""):
        task = super().create_task(request, goal, user_id)
        self.conn.execute("INSERT INTO travel_task_context VALUES (?, ?, ?, ?, ?)",
            (task.task_id, session_id or task.task_id, parent_task_id, planning_mode, memory_context))
        self.conn.commit()
        return self.get_task(task.task_id)

    def _row_to_task(self, row):
        task = super()._row_to_task(row)
        ctx = self.conn.execute("SELECT * FROM travel_task_context WHERE task_id = ?",
                                (task.task_id,)).fetchone()
        if ctx:
            for name in ("session_id", "parent_task_id", "planning_mode", "memory_context"):
                setattr(task, name, ctx[name])
        else:
            task.session_id = task.task_id
        return task

    def append_event(self, task_id, event_type, payload):
        event = super().append_event(task_id, event_type, payload)
        task = self.get_task(task_id)
        observer.record_event(EventType.RUNTIME_EVENT, {**payload, "task_id": task_id,
            "session_id": task.session_id if task else "", "runtime_event": event_type})
        return event

    def tokens_used(self, task_id):
        return sum(e.payload.get("total_tokens", 0) for e in self.list_events(task_id)
                   if e.event_type == "llm.usage")


class TravelToolGateway(ToolGateway):
    """Enforce approval on writes even when called outside the orchestrator."""

    async def execute(self, *, task_id, tool_name, arguments, idempotency_key=None,
                      approval_id=None):
        spec = self.registry.get_spec(tool_name)
        if not spec:
            raise ValueError("Unknown tool")
        previous = self.store.get_tool_call_by_idempotency(idempotency_key) if idempotency_key else None
        args_hash = self._hash_args(arguments)
        if previous and (previous.task_id != task_id or previous.tool_name != tool_name
                         or previous.args_hash != args_hash):
            raise ValueError("Idempotency key reused with different arguments")
        if spec.side_effect or spec.risk_level == ToolRiskLevel.HIGH:
            approval = self.store.get_approval(approval_id) if approval_id else None
            if (not approval or approval.task_id != task_id or approval.tool_name != tool_name
                    or approval.decision != ApprovalDecision.APPROVED or not previous
                    or approval.call_id != previous.call_id
                    or approval.preview.get("args_hash") != args_hash):
                raise PermissionError("An approval bound to these exact arguments is required")
            # A crash/timeout after dispatch leaves the external outcome unknown.
            # Do not automatically re-dispatch a write without provider reconciliation.
            if previous.status in {ToolCallStatus.RUNNING, ToolCallStatus.FAILED}:
                raise RuntimeError("Write outcome requires reconciliation; automatic replay blocked")
        return await super().execute(task_id=task_id, tool_name=tool_name,
                                     arguments=arguments, idempotency_key=idempotency_key)


class GatewayBoundTool:
    def __init__(self, tool, gateway, task_id):
        self.tool, self.gateway, self.task_id = tool, gateway, task_id
        self.name = tool.name

    def to_dict(self):
        return self.tool.to_dict()

    async def run(self, **arguments):
        record = await self.gateway.execute(task_id=self.task_id, tool_name=self.name,
                                            arguments=arguments)
        if record.status != ToolCallStatus.SUCCESS:
            raise RuntimeError(record.error or f"Tool failed: {self.name}")
        return record.result.get("text", record.result)


def register_travel_tools(master, registry):
    # Only discovered tools assigned to the original read-only experts are imported.
    for agent in master.agents.values():
        for name in agent.tool_registry.list_tools():
            registry.register_tool(agent.tool_registry.get_tool(name), server="amap-mcp",
                                   timeout_ms=15000, max_retries=2)
    registry.register_tool(
        MockBusinessTravelTool("mock_book_hotel", "模拟预订单晚酒店，不产生真实订单或扣款", {},
            lambda **args: {"simulation": True, "status": "SIMULATED_CONFIRMED",
                            "booking_id": "SIM-" + args["idempotency_key"], **args}),
        server="mock", risk_level=ToolRiskLevel.HIGH, side_effect=True, max_retries=0,
    )


def scoped_master(template, gateway, task_id, memory_context=""):
    """New agent histories per task; MCP sessions and immutable tool adapters are shared."""
    master = copy.copy(template)
    master.agents = {}
    for key, source in template.agents.items():
        prompt = source.system_prompt
        if memory_context and key != "trip_planner":
            prompt += "\n用户历史偏好（本次明确要求优先）：\n" + memory_context
        agent = SimpleAgent(source.name, source.llm, prompt, source.config)
        for name in source.tool_registry.list_tools():
            tool = source.tool_registry.get_tool(name)
            agent.tool_registry.register_single_tool(GatewayBoundTool(tool, gateway, task_id))
        master.agents[key] = agent
    return master


def calculate_budget(plan):
    plan.budget = build_budget(plan)
    return plan


class TravelPlanningRuntime:
    def __init__(self, store, gateway, master, planner_factory=None):
        self.store, self.gateway, self.master = store, gateway, master
        self.planner_factory = planner_factory or (
            lambda task_id: ParallelTripPlanner(scoped_master(
                master, gateway, task_id, self.get(task_id).memory_context)))
        self._locks = {}
        self.revision_guard = RevisionGuard()

    def _lock(self, task_id):
        return self._locks.setdefault(task_id, asyncio.Lock())

    def get(self, task_id):
        task = self.store.get_task(task_id)
        if task is None:
            raise LookupError("旅行任务不存在")
        return task

    def detail(self, task_id):
        task = self.get(task_id)
        approval = self.store.get_pending_approval(task_id)
        return {**task.model_dump(mode="json"),
                "pending_approval": approval.model_dump(mode="json") if approval else None}

    async def create(self, request, session_id="", memory_context=""):
        task = self.store.create_task(request, f"规划{request.city}{request.travel_days}天旅行",
            session_id=session_id, memory_context=memory_context,
            planning_mode=getattr(self.master, "planning_mode", "multi_agent"))
        self.store.append_event(task.task_id, "task.created", {})
        return await self.resume(task.task_id)

    async def revise(self, request, plan, instruction, session_id="", parent_task_id="", memory_context=""):
        task = self.store.create_task(request, f"修改{request.city}旅行方案",
            session_id=session_id, parent_task_id=parent_task_id, memory_context=memory_context,
            planning_mode=getattr(self.master, "planning_mode", "multi_agent"))
        self.store.save_checkpoint(task.task_id, "revision_requested", TaskState.PLANNING,
            {"weather": "", "attractions": "", "hotels": "",
             "source_plan": plan.model_dump(mode="json"), "instruction": instruction})
        return await self.resume(task.task_id)

    async def resume(self, task_id):
        task = self.get(task_id)
        with execution_scope(task_id, task.session_id,
                lambda usage: self.store.append_event(task_id, "llm.usage", usage)):
            return await self._resume(task_id)

    async def _resume(self, task_id):
        async with self._lock(task_id):
            task = self.get(task_id)
            if task.state in {TaskState.COMPLETED, TaskState.CANCELLED}:
                return task
            cp = self.store.get_latest_checkpoint(task_id)
            snapshot = cp.state_json if cp else {}
            if "action" in snapshot:
                return await self._execute_action(task_id, snapshot)
            if self.master is not None and task.planning_mode != getattr(self.master, "planning_mode", "multi_agent"):
                raise ValueError("请使用创建此任务时的 PLANNING_MODE 恢复任务")
            planner = self.planner_factory(task_id)
            self.store.update_task(task_id, state=TaskState.PLANNING, error="")

            async def step(name, operation):
                if name not in snapshot:
                    self.store.append_event(task_id, "step.started", {"step": name})
                    snapshot[name] = await operation()
                    self.store.save_checkpoint(task_id, name, TaskState.PLANNING, snapshot)
                    self.store.append_event(task_id, "step.completed", {"step": name})
                return snapshot[name]

            try:
                if "source_plan" not in snapshot and task.planning_mode == "multi_agent":
                    # Wait for both branches to settle before recording task failure.
                    results = await asyncio.gather(
                        step("weather", lambda: planner._get_weather_info(task.request)),
                        step("attractions", lambda: planner._get_attractions_info(task.request)),
                        return_exceptions=True,
                    )
                    for result in results:
                        if isinstance(result, BaseException):
                            raise result
                    coord = planner.master.extract_last_coord(snapshot["attractions"])
                    await step("hotels", lambda: planner._get_hotels_info(task.request, coord))

                async def build_plan():
                    if "source_plan" in snapshot:
                        prompt = (f"当前行程：{snapshot['source_plan']}\n"
                                  f"修改要求：{snapshot['instruction']}\n返回修改后的完整行程。")
                    elif task.planning_mode == "single_agent":
                        prompt = build_single_agent_planner_prompt(task.request, task.memory_context)
                    else:
                        prompt = planner._build_final_planner_prompt(
                            task.request, snapshot["attractions"], snapshot["weather"], snapshot["hotels"])
                    if task.memory_context and ("source_plan" in snapshot or task.planning_mode != "single_agent"):
                        prompt += "\n用户历史偏好（本次明确要求优先）：\n" + task.memory_context
                    agent = planner.master.agents["trip_planner"]
                    if "source_plan" in snapshot:
                        plan = await self.revision_guard.run(agent, prompt, task.session_id)
                    else:
                        plan = await agent.run_structured(prompt, TripPlan)
                    if len(plan.days) != task.request.travel_days:
                        raise ValueError("生成行程天数与请求不一致")
                    return calculate_budget(plan).model_dump(mode="json")

                plan = await step("plan", build_plan)
                self.store.append_event(task_id, "task.completed", {"step": "plan_generated"})
                return self.store.update_task(task_id, state=TaskState.COMPLETED,
                                              current_step="plan_generated", result={"plan": plan}, error="")
            except Exception as exc:
                self.store.append_event(task_id, "task.failed", {"error": str(exc)})
                return self.store.update_task(task_id, state=TaskState.FAILED, error=str(exc))

    async def propose_booking(self, task_id, request: BookingRequest):
        async with self._lock(task_id):
            task = self.get(task_id)
            # One optional action per immutable planning task; repeated requests replay it.
            cp = self.store.get_latest_checkpoint(task_id)
            snapshot = cp.state_json if cp else {}
            if "action" in snapshot:
                if snapshot["action"]["selection"] != request.model_dump():
                    raise ValueError("该方案已有预订操作；修改行程后请使用新的任务")
                return self.detail(task_id)
            if task.state != TaskState.COMPLETED or not task.result or "plan" not in task.result:
                raise ValueError("请先完成旅行规划")
            plan = TripPlan.model_validate(task.result["plan"])
            day = next((d for d in plan.days if d.day_index == request.day_index), None)
            if not day or not day.hotel:
                raise ValueError("所选日期没有酒店方案")
            args = {"hotel_name": day.hotel.name, "hotel_address": day.hotel.address,
                    "check_in": day.date,
                    "check_out": (date.fromisoformat(day.date) + timedelta(days=1)).isoformat(),
                    "guest_names": request.guest_names,
                    "estimated_cost": day.hotel.estimated_cost,
                    "idempotency_key": f"{task_id}:mock_book_hotel"}
            args_hash = self.gateway._hash_args(args)
            # TaskStore methods commit individually; a stable call key permits inspection.
            # normal resume never executes without the checkpoint and bound approval.
            call = ToolCallRecord(call_id=str(uuid.uuid4()), task_id=task_id,
                tool_name="mock_book_hotel", arguments=args, args_hash=args_hash,
                idempotency_key=args["idempotency_key"], risk_level=ToolRiskLevel.HIGH,
                side_effect=True, status=ToolCallStatus.WAITING_APPROVAL)
            existing = self.store.get_tool_call_by_idempotency(args["idempotency_key"])
            if existing:
                if existing.args_hash != args_hash:
                    raise ValueError("已有不同参数的预订提案")
                call = existing
            else:
                self.store.upsert_tool_call(call)
            approval = self.store.get_pending_approval(task_id) or self.store.create_approval(
                task_id, call.call_id, call.tool_name, "模拟预订单晚酒店（不扣款）", ToolRiskLevel.HIGH,
                {"simulation": True, "arguments": args, "args_hash": args_hash})
            snapshot["action"] = {"approval_id": approval.approval_id, "arguments": args,
                                  "selection": request.model_dump()}
            self.store.save_checkpoint(task_id, "await_booking_approval", TaskState.WAITING_APPROVAL, snapshot)
            self.store.update_task(task_id, state=TaskState.WAITING_APPROVAL, current_step="await_booking_approval")
            self.store.append_event(task_id, "approval.required", {"approval_id": approval.approval_id})
            return self.detail(task_id)

    async def decide(self, task_id, approval_id, approve):
        async with self._lock(task_id):
            self.get(task_id)
            approval = self.store.get_approval(approval_id)
            cp = self.store.get_latest_checkpoint(task_id)
            if (not approval or approval.task_id != task_id or not cp
                    or cp.state_json.get("action", {}).get("approval_id") != approval_id):
                raise ValueError("审批不属于当前任务方案")
            decision = ApprovalDecision.APPROVED if approve else ApprovalDecision.REJECTED
            if approval.decision not in {ApprovalDecision.PENDING, decision}:
                raise ValueError("已决定的审批不能改为相反结果")
            self.store.decide_approval(approval_id, decision)
            self.store.append_event(task_id, "approval.decided", {"decision": decision.value})
            return await self._execute_action(task_id, cp.state_json)

    async def _execute_action(self, task_id, snapshot):
        action = snapshot["action"]
        approval = self.store.get_approval(action["approval_id"])
        if approval.decision == ApprovalDecision.PENDING:
            return self.store.update_task(task_id, state=TaskState.WAITING_APPROVAL)
        if approval.decision == ApprovalDecision.REJECTED:
            return self.store.update_task(task_id, state=TaskState.COMPLETED,
                current_step="booking_rejected", result={"plan": snapshot["plan"], "booking": {"status": "REJECTED"}})
        try:
            self.store.update_task(task_id, state=TaskState.EXECUTING, current_step="booking")
            record = await self.gateway.execute(task_id=task_id, tool_name="mock_book_hotel",
                arguments=action["arguments"], idempotency_key=action["arguments"]["idempotency_key"],
                approval_id=approval.approval_id)
            if record.status != ToolCallStatus.SUCCESS:
                raise RuntimeError(record.error or "模拟预订失败")
            self.store.append_event(task_id, "booking.completed", {"simulation": True})
            return self.store.update_task(task_id, state=TaskState.COMPLETED, current_step="booking_completed",
                result={"plan": snapshot["plan"], "booking": record.result}, error="")
        except Exception as exc:
            self.store.append_event(task_id, "booking.failed", {"error": str(exc)})
            return self.store.update_task(task_id, state=TaskState.FAILED, error=str(exc))

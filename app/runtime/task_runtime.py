import uuid
from typing import Dict, Optional

from mcp_gateway.executor import ToolGateway
from mcp_gateway.risk_policy import PolicyEngine
from models.schemas import (
    Approval,
    ApprovalDecision,
    BusinessTripRequest,
    BusinessTripTask,
    CreateTaskResponse,
    TaskState,
    ToolCallRecord,
    ToolCallStatus,
    ToolRiskLevel,
)
from services.task_store import TaskStore


class BusinessTripRuntime:
    """Production-agent skeleton for business travel execution."""

    def __init__(self, store: TaskStore, gateway: ToolGateway, policy: Optional[PolicyEngine] = None):
        self.store = store
        self.gateway = gateway
        self.policy = policy or PolicyEngine()

    async def create_task(self, request: BusinessTripRequest, user_id: str = "demo-user") -> CreateTaskResponse:
        goal = (
            f"安排{request.start_date}从{request.origin_city}到{request.destination_city}"
            f"的企业差旅，预算{request.budget_limit}元"
        )
        task = self.store.create_task(request=request, goal=goal, user_id=user_id)
        self.store.append_event(task.task_id, "task.started", {"goal": goal})
        return await self._run_until_blocked_or_done(task.task_id)

    async def approve(self, approval_id: str) -> CreateTaskResponse:
        approval = self.store.decide_approval(approval_id, ApprovalDecision.APPROVED)
        if not approval:
            raise ValueError("approval not found")
        self.store.append_event(
            approval.task_id,
            "approval.decided",
            {"approval_id": approval.approval_id, "decision": approval.decision.value},
        )
        return await self._run_until_blocked_or_done(approval.task_id, approval=approval)

    async def reject(self, approval_id: str) -> CreateTaskResponse:
        approval = self.store.decide_approval(approval_id, ApprovalDecision.REJECTED)
        if not approval:
            raise ValueError("approval not found")
        task = self.store.update_task(
            approval.task_id,
            state=TaskState.CANCELLED,
            current_step="approval_rejected",
            result={"reason": "user rejected high risk action"},
        )
        self.store.append_event(
            approval.task_id,
            "task.cancelled",
            {"approval_id": approval.approval_id, "decision": approval.decision.value},
        )
        return self._response(task)

    async def resume(self, task_id: str) -> CreateTaskResponse:
        task = self.store.get_task(task_id)
        if not task:
            raise ValueError("task not found")
        self.store.append_event(task_id, "task.resumed", {"state": task.state.value})
        return await self._run_until_blocked_or_done(task_id)

    async def _run_until_blocked_or_done(
        self,
        task_id: str,
        approval: Optional[Approval] = None,
    ) -> CreateTaskResponse:
        task = self.store.get_task(task_id)
        if not task:
            raise ValueError("task not found")
        if task.state in {TaskState.COMPLETED, TaskState.CANCELLED, TaskState.FAILED}:
            return self._response(task)

        pending = self.store.get_pending_approval(task_id)
        if pending and not approval:
            return self._response(self.store.get_task(task_id))

        try:
            self.store.update_task(task_id, state=TaskState.PLANNING, current_step="read_policy")
            self.store.append_event(task_id, "agent.step", {"step": "read_policy", "summary": "读取公司差旅政策"})
            policy_call = await self.gateway.execute(
                task_id=task_id,
                tool_name="get_travel_policy",
                arguments={
                    "employee_level": task.request.employee_level,
                    "destination_city": task.request.destination_city,
                },
            )

            self.store.update_task(task_id, state=TaskState.EXECUTING, current_step="search_options")
            self.store.append_event(task_id, "agent.step", {"step": "search_options", "summary": "查询交通和酒店候选"})
            train_call = await self.gateway.execute(
                task_id=task_id,
                tool_name="search_train",
                arguments={
                    "origin_city": task.request.origin_city,
                    "destination_city": task.request.destination_city,
                    "date": task.request.start_date,
                },
            )
            hotel_call = await self.gateway.execute(
                task_id=task_id,
                tool_name="search_hotel",
                arguments={
                    "city": task.request.destination_city,
                    "meeting_location": task.request.meeting_location,
                    "max_distance_km": task.request.hotel_within_km or 3.0,
                    "refundable_required": task.request.hotel_refundable_required,
                    "max_price": policy_call.result["hotel_budget_per_night"],
                },
            )

            selected_train = train_call.result["options"][0]
            selected_hotel = hotel_call.result["hotels"][0]
            budget_call = await self.gateway.execute(
                task_id=task_id,
                tool_name="check_budget",
                arguments={
                    "budget_limit": task.request.budget_limit,
                    "transport_cost": selected_train["cost"],
                    "hotel_cost": selected_hotel["cost_per_night"],
                    "other_cost": 500,
                },
            )
            plan_snapshot = {
                "policy": policy_call.result,
                "train": selected_train,
                "hotel": selected_hotel,
                "budget": budget_call.result,
            }
            self.store.save_checkpoint(
                task_id,
                "proposal_ready",
                TaskState.EXECUTING,
                {"plan_snapshot": plan_snapshot},
            )
            self.store.append_event(task_id, "task.checkpointed", {"step": "proposal_ready"})

            booking_key = self._booking_idempotency_key(task_id, selected_hotel["hotel_id"])
            booking_call = self.store.get_tool_call_by_idempotency(booking_key)
            if booking_call and booking_call.status == ToolCallStatus.SUCCESS:
                return await self._complete_after_booking(task_id, booking_call, plan_snapshot)

            spec = self.gateway.registry.get_spec("book_hotel")
            decision = self.policy.decide(spec, approval)
            if decision.requires_approval:
                pending_approval = self._create_booking_approval(
                    task=task,
                    selected_hotel=selected_hotel,
                    selected_train=selected_train,
                    budget=budget_call.result,
                    idempotency_key=booking_key,
                )
                self.store.update_task(task_id, state=TaskState.WAITING_APPROVAL, current_step="await_book_hotel_approval")
                self.store.save_checkpoint(
                    task_id,
                    "await_book_hotel_approval",
                    TaskState.WAITING_APPROVAL,
                    {"plan_snapshot": plan_snapshot, "approval_id": pending_approval.approval_id},
                )
                self.store.append_event(
                    task_id,
                    "approval.required",
                    pending_approval.model_dump(mode="json"),
                )
                return self._response(self.store.get_task(task_id))

            booking_record = await self.gateway.execute(
                task_id=task_id,
                tool_name="book_hotel",
                arguments={
                    "hotel_id": selected_hotel["hotel_id"],
                    "guest_names": task.request.travelers or ["demo-user"],
                    "check_in": task.request.start_date,
                    "check_out": task.request.end_date,
                    "idempotency_key": booking_key,
                },
                idempotency_key=booking_key,
            )
            if booking_record.status != ToolCallStatus.SUCCESS:
                return self._fail(task_id, "book_hotel_failed", booking_record.error or "booking failed")
            return await self._complete_after_booking(task_id, booking_record, plan_snapshot)
        except Exception as exc:
            return self._fail(task_id, "runtime_error", str(exc))

    async def _complete_after_booking(
        self,
        task_id: str,
        booking_record: ToolCallRecord,
        plan_snapshot: Dict,
    ) -> CreateTaskResponse:
        task = self.store.get_task(task_id)
        calendar_key = f"{task_id}:calendar_create"
        notify_key = f"{task_id}:send_itinerary"
        calendar_call = await self.gateway.execute(
            task_id=task_id,
            tool_name="calendar_create",
            arguments={
                "title": f"{task.request.destination_city}客户会议差旅",
                "date": task.request.start_date,
                "location": task.request.meeting_location,
            },
            idempotency_key=calendar_key,
        )
        notify_call = await self.gateway.execute(
            task_id=task_id,
            tool_name="send_itinerary",
            arguments={
                "emails": task.request.notify_emails,
                "summary": f"酒店{booking_record.result['status']}，日历{calendar_call.result['status']}",
            },
            idempotency_key=notify_key,
        )
        result = {
            "plan": plan_snapshot,
            "booking": booking_record.result,
            "calendar": calendar_call.result,
            "notification": notify_call.result,
        }
        task = self.store.update_task(
            task_id,
            state=TaskState.COMPLETED,
            current_step="completed",
            result=result,
        )
        self.store.save_checkpoint(task_id, "completed", TaskState.COMPLETED, result)
        self.store.append_event(task_id, "task.completed", {"result": result})
        return self._response(task)

    def _create_booking_approval(
        self,
        *,
        task: BusinessTripTask,
        selected_hotel: Dict,
        selected_train: Dict,
        budget: Dict,
        idempotency_key: str,
    ) -> Approval:
        call_id = str(uuid.uuid4())
        proposed = ToolCallRecord(
            call_id=call_id,
            task_id=task.task_id,
            tool_name="book_hotel",
            arguments={
                "hotel_id": selected_hotel["hotel_id"],
                "guest_names": task.request.travelers or ["demo-user"],
                "check_in": task.request.start_date,
                "check_out": task.request.end_date,
                "idempotency_key": idempotency_key,
            },
            idempotency_key=idempotency_key,
            risk_level=ToolRiskLevel.HIGH,
            side_effect=True,
            status=ToolCallStatus.WAITING_APPROVAL,
        )
        self.store.upsert_tool_call(proposed)
        return self.store.create_approval(
            task_id=task.task_id,
            call_id=call_id,
            tool_name="book_hotel",
            action=f"预订酒店：{selected_hotel['name']}",
            risk_level=ToolRiskLevel.HIGH,
            preview={
                "hotel": selected_hotel,
                "train": selected_train,
                "budget": budget,
                "side_effect": "确认后将产生酒店预订记录",
            },
        )

    def _fail(self, task_id: str, step: str, error: str) -> CreateTaskResponse:
        task = self.store.update_task(task_id, state=TaskState.FAILED, current_step=step, error=error)
        self.store.append_event(task_id, "task.failed", {"step": step, "error": error})
        return self._response(task)

    def _response(self, task: BusinessTripTask) -> CreateTaskResponse:
        return CreateTaskResponse(
            task_id=task.task_id,
            state=task.state,
            current_step=task.current_step,
            events=self.store.list_events(task.task_id),
            pending_approval=self.store.get_pending_approval(task.task_id),
            result=task.result,
        )

    def _booking_idempotency_key(self, task_id: str, hotel_id: str) -> str:
        return f"{task_id}:book_hotel:{hotel_id}"

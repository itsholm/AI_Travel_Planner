import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app")))

from mcp_gateway.executor import ToolGateway
from mcp_gateway.registry import GatewayToolRegistry
from mcp_gateway.risk_policy import PolicyEngine
from models.schemas import BusinessTripRequest, TaskState, ToolCallStatus, ToolRiskLevel
from runtime.task_runtime import BusinessTripRuntime
from services.task_store import TaskStore
from tools.business_travel import create_business_travel_tools


class BusinessTripRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = TaskStore(os.path.join(self.tmp.name, "tasks.db"))
        self.registry = GatewayToolRegistry()
        for tool in create_business_travel_tools():
            if tool.name == "book_hotel":
                self.registry.register_tool(
                    tool,
                    risk_level=ToolRiskLevel.HIGH,
                    side_effect=True,
                    required_scope="travel:write",
                    max_retries=0,
                )
            elif tool.name in {"calendar_create", "send_itinerary"}:
                self.registry.register_tool(
                    tool,
                    risk_level=ToolRiskLevel.MEDIUM,
                    side_effect=True,
                    required_scope="calendar:write",
                    max_retries=1,
                )
            else:
                self.registry.register_tool(tool, risk_level=ToolRiskLevel.LOW)
        self.runtime = BusinessTripRuntime(
            self.store,
            ToolGateway(self.registry, self.store),
            PolicyEngine(),
        )

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    async def test_high_risk_booking_waits_for_approval_then_completes_once(self):
        response = await self.runtime.create_task(self._request())

        self.assertEqual(response.state, TaskState.WAITING_APPROVAL)
        self.assertIsNotNone(response.pending_approval)
        self.assertEqual(response.pending_approval.tool_name, "book_hotel")

        before_approval_calls = self.store.list_tool_calls(response.task_id)
        booking_calls = [call for call in before_approval_calls if call.tool_name == "book_hotel"]
        self.assertEqual(len(booking_calls), 1)
        self.assertEqual(booking_calls[0].status, ToolCallStatus.WAITING_APPROVAL)

        approved = await self.runtime.approve(response.pending_approval.approval_id)
        self.assertEqual(approved.state, TaskState.COMPLETED)
        self.assertIsNotNone(approved.result["booking"]["booking_id"])

        after_approval_calls = self.store.list_tool_calls(response.task_id)
        successful_bookings = [
            call for call in after_approval_calls
            if call.tool_name == "book_hotel" and call.status == ToolCallStatus.SUCCESS
        ]
        self.assertEqual(len(successful_bookings), 1)

        resumed = await self.runtime.resume(response.task_id)
        self.assertEqual(resumed.state, TaskState.COMPLETED)

        after_resume_calls = self.store.list_tool_calls(response.task_id)
        successful_bookings_after_resume = [
            call for call in after_resume_calls
            if call.tool_name == "book_hotel" and call.status == ToolCallStatus.SUCCESS
        ]
        self.assertEqual(len(successful_bookings_after_resume), 1)

    async def test_reject_cancels_task_without_side_effect(self):
        response = await self.runtime.create_task(self._request())
        rejected = await self.runtime.reject(response.pending_approval.approval_id)

        self.assertEqual(rejected.state, TaskState.CANCELLED)
        booking_calls = [
            call for call in self.store.list_tool_calls(response.task_id)
            if call.tool_name == "book_hotel" and call.status == ToolCallStatus.SUCCESS
        ]
        self.assertEqual(booking_calls, [])

    def _request(self):
        return BusinessTripRequest(
            origin_city="上海",
            destination_city="杭州",
            start_date="2026-09-09",
            end_date="2026-09-10",
            meeting_time="周四下午2点",
            meeting_location="滨江客户公司",
            budget_limit=4000,
            employee_level="standard",
            avoid_red_eye=True,
            travelers=["钟韵雪"],
            notify_emails=["team@example.com"],
        )


if __name__ == "__main__":
    unittest.main()

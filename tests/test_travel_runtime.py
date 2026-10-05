import asyncio
import os
import sys
import tempfile
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))

from amap_mcp import AmapMCPTool
from mcp_gateway.registry import GatewayToolRegistry
from models.schemas import BookingRequest, TaskState, ToolCallStatus, TripPlan, TripRequest
from runtime.travel_runtime import (
    GatewayBoundTool, TravelPlanningRuntime, TravelTaskStore, TravelToolGateway,
    register_travel_tools, scoped_master,
)
from SimpleAgent import SimpleAgent


REQUEST = dict(city='杭州', start_date='2026-10-01', end_date='2026-10-01',
               travel_days=1, transportation='公共交通', accommodation='舒适型')


def plan():
    return TripPlan(city='杭州', start_date='2026-10-01', end_date='2026-10-01',
        overall_suggestions='测试行程', days=[dict(date='2026-10-01', day_index=1,
        description='西湖', transportation='步行', accommodation='舒适型',
        hotel=dict(name='测试酒店', address='西湖附近', estimated_cost=300))])


class TravelRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, 'travel.db')
        self.store = TravelTaskStore(self.path)
        self.registry = GatewayToolRegistry()
        register_travel_tools(SimpleNamespace(agents={}), self.registry)
        self.counts = Counter()
        self.fail_hotels = False
        self.gateway = TravelToolGateway(self.registry, self.store)
        self.runtime = TravelPlanningRuntime(self.store, self.gateway, None, self.factory)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def factory(self, task_id):
        async def weather(request):
            self.counts['weather'] += 1
            await asyncio.sleep(0)
            return '晴'
        async def attractions(request):
            self.counts['attractions'] += 1
            return '西湖 120.1,30.2'
        async def hotels(request, coord):
            self.counts['hotels'] += 1
            if self.fail_hotels:
                raise RuntimeError('hotel service unavailable')
            return '测试酒店'
        async def structured(prompt, model):
            self.counts['plan'] += 1
            return plan()
        return SimpleNamespace(
            _get_weather_info=weather, _get_attractions_info=attractions,
            _get_hotels_info=hotels, _build_final_planner_prompt=lambda *args: 'plan',
            master=SimpleNamespace(extract_last_coord=lambda text: '120.1,30.2',
                agents={'trip_planner': SimpleNamespace(run_structured=structured)}))

    async def create(self):
        return await self.runtime.create(TripRequest(**REQUEST))

    async def proposal(self, task):
        return await self.runtime.propose_booking(task.task_id,
                    BookingRequest(day_index=1, guest_names=['测试用户']))

    async def test_planning_completes_without_approval_or_writes(self):
        task = await self.create()
        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertIsNone(self.store.get_pending_approval(task.task_id))
        self.assertEqual(self.store.list_tool_calls(task.task_id), [])
        self.assertEqual(task.result['plan']['budget']['total'], 350)

    async def test_restart_resumes_only_unfinished_steps(self):
        self.fail_hotels = True
        task = await self.create()
        self.assertEqual(task.state, TaskState.FAILED)
        self.store.close()
        self.store = TravelTaskStore(self.path)
        self.gateway = TravelToolGateway(self.registry, self.store)
        self.runtime = TravelPlanningRuntime(self.store, self.gateway, None, self.factory)
        self.fail_hotels = False
        task = await self.runtime.resume(task.task_id)
        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(self.counts, {'weather': 1, 'attractions': 1, 'hotels': 2, 'plan': 1})
        await self.runtime.resume(task.task_id)
        self.assertEqual(self.counts['plan'], 1)

    async def test_parallel_duplicate_approval_executes_frozen_arguments_once(self):
        task = await self.create()
        proposal = await self.proposal(task)
        approval_id = proposal['pending_approval']['approval_id']
        before = self.store.list_tool_calls(task.task_id)
        self.assertEqual(before[0].status, ToolCallStatus.WAITING_APPROVAL)
        mock = self.registry.get_tool('mock_book_hotel')
        mock.run = AsyncMock(wraps=mock.run)
        results = await asyncio.gather(
            self.runtime.decide(task.task_id, approval_id, True),
            self.runtime.decide(task.task_id, approval_id, True))
        self.assertTrue(all(r.state == TaskState.COMPLETED for r in results))
        self.assertEqual(mock.run.await_count, 1)
        self.assertEqual(self.counts['hotels'], 1)
        self.assertEqual(results[0].result['booking']['hotel_name'], '测试酒店')

    async def test_reject_preserves_plan_and_cannot_be_approved(self):
        task = await self.create()
        proposal = await self.proposal(task)
        aid = proposal['pending_approval']['approval_id']
        result = await self.runtime.decide(task.task_id, aid, False)
        self.assertEqual(result.result['booking']['status'], 'REJECTED')
        self.assertEqual(result.result['plan'], task.result['plan'])
        with self.assertRaises(ValueError):
            await self.runtime.decide(task.task_id, aid, True)

    async def test_gateway_blocks_unapproved_or_changed_arguments(self):
        task = await self.create()
        proposal = await self.proposal(task)
        approval = proposal['pending_approval']
        args = approval['preview']['arguments']
        with self.assertRaises(PermissionError):
            await self.gateway.execute(task_id=task.task_id, tool_name='mock_book_hotel',
                arguments=args, idempotency_key=args['idempotency_key'])
        await self.runtime.decide(task.task_id, approval['approval_id'], True)
        with self.assertRaises(ValueError):
            await self.gateway.execute(task_id=task.task_id, tool_name='mock_book_hotel',
                arguments={**args, 'hotel_name': '其他酒店'},
                idempotency_key=args['idempotency_key'], approval_id=approval['approval_id'])

    async def test_revision_does_not_change_pending_snapshot(self):
        task = await self.create()
        proposal = await self.proposal(task)
        revision = await self.runtime.revise(task.request, plan(), '减少景点')
        self.assertNotEqual(revision.task_id, task.task_id)
        self.assertEqual(self.counts['weather'], 1)
        original = self.runtime.detail(task.task_id)
        self.assertEqual(original['pending_approval'], proposal['pending_approval'])

    async def test_mcp_adapter_calls_gateway_and_records_observation(self):
        task = await self.create()
        session = SimpleNamespace(call_tool=AsyncMock(return_value=SimpleNamespace(
            content=[SimpleNamespace(text='晴')], isError=False)))
        tool = AmapMCPTool(session, SimpleNamespace(name='weather', description='天气', inputSchema={}))
        self.registry.register_tool(tool)
        wrapped = GatewayBoundTool(tool, self.gateway, task.task_id)
        self.assertEqual(await wrapped.run(city='杭州'), '晴')
        session.call_tool.assert_awaited_once_with('weather', arguments={'city': '杭州'})
        self.assertEqual(self.store.list_tool_calls(task.task_id)[0].status, ToolCallStatus.SUCCESS)

    async def test_timeout_and_retry_recorded(self):
        task = await self.create()
        tool = SimpleNamespace(name='slow', run=AsyncMock(side_effect=[asyncio.TimeoutError(), 'ok']))
        self.registry.register_tool(tool, max_retries=1, timeout_ms=10)
        record = await self.gateway.execute(task_id=task.task_id, tool_name='slow', arguments={})
        self.assertEqual(record.status, ToolCallStatus.SUCCESS)
        self.assertEqual(record.retry_count, 1)
        async def slow():
            await asyncio.sleep(1)
        tool.run = slow
        self.registry.register_tool(tool, max_retries=0, timeout_ms=1)
        record = await self.gateway.execute(task_id=task.task_id, tool_name='slow', arguments={})
        self.assertEqual(record.status, ToolCallStatus.FAILED)

    async def test_task_agent_histories_are_isolated(self):
        source = SimpleAgent('planner', None)
        template = SimpleNamespace(agents={'trip_planner': source})
        a = scoped_master(template, self.gateway, 'a')
        b = scoped_master(template, self.gateway, 'b')
        a.agents['trip_planner']._history.append('private')
        self.assertEqual(b.agents['trip_planner']._history, [])
        self.assertEqual(source._history, [])

    async def test_actual_multi_agent_loop_uses_gateway_for_all_mcp_calls(self):
        from trip_planner import TripMaster
        from llm_client import LLMMessage, ToolCall, FunctionCall

        class Model:
            async def generate_response(self, messages, tools=None, **kwargs):
                if not tools:
                    return LLMMessage(plan().model_dump_json())
                if not any(m['role'] == 'tool' for m in messages):
                    return LLMMessage('', [ToolCall('test-call', FunctionCall(
                        tools[0]['function']['name'], {'city': '杭州'}))])
                return LLMMessage('查询结果：晴，西湖，测试酒店，120.1,30.2')

        session = SimpleNamespace(
            list_tools=AsyncMock(return_value=SimpleNamespace(tools=[
                SimpleNamespace(name=n, description=n, inputSchema={'type': 'object'})
                for n in ['amap_maps_weather', 'amap_text_search', 'amap_hotel_search']])),
            call_tool=AsyncMock(return_value=SimpleNamespace(
                isError=False, content=[SimpleNamespace(text='查询成功 120.1,30.2')]))
        )
        master = TripMaster(Model(), session)
        await master.initialize_team()
        register_travel_tools(master, self.registry)
        runtime = TravelPlanningRuntime(self.store, self.gateway, master)
        task = await runtime.create(TripRequest(**REQUEST))
        self.assertEqual(task.state, TaskState.COMPLETED, task.error)
        self.assertEqual(session.call_tool.await_count, 3)
        calls = self.store.list_tool_calls(task.task_id)
        self.assertEqual({c.tool_name for c in calls},
                         {'amap_maps_weather', 'amap_text_search', 'amap_hotel_search'})
        self.assertTrue(all(c.status == ToolCallStatus.SUCCESS for c in calls))
        self.assertTrue(all(not a._history for a in master.agents.values()))

    async def test_pending_approval_survives_restart_without_rerunning_planning(self):
        task = await self.create()
        proposal = await self.proposal(task)
        self.store.close()
        self.store = TravelTaskStore(self.path)
        self.gateway = TravelToolGateway(self.registry, self.store)
        self.runtime = TravelPlanningRuntime(self.store, self.gateway, None, self.factory)
        waiting = await self.runtime.resume(task.task_id)
        self.assertEqual(waiting.state, TaskState.WAITING_APPROVAL)
        result = await self.runtime.decide(task.task_id, proposal['pending_approval']['approval_id'], True)
        self.assertEqual(result.state, TaskState.COMPLETED)
        self.assertEqual(self.counts['plan'], 1)

    async def test_unknown_write_outcome_is_not_retried(self):
        task = await self.create()
        proposal = await self.proposal(task)
        tool = self.registry.get_tool('mock_book_hotel')
        tool.run = AsyncMock(side_effect=asyncio.TimeoutError())
        aid = proposal['pending_approval']['approval_id']
        result = await self.runtime.decide(task.task_id, aid, True)
        self.assertEqual(result.state, TaskState.FAILED)
        await self.runtime.resume(task.task_id)
        self.assertEqual(tool.run.await_count, 1)

    async def test_api_plan_modify_booking_and_failure_resume(self):
        import httpx
        import api
        from services.session_store import SessionStore
        sessions = SessionStore(os.path.join(self.tmp.name, 'sessions.db'))
        previous = api.mcp_manager.copy()
        api.mcp_manager.update(travel_runtime=self.runtime, master=object(),
                               parallel_planner=object(), session_store=sessions)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url='http://test') as client:
                response = await client.post('/api/plan', json=REQUEST)
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertIn('days', data)
                modified = await client.post('/api/modify', json={
                    'session_id': data['session_id'], 'instruction': '减少景点'})
                self.assertEqual(modified.status_code, 200, modified.text)
                self.assertNotEqual(modified.json()['task_id'], data['task_id'])
                tid = modified.json()['task_id']
                proposal = await client.post(f'/api/travel/tasks/{tid}/booking-proposal',
                    json={'day_index': 1, 'guest_names': ['演示用户']})
                self.assertEqual(proposal.status_code, 200, proposal.text)
                aid = proposal.json()['pending_approval']['approval_id']
                approved = await client.post(f'/api/travel/tasks/{tid}/approvals/{aid}/approve')
                self.assertEqual(approved.status_code, 200, approved.text)
                self.assertTrue(approved.json()['result']['booking']['simulation'])
                detail = await client.get(f'/api/travel/tasks/{tid}')
                self.assertTrue(detail.json()['events'])
                self.fail_hotels = True
                failed = await client.post('/api/plan', json=REQUEST)
                self.assertEqual(failed.status_code, 502, failed.text)
                tid = failed.json()['detail']['task_id']
                self.fail_hotels = False
                recovered = await client.post(f'/api/travel/tasks/{tid}/resume')
                self.assertEqual(recovered.json()['state'], 'COMPLETED')
                self.assertIsNotNone(sessions.get_session(recovered.json()['session_id']))
        finally:
            api.mcp_manager.clear()
            api.mcp_manager.update(previous)
            sessions.close()


if __name__ == '__main__':
    unittest.main()

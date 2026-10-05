# app/observability/agent_observer.py
"""
智能体执行链路观测模块。

当前职责模型保持三层结构：
- 智能体观测入口管理某个智能体的执行记录。
- 执行记录表示一次具体执行，并持有本次执行的运行时状态。
- 迭代、工具调用和模型调用记录表示执行过程中的明细。
"""
import time
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from .observer_framework import observer, EventType


@dataclass
class ToolCallRecord:
    """一次智能体执行中的工具调用记录。"""

    tool_name: str
    start_time: float
    end_time: float = 0
    duration: float = 0
    success: bool = True
    error_message: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    result_preview: str = ""

    def finish(self, success: bool = True, error_message: str = "", result_preview: str = ""):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error_message = error_message
        self.result_preview = result_preview[:200] if result_preview else ""

    def to_dict(self) -> Dict:
        return {
            "tool_name": self.tool_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "success": self.success,
            "error_message": self.error_message,
            "arguments": self.arguments,
            "result_preview": self.result_preview,
        }


@dataclass
class ReActIterationRecord:
    """一次智能体执行中的推理行动迭代记录。"""

    iteration: int
    thought: str
    start_time: float
    action: str = ""
    action_input: Dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    end_time: float = 0
    duration: float = 0
    token_used: int = 0

    def finish(
        self,
        action: str = "",
        action_input: Optional[Dict] = None,
        observation: str = "",
        token_used: int = 0,
    ):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.action = action
        self.action_input = action_input or {}
        self.observation = observation[:500] if observation else ""
        self.token_used = token_used

    def to_dict(self) -> Dict:
        return {
            "iteration": self.iteration,
            "thought": self.thought[:500] if self.thought else "",
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "duration": self.duration,
            "token_used": self.token_used,
        }


@dataclass
class LLMCallRecord:
    """一次智能体执行关联的大语言模型调用记录。"""

    model: str
    input_tokens: int
    output_tokens: int
    start_time: float
    end_time: float = 0
    duration: float = 0
    cost: float = 0
    cached: bool = False

    def finish(
        self,
        output_tokens: Optional[int] = None,
        cached: bool = False,
        input_price: float = 0.001,
        output_price: float = 0.002,
        duration: Optional[float] = None,
    ):
        self.end_time = time.time()
        self.duration = duration if duration is not None else self.end_time - self.start_time
        if output_tokens is not None:
            self.output_tokens = output_tokens
        self.cached = cached
        self.cost = (
            self.input_tokens * input_price / 1000
            + self.output_tokens * output_price / 1000
        )

    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> Dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens(),
            "duration": self.duration,
            "cost": self.cost,
            "cached": self.cached,
        }


@dataclass
class AgentExecutionRecord:
    """一次智能体执行的运行时状态和最终链路记录。"""

    trace_id: str
    agent_name: str
    session_id: str
    start_time: float
    end_time: float = 0
    duration: float = 0
    iterations: List[ReActIterationRecord] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    llm_calls: List[LLMCallRecord] = field(default_factory=list)
    current_iteration: Optional[ReActIterationRecord] = None
    tool_call_stack: List[ToolCallRecord] = field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0
    success: bool = True
    error_message: str = ""
    final_response_preview: str = ""

    def start_iteration(self, iteration: int, thought: str):
        self.current_iteration = ReActIterationRecord(
            iteration=iteration,
            thought=thought,
            start_time=time.time(),
        )

        observer.record_event(EventType.REACT_ITERATION, {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "iteration": iteration,
            "thought_preview": thought[:200],
        })

    def end_iteration(
        self,
        action: str = "",
        action_input: Optional[Dict] = None,
        observation: str = "",
        token_used: int = 0,
    ):
        if not self.current_iteration:
            return

        self.current_iteration.finish(action, action_input, observation, token_used)
        self.iterations.append(self.current_iteration)

        observer.record_histogram(
            "react_iteration_duration",
            self.current_iteration.duration,
            {"agent": self.agent_name, "iteration": self.current_iteration.iteration},
        )
        self.current_iteration = None

    def record_llm_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
        cached: bool = False,
        duration: Optional[float] = None,
    ):
        llm_record = LLMCallRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            start_time=time.time(),
        )
        llm_record.finish(output_tokens, cached, duration=duration)
        self.llm_calls.append(llm_record)

    def start_tool_call(self, tool_name: str, arguments: Optional[Dict] = None):
        tool_record = ToolCallRecord(
            tool_name=tool_name,
            start_time=time.time(),
            arguments=arguments or {},
        )
        self.tool_call_stack.append(tool_record)

        observer.record_event(EventType.TOOL_CALL_START, {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "tool_name": tool_name,
            "arguments_preview": str(arguments)[:200] if arguments else "",
        })

    def end_tool_call(
        self,
        success: bool = True,
        error_message: str = "",
        result_preview: str = "",
    ):
        if not self.tool_call_stack:
            return

        tool_record = self.tool_call_stack.pop()
        tool_record.finish(success, error_message, result_preview)
        self.tool_calls.append(tool_record)

        tags = {
            "agent": self.agent_name,
            "tool": tool_record.tool_name,
            "success": str(success),
        }
        observer.record_counter("tool_calls_total", 1, tags)
        observer.record_histogram("tool_call_duration", tool_record.duration, tags)
        observer.record_event(EventType.TOOL_CALL_END, {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "tool_name": tool_record.tool_name,
            "success": success,
            "duration": tool_record.duration,
            "error_message": error_message,
        })

    def finish(
        self,
        success: bool = True,
        error_message: str = "",
        response_preview: str = "",
    ):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error_message = error_message
        self.final_response_preview = response_preview[:500] if response_preview else ""
        self.total_tokens = sum(llm.total_tokens() for llm in self.llm_calls)
        self.total_cost = sum(llm.cost for llm in self.llm_calls)

        tags = {"agent": self.agent_name}
        observer.record_counter("agent_requests_total", 1, tags)
        observer.record_histogram("agent_duration", self.duration, tags)
        observer.record_counter("agent_tokens_total", self.total_tokens, tags)
        observer.record_histogram(
            "agent_llm_duration",
            sum(llm.duration for llm in self.llm_calls),
            tags,
        )

        if not success:
            observer.record_counter("agent_errors_total", 1, tags)

        observer.record_event(EventType.AGENT_END, {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "success": success,
            "duration": self.duration,
            "total_tokens": self.total_tokens,
            "error_message": error_message,
        })

    def to_dict(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "iterations": [it.to_dict() for it in self.iterations],
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "llm_calls": [llm.to_dict() for llm in self.llm_calls],
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "success": self.success,
            "error_message": self.error_message,
            "final_response_preview": self.final_response_preview,
        }


class AgentInstrumentor:
    """智能体层观测入口，负责创建、索引和归档执行记录。"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.latest_execution: Optional[AgentExecutionRecord] = None
        self.active_executions: Dict[str, AgentExecutionRecord] = {}

    def start_execution(self, session_id: str, user_input: str) -> AgentExecutionRecord:
        trace_id = f"{self.agent_name}_{uuid.uuid4().hex}"
        execution = AgentExecutionRecord(
            trace_id=trace_id,
            agent_name=self.agent_name,
            session_id=session_id,
            start_time=time.time(),
        )
        self.active_executions[trace_id] = execution

        observer.record_event(EventType.AGENT_START, {
            "trace_id": trace_id,
            "agent_name": self.agent_name,
            "session_id": session_id,
            "user_input_preview": user_input[:200],
        })

        return execution

    def finish_execution(self, execution: AgentExecutionRecord):
        self.latest_execution = execution
        self.active_executions.pop(execution.trace_id, None)
        observer.on_trace(execution)

    def get_execution_chain(self, trace_id: Optional[str] = None) -> List[Dict]:
        execution = self._resolve_execution(trace_id)
        if not execution:
            return []

        return [
            {
                "iteration": iteration.iteration,
                "thought": iteration.thought[:300],
                "action": iteration.action,
                "observation": iteration.observation[:300] if iteration.observation else "",
            }
            for iteration in execution.iterations
        ]

    def get_summary(self, trace_id: Optional[str] = None) -> Dict:
        execution = self._resolve_execution(trace_id)
        if not execution:
            return {}

        tool_stats = {}
        for tool_call in execution.tool_calls:
            if tool_call.tool_name not in tool_stats:
                tool_stats[tool_call.tool_name] = {
                    "count": 0,
                    "total_duration": 0,
                    "failures": 0,
                }
            tool_stats[tool_call.tool_name]["count"] += 1
            tool_stats[tool_call.tool_name]["total_duration"] += tool_call.duration
            if not tool_call.success:
                tool_stats[tool_call.tool_name]["failures"] += 1

        return {
            "trace_id": execution.trace_id,
            "agent_name": execution.agent_name,
            "duration": execution.duration,
            "total_tokens": execution.total_tokens,
            "total_cost": execution.total_cost,
            "iterations": len(execution.iterations),
            "tool_calls": len(execution.tool_calls),
            "llm_calls": len(execution.llm_calls),
            "tool_stats": tool_stats,
            "success": execution.success,
            "error_message": execution.error_message,
        }

    def get_dashboard(self, trace_id: Optional[str] = None) -> Dict:
        execution = self._resolve_execution(trace_id)
        if not execution:
            return {
                "agent_name": self.agent_name,
                "has_execution": False,
                "active_executions": len(self.active_executions),
            }

        return {
            "agent_name": self.agent_name,
            "has_execution": True,
            "active_executions": len(self.active_executions),
            "summary": self.get_summary(trace_id),
            "iterations": [iteration.to_dict() for iteration in execution.iterations],
            "tool_calls": [tool_call.to_dict() for tool_call in execution.tool_calls],
            "llm_calls": [llm_call.to_dict() for llm_call in execution.llm_calls],
        }

    def _resolve_execution(self, trace_id: Optional[str] = None) -> Optional[AgentExecutionRecord]:
        if trace_id:
            return self.active_executions.get(trace_id)
        return self.latest_execution


_agent_instrumentors: Dict[str, AgentInstrumentor] = {}


def get_agent_instrumentor(agent_name: str) -> AgentInstrumentor:
    if agent_name not in _agent_instrumentors:
        _agent_instrumentors[agent_name] = AgentInstrumentor(agent_name)
    return _agent_instrumentors[agent_name]


def get_all_agent_dashboards() -> Dict[str, Dict]:
    return {
        agent_name: instrumentor.get_dashboard()
        for agent_name, instrumentor in _agent_instrumentors.items()
    }

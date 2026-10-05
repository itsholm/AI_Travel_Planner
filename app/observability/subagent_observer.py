# app/observability/subagent_observer.py
"""
Sub-Agent协作监控模块
监控多Agent并行执行、协作效率等
"""
import time
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from .observer_framework import (
    observer, EventType, MetricType
)

@dataclass
class SubAgentCallRecord:
    """Sub-Agent调用记录"""
    agent_name: str
    session_id: str
    start_time: float
    end_time: float = 0
    duration: float = 0
    success: bool = True
    error_message: str = ""
    input_preview: str = ""
    output_preview: str = ""
    tokens_used: int = 0
    
    def finish(self, success: bool = True, error_message: str = "",
              output_preview: str = "", tokens_used: int = 0):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.error_message = error_message
        self.output_preview = output_preview[:200] if output_preview else ""
        self.tokens_used = tokens_used
    
    def to_dict(self) -> Dict:
        return {
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "success": self.success,
            "error_message": self.error_message,
            "input_preview": self.input_preview[:200] if self.input_preview else "",
            "output_preview": self.output_preview,
            "tokens_used": self.tokens_used
        }

@dataclass
class ParallelExecutionRecord:
    """并行执行记录"""
    execution_id: str
    session_id: str
    start_time: float
    agents: List[str] = field(default_factory=list)
    agent_records: List[SubAgentCallRecord] = field(default_factory=list)
    end_time: float = 0
    total_duration: float = 0
    parallel_duration: float = 0  # 实际并行执行时间
    serial_duration: float = 0    # 如果串行执行需要的时间
    speedup_ratio: float = 0      # 加速比
    success: bool = True
    
    def finish(self, success: bool = True):
        self.end_time = time.time()
        self.total_duration = self.end_time - self.start_time
        self.parallel_duration = max((r.end_time - r.start_time) for r in self.agent_records) if self.agent_records else 0
        self.serial_duration = sum(r.duration for r in self.agent_records) if self.agent_records else 0
        self.speedup_ratio = self.serial_duration / self.parallel_duration if self.parallel_duration > 0 else 1.0
        self.success = success
        
        # 记录并行执行指标
        observer.record_histogram("parallel_execution_duration", self.parallel_duration)
        observer.record_histogram("speedup_ratio", self.speedup_ratio)
        observer.record_gauge("parallel_efficiency", self.speedup_ratio / len(self.agents) if self.agents else 0)
    
    def to_dict(self) -> Dict:
        return {
            "execution_id": self.execution_id,
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration": self.total_duration,
            "parallel_duration": self.parallel_duration,
            "serial_duration": self.serial_duration,
            "speedup_ratio": self.speedup_ratio,
            "agents": self.agents,
            "agent_records": [r.to_dict() for r in self.agent_records],
            "success": self.success
        }

@dataclass
class CollaborationRecord:
    """协作记录"""
    session_id: str
    timestamp: float
    collaboration_type: str  # sequential, parallel, hierarchical
    participants: List[str]
    message_passes: int  # 消息传递次数
    shared_context_size: int  # 共享上下文大小
    coordination_overhead: float  # 协调开销
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "collaboration_type": self.collaboration_type,
            "participants": self.participants,
            "message_passes": self.message_passes,
            "shared_context_size": self.shared_context_size,
            "coordination_overhead": self.coordination_overhead
        }

class SubAgentInstrumentor:
    """Sub-Agent仪器化追踪器"""
    
    def __init__(self):
        self.agent_calls: List[SubAgentCallRecord] = []
        self.parallel_executions: List[ParallelExecutionRecord] = []
        self.collaboration_records: List[CollaborationRecord] = []
        self._agent_call_counts: Dict[str, int] = defaultdict(int)
        self._agent_total_duration: Dict[str, float] = defaultdict(float)
    
    def start_agent_call(self, agent_name: str, session_id: str, 
                        input_preview: str = "") -> SubAgentCallRecord:
        """开始Agent调用"""
        record = SubAgentCallRecord(
            agent_name=agent_name,
            session_id=session_id,
            start_time=time.time(),
            input_preview=input_preview
        )
        
        self._agent_call_counts[agent_name] += 1
        
        observer.record_counter("subagent_calls_total", 1, {"agent": agent_name})
        observer.record_event(EventType.SUBAGENT_CALL, {
            "agent_name": agent_name,
            "session_id": session_id,
            "action": "start"
        })
        
        return record
    
    def end_agent_call(self, record: SubAgentCallRecord, success: bool = True,
                      error_message: str = "", output_preview: str = "",
                      tokens_used: int = 0):
        """结束Agent调用"""
        record.finish(success, error_message, output_preview, tokens_used)
        self.agent_calls.append(record)
        
        self._agent_total_duration[record.agent_name] += record.duration
        
        observer.record_event(EventType.SUBAGENT_CALL, {
            "agent_name": record.agent_name,
            "session_id": record.session_id,
            "action": "end",
            "duration": record.duration,
            "success": success
        })
        
        observer.record_histogram("subagent_call_duration", record.duration, {"agent": record.agent_name})
    
    def start_parallel_execution(self, execution_id: str, session_id: str,
                               agents: List[str]) -> ParallelExecutionRecord:
        """开始并行执行"""
        record = ParallelExecutionRecord(
            execution_id=execution_id,
            session_id=session_id,
            start_time=time.time(),
            agents=agents
        )
        
        observer.record_event(EventType.AGENT_START, {
            "execution_id": execution_id,
            "agents": agents,
            "type": "parallel"
        })
        
        return record
    
    def add_agent_record(self, execution_record: ParallelExecutionRecord,
                        agent_record: SubAgentCallRecord):
        """添加Agent执行记录到并行执行"""
        execution_record.agent_records.append(agent_record)
    
    def end_parallel_execution(self, execution_record: ParallelExecutionRecord,
                              success: bool = True):
        """结束并行执行"""
        execution_record.finish(success)
        self.parallel_executions.append(execution_record)
        
        observer.record_event(EventType.AGENT_END, {
            "execution_id": execution_record.execution_id,
            "parallel_duration": execution_record.parallel_duration,
            "speedup_ratio": execution_record.speedup_ratio,
            "success": success
        })
    
    def record_collaboration(self, session_id: str, collaboration_type: str,
                           participants: List[str], message_passes: int = 0,
                           shared_context_size: int = 0, coordination_overhead: float = 0):
        """记录协作事件"""
        record = CollaborationRecord(
            session_id=session_id,
            timestamp=time.time(),
            collaboration_type=collaboration_type,
            participants=participants,
            message_passes=message_passes,
            shared_context_size=shared_context_size,
            coordination_overhead=coordination_overhead
        )
        
        self.collaboration_records.append(record)
        
        observer.record_histogram("coordination_overhead", coordination_overhead,
                                {"type": collaboration_type})
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """获取各Agent统计"""
        stats = {}
        for agent_name in self._agent_call_counts:
            call_count = self._agent_call_counts[agent_name]
            total_duration = self._agent_total_duration.get(agent_name, 0)
            
            # 获取该Agent的成功率
            agent_calls = [c for c in self.agent_calls if c.agent_name == agent_name]
            success_count = sum(1 for c in agent_calls if c.success)
            
            stats[agent_name] = {
                "call_count": call_count,
                "total_duration": total_duration,
                "avg_duration": total_duration / call_count if call_count > 0 else 0,
                "success_rate": (success_count / call_count * 100) if call_count > 0 else 100,
                "total_tokens": sum(c.tokens_used for c in agent_calls)
            }
        
        return stats
    
    def get_parallel_execution_stats(self) -> Dict[str, Any]:
        """获取并行执行统计"""
        if not self.parallel_executions:
            return {
                "total_executions": 0,
                "avg_speedup_ratio": 0,
                "avg_parallel_duration": 0,
                "avg_efficiency": 0
            }
        
        total = len(self.parallel_executions)
        successful = sum(1 for e in self.parallel_executions if e.success)
        avg_speedup = sum(e.speedup_ratio for e in self.parallel_executions) / total
        avg_parallel = sum(e.parallel_duration for e in self.parallel_executions) / total
        avg_efficiency = sum(e.speedup_ratio / len(e.agents) if e.agents else 0 
                           for e in self.parallel_executions) / total
        
        return {
            "total_executions": total,
            "successful_executions": successful,
            "success_rate": (successful / total * 100) if total > 0 else 100,
            "avg_speedup_ratio": avg_speedup,
            "avg_parallel_duration": avg_parallel,
            "avg_efficiency": avg_efficiency,
            "max_speedup_ratio": max(e.speedup_ratio for e in self.parallel_executions),
            "min_speedup_ratio": min(e.speedup_ratio for e in self.parallel_executions)
        }
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取Sub-Agent监控仪表盘"""
        return {
            "agent_stats": self.get_agent_stats(),
            "parallel_execution_stats": self.get_parallel_execution_stats(),
            "total_agent_calls": len(self.agent_calls),
            "total_parallel_executions": len(self.parallel_executions)
        }

# 全局Sub-Agent仪器化追踪器
subagent_instrumentor = SubAgentInstrumentor()

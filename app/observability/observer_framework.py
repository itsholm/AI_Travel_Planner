# app/observability/observer_framework.py
"""
统一观测者框架 - 为项目提供全面的可观测性支持
"""
import time
import json
import logging
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from collections import defaultdict
import threading
import uuid

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"       # 计数器
    GAUGE = "gauge"           # 瞬时值
    HISTOGRAM = "histogram"    # 直方图
    TRACE = "trace"           # 链路追踪
    LOG = "log"               # 日志

from .execution_context import current_execution

class EventType(Enum):
    RUNTIME_EVENT = "runtime_event"
    """事件类型"""
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_COMPLETE = "agent_complete"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    LLM_CALL_START = "llm_call_start"
    LLM_CALL_END = "llm_call_end"
    REACT_ITERATION = "react_iteration"
    INPUT_VALIDATION = "input_validation"
    OUTPUT_VALIDATION = "output_validation"
    INJECTION_DETECTED = "injection_detected"
    RISK_ASSESSMENT = "risk_assessment"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SUBAGENT_CALL = "subagent_call"
    HARNESS_CHECK = "harness_check"
    EXTERNAL_SERVICE_CALL = "external_service_call"
    PLANNING_START = "planning_start"
    PLANNING_COMPLETE = "planning_complete"
    HTTP_REQUEST = "http_request"

@dataclass
class MetricPoint:
    """指标点"""
    name: str
    value: float
    metric_type: MetricType
    timestamp: str
    tags: Dict[str, str] = field(default_factory=dict)
    trace_id: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "value": self.value,
            "metric_type": self.metric_type.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
            "trace_id": self.trace_id
        }

@dataclass
class TraceSpan:
    """链路追踪span"""
    trace_id: str
    span_id: str
    parent_span_id: str
    operation_name: str
    start_time: float
    end_time: float = 0
    duration: float = 0
    tags: Dict[str, str] = field(default_factory=dict)
    logs: List[Dict] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    
    def finish(self):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
    
    def to_dict(self) -> Dict:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "tags": self.tags,
            "logs": self.logs,
            "children": self.children
        }

@dataclass
class ObservationEvent:
    """观测事件"""
    event_type: EventType
    timestamp: str
    data: Dict[str, Any]
    trace_id: str = ""
    span_id: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "trace_id": self.trace_id,
            "span_id": self.span_id
        }

class Observer: #父类
    """观测者接口"""
    def on_metric(self, metric: MetricPoint):
        raise NotImplementedError
    
    def on_event(self, event: ObservationEvent):
        raise NotImplementedError
    
    def on_trace(self, trace: TraceSpan):
        raise NotImplementedError

class MetricsObserver(Observer):
    """指标收集观测者"""
    
    def __init__(self):
        self.counters: Dict[str, float] = defaultdict(float)
        self.gauges: Dict[str, float] = {}
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.Lock()
    
    def on_metric(self, metric: MetricPoint):
        with self.lock:
            if metric.metric_type == MetricType.COUNTER:
                self.counters[metric.name] += metric.value
            elif metric.metric_type == MetricType.GAUGE:
                self.gauges[metric.name] = metric.value
            elif metric.metric_type == MetricType.HISTOGRAM:
                self.histograms[metric.name].append(metric.value)
    
    def on_event(self, event: ObservationEvent):
        pass
    
    def on_trace(self, trace: TraceSpan):
        pass
    
    def get_counter(self, name: str) -> float:
        return self.counters.get(name, 0)
    
    def get_gauge(self, name: str) -> Optional[float]:
        return self.gauges.get(name)
    
    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        values = self.histograms.get(name, [])
        if not values:
            return {}
        
        sorted_values = sorted(values)
        count = len(values)
        
        return {
            "count": count,
            "sum": sum(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / count,
            "p50": sorted_values[count // 2],
            "p95": sorted_values[int(count * 0.95)] if count > 1 else sorted_values[0],
            "p99": sorted_values[int(count * 0.99)] if count > 1 else sorted_values[0],
        }
    
    def get_all_metrics(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "histograms": {
                    name: self.get_histogram_stats(name) 
                    for name in self.histograms.keys()
                }
            }

class TraceObserver(Observer):
    """链路追踪观测者"""
    
    def __init__(self, max_traces: int = 1000):
        self.traces: Dict[str, List[TraceSpan]] = defaultdict(list)
        self.max_traces = max_traces
        self.lock = threading.Lock()
    
    def on_metric(self, metric: MetricPoint):
        pass
    
    def on_event(self, event: ObservationEvent):
        pass
    
    def on_trace(self, trace: TraceSpan):
        with self.lock:
            self.traces[trace.trace_id].append(trace)
            
            # 限制存储数量
            if len(self.traces) > self.max_traces:
                oldest = min(self.traces.keys())
                del self.traces[oldest]
    
    def get_trace(self, trace_id: str) -> List[TraceSpan]:
        return self.traces.get(trace_id, [])
    
    def get_all_traces(self) -> Dict[str, List[Dict]]:
        with self.lock:
            return {
                trace_id: [span.to_dict() for span in spans]
                for trace_id, spans in self.traces.items()
            }

class LogObserver(Observer):
    """日志观测者"""
    
    def __init__(self, max_logs: int = 10000):
        self.events: List[ObservationEvent] = []
        self.max_logs = max_logs
        self.lock = threading.Lock()
    
    def on_metric(self, metric: MetricPoint):
        pass
    
    def on_event(self, event: ObservationEvent):
        with self.lock:
            self.events.append(event)
            
            # 限制存储数量
            if len(self.events) > self.max_logs:
                self.events = self.events[-self.max_logs:]
    
    def on_trace(self, trace: TraceSpan):
        pass
    
    def get_events(self, event_type: EventType = None, limit: int = 100) -> List[Dict]:
        with self.lock:
            events = self.events
            if event_type:
                events = [e for e in events if e.event_type == event_type]
            return [e.to_dict() for e in events[-limit:]]

class TracingContext:
    """链路追踪上下文"""
    
    def __init__(self, observer_manager: 'ObserverManager', operation_name: str, tags: Dict = None):
        self.observer_manager = observer_manager
        self.operation_name = operation_name
        self.tags = tags or {}
        self.trace_id = ""
        self.span_id = ""
        self.parent_span_id = ""
        self.start_time = 0
        self.span: Optional[TraceSpan] = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.trace_id = self.observer_manager.trace_id or str(uuid.uuid4())
        self.span_id = str(uuid.uuid4())
        self.parent_span_id = self.observer_manager.current_span_id or ""
        
        self.span = TraceSpan(
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            operation_name=self.operation_name,
            start_time=self.start_time,
            tags=self.tags
        )
        
        self.observer_manager.push_span(self.span)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.span.finish()
        
        if exc_type:
            self.span.tags["error"] = str(exc_val)
            self.span.tags["error_type"] = exc_type.__name__
        
        self.observer_manager.on_trace(self.span)
        self.observer_manager.pop_span()
        
        return False
    
    def add_tag(self, key: str, value: str):
        if self.span:
            self.span.tags[key] = value
    
    def add_log(self, message: str, data: Dict = None):
        if self.span:
            self.span.logs.append({
                "timestamp": datetime.now().isoformat(),
                "message": message,
                "data": data or {}
            })

class ObserverManager:
    """观测者管理器（单例）"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.observers: List[Observer] = []
        self.metrics_observer = MetricsObserver()
        self.trace_observer = TraceObserver()
        self.log_observer = LogObserver()
        
        #初始化了3个观测对象，分别是指标观测者、链路观测者、日志观测者
        self.observers.extend([
            self.metrics_observer,
            self.trace_observer,
            self.log_observer
        ])
        
        self.trace_id: str = ""
        self.current_span_id: str = ""
        self._span_stack: List[TraceSpan] = []
    
    def add_observer(self, observer: Observer):
        self.observers.append(observer)
    
    def record_metric(self, name: str, value: float, metric_type: MetricType, tags: Dict = None):
        #全局观察者 创建一条指标
        metric = MetricPoint(
            name=name,
            value=value,
            metric_type=metric_type,
            timestamp=datetime.now().isoformat(),
            tags={**(tags or {}), **current_execution()},
            trace_id=current_execution().get("trace_id", self.trace_id)
        )
        #分发给所有子observer处理
        for observer in self.observers:
            observer.on_metric(metric)
    
    def record_counter(self, name: str, value: float = 1, tags: Dict = None):
        self.record_metric(name, value, MetricType.COUNTER, tags)
    
    def record_gauge(self, name: str, value: float, tags: Dict = None):
        self.record_metric(name, value, MetricType.GAUGE, tags)
    
    def record_histogram(self, name: str, value: float, tags: Dict = None):
        self.record_metric(name, value, MetricType.HISTOGRAM, tags)
    
    def record_event(self, event_type: EventType, data: Dict):
        event = ObservationEvent(
            event_type=event_type,
            timestamp=datetime.now().isoformat(),
            data={**data, **current_execution()},
            trace_id=current_execution().get("trace_id", data.get("task_id", self.trace_id)),
            span_id=self.current_span_id
        )
        
        for observer in self.observers:
            observer.on_event(event)
    
    def on_trace(self, trace: TraceSpan):
        for observer in self.observers:
            observer.on_trace(trace)
    
    def push_span(self, span: TraceSpan):
        self._span_stack.append(span)
        self.current_span_id = span.span_id
        if not self.trace_id:
            self.trace_id = span.trace_id
    
    def pop_span(self):
        self._span_stack.pop()
        self.current_span_id = self._span_stack[-1].span_id if self._span_stack else ""
    
    def create_context(self, operation_name: str, tags: Dict = None) -> TracingContext:
        return TracingContext(self, operation_name, tags)
    
    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics_observer.get_all_metrics()
    
    def get_traces(self) -> Dict[str, List[Dict]]:
        return self.trace_observer.get_all_traces()
    
    def get_events(self, event_type: EventType = None, limit: int = 100) -> List[Dict]:
        return self.log_observer.get_events(event_type, limit)
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取完整的可观测性仪表盘数据"""
        metrics = self.get_metrics()
        traces = self.get_traces()
        events = self.get_events(limit=100)
        
        # 聚合关键指标
        summary = {
            "total_requests": metrics.get("counters", {}).get("agent_requests_total", 0),
            "total_tool_calls": metrics.get("counters", {}).get("tool_calls_total", 0),
            "total_llm_calls": metrics.get("counters", {}).get("llm_calls_total", 0),
            "total_tokens": metrics.get("counters", {}).get("tokens_total", 0),
            "injection_attempts": metrics.get("counters", {}).get("injection_detected_total", 0),
            "avg_response_time": metrics.get("histograms", {}).get("agent_duration", {}).get("avg", 0),
            "error_rate": self._calculate_error_rate(metrics),
        }
        
        return {
            "summary": summary,
            "metrics": metrics,
            "traces": traces,
            "recent_events": events
        }
    
    def _calculate_error_rate(self, metrics: Dict) -> float:
        total = metrics.get("counters", {}).get("agent_requests_total", 0)
        errors = metrics.get("counters", {}).get("agent_errors_total", 0)
        
        if total == 0:
            return 0.0
        
        return round(errors / total * 100, 2)
    
    def reset(self):
        """重置所有观测数据（用于测试）"""
        self.metrics_observer = MetricsObserver()
        self.trace_observer = TraceObserver()
        self.log_observer = LogObserver()
        
        self.observers = [
            self.metrics_observer,
            self.trace_observer,
            self.log_observer
        ]
        
        self.trace_id = ""
        self.current_span_id = ""
        self._span_stack = []

# 全局观测者管理器
observer = ObserverManager()

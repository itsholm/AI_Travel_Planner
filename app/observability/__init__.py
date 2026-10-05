# app/observability/__init__.py
"""
可观测性模块
"""
from .observer_framework import (
    observer,
    ObserverManager,
    Observer,
    MetricsObserver,
    TraceObserver,
    LogObserver,
    TracingContext,
    MetricType,
    EventType,
    MetricPoint,
    TraceSpan,
    ObservationEvent
)

from .agent_observer import (
    AgentInstrumentor,
    get_agent_instrumentor,
    get_all_agent_dashboards,
    ToolCallRecord,
    ReActIterationRecord,
    LLMCallRecord,
    AgentExecutionRecord
)

from .security_observer import (
    security_instrumentor,
    SecurityInstrumentor,
    InputValidationRecord,
    OutputValidationRecord,
    SecurityEventRecord
)

from .subagent_observer import (
    subagent_instrumentor,
    SubAgentInstrumentor,
    SubAgentCallRecord,
    ParallelExecutionRecord,
    CollaborationRecord
)

from .session_observer import (
    session_instrumentor,
    SessionInstrumentor,
    SessionStateRecord,
    ContextCompressionRecord,
    SessionEventRecord
)

from .external_service_observer import (
    external_service_instrumentor,
    ExternalServiceInstrumentor,
    ServiceStatus,
    ExternalServiceCallRecord,
    ServiceHealthRecord
)

from .http_observer import (
    http_instrumentor,
    setup_http_observability,
    HttpPerformanceInstrumentor,
    HttpRequestRecord,
    EndpointStats
)

__all__ = [
    # Framework
    "observer",
    "ObserverManager",
    "Observer",
    "MetricsObserver",
    "TraceObserver",
    "LogObserver",
    "TracingContext",
    "MetricType",
    "EventType",
    "MetricPoint",
    "TraceSpan",
    "ObservationEvent",
    # Agent
    "AgentInstrumentor",
    "get_agent_instrumentor",
    "get_all_agent_dashboards",
    "ToolCallRecord",
    "ReActIterationRecord",
    "LLMCallRecord",
    "AgentExecutionRecord",
    # Security
    "security_instrumentor",
    "SecurityInstrumentor",
    "InputValidationRecord",
    "OutputValidationRecord",
    "SecurityEventRecord",
    # SubAgent
    "subagent_instrumentor",
    "SubAgentInstrumentor",
    "SubAgentCallRecord",
    "ParallelExecutionRecord",
    "CollaborationRecord",
    # Session
    "session_instrumentor",
    "SessionInstrumentor",
    "SessionStateRecord",
    "ContextCompressionRecord",
    "SessionEventRecord",
    # External Service
    "external_service_instrumentor",
    "ExternalServiceInstrumentor",
    "ServiceStatus",
    "ExternalServiceCallRecord",
    "ServiceHealthRecord",
    # HTTP
    "http_instrumentor",
    "setup_http_observability",
    "HttpPerformanceInstrumentor",
    "HttpRequestRecord",
    "EndpointStats",
]

# app/observability/api_endpoints.py
"""
可观测性API端点
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime

from .observer_framework import observer, EventType
from .agent_observer import get_agent_instrumentor, get_all_agent_dashboards
from .security_observer import security_instrumentor
from .subagent_observer import subagent_instrumentor
from .session_observer import session_instrumentor
from .external_service_observer import external_service_instrumentor
from .http_observer import http_instrumentor

router = APIRouter(prefix="/api/observability", tags=["可观测性"])

@router.get("/dashboard")
async def get_observability_dashboard() -> Dict[str, Any]:
    """
    获取完整的可观测性仪表盘
    
    包含：
    - 总体指标摘要
    - Agent执行链路追踪
    - 安全监控数据
    - Sub-Agent协作数据
    - 会话状态数据
    - 外部服务健康状态
    """
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "dashboard": {
            "summary": observer.get_metrics(),
            "agent": _get_agent_dashboard(),
            "security": security_instrumentor.get_dashboard(),
            "subagent": subagent_instrumentor.get_dashboard(),
            "session": session_instrumentor.get_dashboard(),
            "external_services": external_service_instrumentor.get_dashboard(),
            "http": http_instrumentor.get_dashboard()
        }
    }

@router.get("/metrics")
async def get_metrics() -> Dict[str, Any]:
    """获取所有指标数据"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "metrics": observer.get_metrics()
    }

@router.get("/metrics/counters")
async def get_counters() -> Dict[str, Any]:
    """获取计数器指标"""
    metrics = observer.get_metrics()
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "counters": metrics.get("counters", {})
    }

@router.get("/metrics/gauges")
async def get_gauges() -> Dict[str, Any]:
    """获取仪表盘指标"""
    metrics = observer.get_metrics()
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "gauges": metrics.get("gauges", {})
    }

@router.get("/metrics/histograms")
async def get_histograms() -> Dict[str, Any]:
    """获取直方图指标"""
    metrics = observer.get_metrics()
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "histograms": metrics.get("histograms", {})
    }

@router.get("/traces")
async def get_traces(limit: int = 100) -> Dict[str, Any]:
    """获取链路追踪数据"""
    traces = observer.get_traces()
    
    # 按时间排序，只返回最新的limit条
    sorted_traces = sorted(
        traces.items(),
        key=lambda x: x[1][0].get("start_time", 0) if x[1] else 0,
        reverse=True
    )[:limit]
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "traces_count": len(traces),
        "traces": dict(sorted_traces)
    }

@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str) -> Dict[str, Any]:
    """获取特定追踪的详细信息"""
    traces = observer.get_traces()
    
    if trace_id not in traces:
        raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "trace": traces[trace_id]
    }

@router.get("/events")
async def get_events(event_type: str = None, limit: int = 100) -> Dict[str, Any]:
    """获取事件日志"""
    event_type_enum = None
    if event_type:
        try:
            event_type_enum = EventType(event_type)
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid event type: {event_type}. Valid types: {[e.value for e in EventType]}"
            )
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "events": observer.get_events(event_type_enum, limit)
    }

@router.get("/http/dashboard")
async def get_http_dashboard() -> Dict[str, Any]:
    """Return HTTP request performance metrics."""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "dashboard": http_instrumentor.get_dashboard()
    }

@router.get("/http/summary")
async def get_http_summary() -> Dict[str, Any]:
    """Return aggregated HTTP performance metrics."""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "summary": http_instrumentor.get_summary()
    }

@router.get("/http/endpoints")
async def get_http_endpoint_stats() -> Dict[str, Any]:
    """Return HTTP performance metrics grouped by endpoint."""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "endpoints": http_instrumentor.get_endpoint_stats()
    }

@router.get("/http/recent")
async def get_http_recent_requests(limit: int = 100) -> Dict[str, Any]:
    """Return recent HTTP request records."""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "requests": http_instrumentor.get_recent_requests(limit)
    }

@router.get("/agent/stats")
async def get_agent_stats() -> Dict[str, Any]:
    """获取Agent执行统计"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "agent_stats": _get_agent_dashboard()
    }

@router.get("/agent/{agent_name}/stats")
async def get_specific_agent_stats(agent_name: str) -> Dict[str, Any]:
    """获取特定Agent的统计"""
    instrumentor = get_agent_instrumentor(agent_name)
    summary = instrumentor.get_summary()
    
    if not summary:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found or not yet executed")
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "agent_name": agent_name,
        "stats": summary
    }

@router.get("/security/dashboard")
async def get_security_dashboard() -> Dict[str, Any]:
    """获取安全监控仪表盘"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "security_dashboard": security_instrumentor.get_dashboard()
    }

@router.get("/security/input-validation-stats")
async def get_input_validation_stats() -> Dict[str, Any]:
    """获取输入验证统计"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "stats": security_instrumentor.get_input_validation_stats()
    }

@router.get("/security/output-validation-stats")
async def get_output_validation_stats() -> Dict[str, Any]:
    """获取输出验证统计"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "stats": security_instrumentor.get_output_validation_stats()
    }

@router.get("/security/events")
async def get_security_events(limit: int = 50) -> Dict[str, Any]:
    """获取安全事件"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "events": security_instrumentor.get_security_events_stats()
    }

@router.get("/subagent/dashboard")
async def get_subagent_dashboard() -> Dict[str, Any]:
    """获取Sub-Agent监控仪表盘"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "subagent_dashboard": subagent_instrumentor.get_dashboard()
    }

@router.get("/subagent/stats")
async def get_subagent_stats() -> Dict[str, Any]:
    """获取Sub-Agent统计"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "agent_stats": subagent_instrumentor.get_agent_stats(),
        "parallel_stats": subagent_instrumentor.get_parallel_execution_stats()
    }

@router.get("/session/dashboard")
async def get_session_dashboard() -> Dict[str, Any]:
    """获取会话监控仪表盘"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "session_dashboard": session_instrumentor.get_dashboard()
    }

@router.get("/session/stats")
async def get_session_stats() -> Dict[str, Any]:
    """获取会话统计"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "stats": session_instrumentor.get_session_stats()
    }

@router.get("/external-services/dashboard")
async def get_external_services_dashboard() -> Dict[str, Any]:
    """获取外部服务监控仪表盘"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "dashboard": external_service_instrumentor.get_dashboard()
    }

@router.get("/external-services/health")
async def get_external_services_health() -> Dict[str, Any]:
    """获取外部服务健康状态"""
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "health": external_service_instrumentor.get_overall_health()
    }

@router.get("/external-services/{service_name}/stats")
async def get_service_stats(service_name: str) -> Dict[str, Any]:
    """获取特定服务统计"""
    stats = external_service_instrumentor.get_service_stats(service_name)
    
    if stats["total_calls"] == 0:
        raise HTTPException(status_code=404, detail=f"Service {service_name} not found or not yet called")
    
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "service_name": service_name,
        "stats": stats
    }

@router.post("/reset")
async def reset_observability() -> Dict[str, Any]:
    """重置所有可观测性数据（用于测试）"""
    observer.reset()
    http_instrumentor.reset()
    return {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "message": "All observability data has been reset"
    }

def _get_agent_dashboard() -> Dict[str, Any]:
    """获取Agent监控仪表盘"""
    agents = get_all_agent_dashboards()
    return {
        "total_agents": len(agents),
        "agent_names": list(agents.keys()),
        "agents": agents,
    }

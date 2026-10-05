# app/observability/external_service_observer.py
"""
外部服务监控模块
监控MCP、高德地图、Unsplash等外部服务的响应时间和可用性
"""
import time
import asyncio
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
from enum import Enum

from .observer_framework import (
    observer, EventType, MetricType
)

class ServiceStatus(Enum):
    """服务状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

@dataclass
class ExternalServiceCallRecord:
    """外部服务调用记录"""
    service_name: str
    operation: str
    start_time: float
    end_time: float = 0
    duration: float = 0
    success: bool = True
    status_code: int = 200
    error_message: str = ""
    request_size: int = 0
    response_size: int = 0
    
    def finish(self, success: bool = True, status_code: int = 200,
               error_message: str = "", response_size: int = 0):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        self.status_code = status_code
        self.error_message = error_message
        self.response_size = response_size
    
    def to_dict(self) -> Dict:
        return {
            "service_name": self.service_name,
            "operation": self.operation,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "success": self.success,
            "status_code": self.status_code,
            "error_message": self.error_message,
            "request_size": self.request_size,
            "response_size": self.response_size
        }

@dataclass
class ServiceHealthRecord:
    """服务健康状态记录"""
    service_name: str
    timestamp: float
    status: ServiceStatus
    avg_response_time: float
    success_rate: float
    requests_count: int
    errors_count: int
    
    def to_dict(self) -> Dict:
        return {
            "service_name": self.service_name,
            "timestamp": self.timestamp,
            "status": self.status.value,
            "avg_response_time": self.avg_response_time,
            "success_rate": self.success_rate,
            "requests_count": self.requests_count,
            "errors_count": self.errors_count
        }

class ExternalServiceInstrumentor:
    """外部服务仪器化追踪器"""
    
    def __init__(self):
        self.service_calls: List[ExternalServiceCallRecord] = []
        self.service_health: Dict[str, ServiceHealthRecord] = {}
        self._service_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_duration": 0,
            "min_duration": float('inf'),
            "max_duration": 0,
            "status_codes": defaultdict(int)
        })
    
    def start_call(self, service_name: str, operation: str,
                  request_size: int = 0) -> ExternalServiceCallRecord: #创建一个本地记录对象
        """开始服务调用"""
        record = ExternalServiceCallRecord(
            service_name=service_name,
            operation=operation,
            start_time=time.time(),
            request_size=request_size
        )
        
        observer.record_event(EventType.EXTERNAL_SERVICE_CALL, { #记录一个全局事件
            "service": service_name,
            "operation": operation,
            "action": "start"
        })
        
        return record
    
    def end_call(self, record: ExternalServiceCallRecord, success: bool = True,
                status_code: int = 200, error_message: str = "",
                response_size: int = 0):
        """结束服务调用"""
        record.finish(success, status_code, error_message, response_size) #写入对应信息，补齐剩余信息
        self.service_calls.append(record) #添加到本地记录列表
        
        # 更新该instrumentor自己维护的统计 统计服务调用次数、成功次数、失败次数、总时长、最小时长、最大时长、状态码次数
        stats = self._service_stats[record.service_name] #一个字典类型
        stats["total_calls"] += 1
        if success:
            stats["successful_calls"] += 1
        else:
            stats["failed_calls"] += 1
        
        stats["total_duration"] += record.duration
        stats["min_duration"] = min(stats["min_duration"], record.duration)
        stats["max_duration"] = max(stats["max_duration"], record.duration)
        stats["status_codes"][status_code] += 1
        
        # 记录全局指标 服务调用次数、成功次数、失败次数、总时长、最小时长、最大时长、状态码次数
        observer.record_counter("external_service_calls_total", 1,
                              {"service": record.service_name, "operation": record.operation,
                               "success": str(success)})
        observer.record_histogram("external_service_duration", record.duration,
                                {"service": record.service_name, "operation": record.operation})
        
        # 更新健康状态
        self._update_health_status(record.service_name)
        
        observer.record_event(EventType.EXTERNAL_SERVICE_CALL, {
            "service": record.service_name,
            "operation": record.operation,
            "action": "end",
            "duration": record.duration,
            "success": success
        })
    
    def _update_health_status(self, service_name: str):
        """更新服务健康状态"""
        stats = self._service_stats[service_name]
        
        if stats["total_calls"] == 0:
            status = ServiceStatus.UNKNOWN
        elif stats["failed_calls"] / stats["total_calls"] > 0.5:
            status = ServiceStatus.UNHEALTHY
        elif stats["failed_calls"] / stats["total_calls"] > 0.1:
            status = ServiceStatus.DEGRADED
        else:
            status = ServiceStatus.HEALTHY
        
        avg_duration = (stats["total_duration"] / stats["total_calls"] 
                       if stats["total_calls"] > 0 else 0)
        success_rate = (stats["successful_calls"] / stats["total_calls"] * 100
                       if stats["total_calls"] > 0 else 0)
        
        self.service_health[service_name] = ServiceHealthRecord(
            service_name=service_name,
            timestamp=time.time(),
            status=status,
            avg_response_time=avg_duration,
            success_rate=success_rate,
            requests_count=stats["total_calls"],
            errors_count=stats["failed_calls"]
        )
        
        # 记录服务状态指标
        observer.record_gauge(f"service_health_{service_name}", 
                            1 if status == ServiceStatus.HEALTHY else 0)
    
    def record_rate_limit_hit(self, service_name: str):
        """记录限流触发"""
        observer.record_counter("rate_limit_hits_total", 1, {"service": service_name})
        
        observer.record_event(EventType.EXTERNAL_SERVICE_CALL, {
            "service": service_name,
            "action": "rate_limit_hit"
        })
    
    async def track_call(self, service_name: str, operation: str,
                        call_func: Callable, *args, **kwargs) -> Any:
        """追踪服务调用的上下文管理器"""
        record = self.start_call(service_name, operation)
        
        try:
            if asyncio.iscoroutinefunction(call_func):
                result = await call_func(*args, **kwargs)
            else:
                result = call_func(*args, **kwargs)
            
            self.end_call(record, success=True, status_code=200)
            return result
            
        except Exception as e:
            error_message = str(e)
            status_code = getattr(e, 'status_code', 500) if hasattr(e, 'status_code') else 500
            
            self.end_call(record, success=False, status_code=status_code,
                         error_message=error_message)
            
            raise
    
    def get_service_stats(self, service_name: str) -> Dict[str, Any]:
        """获取服务统计"""
        stats = self._service_stats.get(service_name, {})
        
        if not stats or stats["total_calls"] == 0:
            return {
                "service_name": service_name,
                "total_calls": 0,
                "status": ServiceStatus.UNKNOWN.value
            }
        
        return {
            "service_name": service_name,
            "total_calls": stats["total_calls"],
            "successful_calls": stats["successful_calls"],
            "failed_calls": stats["failed_calls"],
            "success_rate": stats["successful_calls"] / stats["total_calls"] * 100,
            "avg_duration": stats["total_duration"] / stats["total_calls"],
            "min_duration": stats["min_duration"] if stats["min_duration"] != float('inf') else 0,
            "max_duration": stats["max_duration"],
            "status_codes": dict(stats["status_codes"]),
            "health_status": self.service_health.get(service_name, ServiceHealthRecord(
                service_name, time.time(), ServiceStatus.UNKNOWN, 0, 0, 0, 0
            )).status.value
        }
    
    def get_all_services_stats(self) -> Dict[str, Any]:
        """获取所有服务统计"""
        return {
            service_name: self.get_service_stats(service_name)
            for service_name in self._service_stats.keys()
        }
    
    def get_overall_health(self) -> Dict[str, Any]:
        """获取整体健康状态"""
        if not self.service_health:
            return {"status": ServiceStatus.UNKNOWN.value, "services": {}}
        
        services_status = {}
        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0
        
        for service_name, health in self.service_health.items():
            services_status[service_name] = health.to_dict()
            
            if health.status == ServiceStatus.HEALTHY:
                healthy_count += 1
            elif health.status == ServiceStatus.DEGRADED:
                degraded_count += 1
            elif health.status == ServiceStatus.UNHEALTHY:
                unhealthy_count += 1
        
        overall_status = ServiceStatus.HEALTHY.value
        if unhealthy_count > 0:
            overall_status = ServiceStatus.UNHEALTHY.value
        elif degraded_count > 0:
            overall_status = ServiceStatus.DEGRADED.value
        
        return {
            "overall_status": overall_status,
            "healthy_services": healthy_count,
            "degraded_services": degraded_count,
            "unhealthy_services": unhealthy_count,
            "services": services_status
        }
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取外部服务监控仪表盘"""
        return {
            "overall_health": self.get_overall_health(),
            "services_stats": self.get_all_services_stats(),
            "recent_calls": [c.to_dict() for c in self.service_calls[-20:]]
        }

# 全局外部服务仪器化追踪器
external_service_instrumentor = ExternalServiceInstrumentor()

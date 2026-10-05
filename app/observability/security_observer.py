# app/observability/security_observer.py
"""
Harness安全监控模块
监控输入验证、注入攻击检测、风险评估等安全事件
"""
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

from .observer_framework import (
    observer, EventType, MetricType
)

@dataclass
class InputValidationRecord:
    """输入验证记录"""
    session_id: str
    timestamp: float
    is_valid: bool
    error_code: str
    error_message: str
    risk_score: float
    blocked_keywords: List[str] = field(default_factory=list)
    injection_patterns: List[str] = field(default_factory=list)
    input_length: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "is_valid": self.is_valid,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "risk_score": self.risk_score,
            "blocked_keywords": self.blocked_keywords,
            "injection_patterns": self.injection_patterns,
            "input_length": self.input_length
        }

@dataclass
class OutputValidationRecord:
    """输出验证记录"""
    session_id: str
    timestamp: float
    is_valid: bool
    error_code: str
    error_message: str
    risk_level: str
    risk_score: float
    risk_reasons: List[str] = field(default_factory=list)
    sensitive_data_found: List[str] = field(default_factory=list)
    external_links: int = 0
    output_length: int = 0
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "is_valid": self.is_valid,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "risk_level": self.risk_level,
            "risk_score": self.risk_score,
            "risk_reasons": self.risk_reasons,
            "sensitive_data_found": self.sensitive_data_found,
            "external_links": self.external_links,
            "output_length": self.output_length
        }

@dataclass
class SecurityEventRecord:
    """安全事件记录"""
    event_type: str
    session_id: str
    timestamp: float
    severity: str  # low, medium, high, critical
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "event_type": self.event_type,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "severity": self.severity,
            "description": self.description,
            "details": self.details
        }

class SecurityInstrumentor:
    """安全仪器化追踪器"""
    
    def __init__(self):
        self.input_validations: List[InputValidationRecord] = []
        self.output_validations: List[OutputValidationRecord] = []
        self.security_events: List[SecurityEventRecord] = []
        self._session_blocked_count: Dict[str, int] = {}
    
    def record_input_validation(self, session_id: str, is_valid: bool, 
                                error_code: str = "", error_message: str = "",
                                risk_score: float = 0.0, blocked_keywords: List[str] = None,
                                injection_patterns: List[str] = None, input_length: int = 0):
        """记录输入验证结果"""
        record = InputValidationRecord(
            session_id=session_id,
            timestamp=time.time(),
            is_valid=is_valid,
            error_code=error_code,
            error_message=error_message,
            risk_score=risk_score,
            blocked_keywords=blocked_keywords or [],
            injection_patterns=injection_patterns or [],
            input_length=input_length
        )
        
        self.input_validations.append(record)
        
        # 记录指标
        if not is_valid:
            observer.record_counter("input_validation_failed_total", 1, 
                                   {"error_code": error_code})
            
            # 记录被屏蔽的关键词
            for keyword in (blocked_keywords or []):
                observer.record_counter("blocked_keyword_total", 1, {"keyword": keyword})
            
            # 记录注入模式
            for pattern in (injection_patterns or []):
                observer.record_counter("injection_pattern_total", 1, {"pattern": pattern})
            
            # 跟踪会话被阻止次数
            self._session_blocked_count[session_id] = self._session_blocked_count.get(session_id, 0) + 1
            if self._session_blocked_count[session_id] > 3:
                self.record_security_event(
                    event_type="session_blocked",
                    session_id=session_id,
                    severity="high",
                    description=f"会话 {session_id} 被阻止超过3次",
                    details={"blocked_count": self._session_blocked_count[session_id]}
                )
        else:
            observer.record_counter("input_validation_success_total", 1)
        
        observer.record_histogram("input_risk_score", risk_score)
        
        # 记录事件
        if blocked_keywords or injection_patterns:
            observer.record_event(EventType.INPUT_VALIDATION, record.to_dict())
    
    def record_output_validation(self, session_id: str, is_valid: bool,
                                 error_code: str = "", error_message: str = "",
                                 risk_level: str = "low", risk_score: float = 0.0,
                                 risk_reasons: List[str] = None,
                                 sensitive_data_found: List[str] = None,
                                 external_links: int = 0, output_length: int = 0):
        """记录输出验证结果"""
        record = OutputValidationRecord(
            session_id=session_id,
            timestamp=time.time(),
            is_valid=is_valid,
            error_code=error_code,
            error_message=error_message,
            risk_level=risk_level,
            risk_score=risk_score,
            risk_reasons=risk_reasons or [],
            sensitive_data_found=sensitive_data_found or [],
            external_links=external_links,
            output_length=output_length
        )
        
        self.output_validations.append(record)
        
        # 记录指标
        if not is_valid:
            observer.record_counter("output_validation_failed_total", 1,
                                   {"error_code": error_code})
        
        observer.record_counter("output_validation_total", 1,
                               {"risk_level": risk_level})
        observer.record_histogram("output_risk_score", risk_score)
        
        # 记录事件
        if risk_level in ["high", "critical"]:
            observer.record_event(EventType.RISK_ASSESSMENT, record.to_dict())
            
            self.record_security_event(
                event_type="high_risk_output",
                session_id=session_id,
                severity=risk_level,
                description=f"检测到高风险输出: {', '.join(risk_reasons or [])}",
                details=record.to_dict()
            )
    
    def record_injection_detected(self, session_id: str, injection_type: str,
                                 pattern: str, user_input: str):
        """记录注入攻击检测"""
        self.record_security_event(
            event_type="injection_detected",
            session_id=session_id,
            severity="critical",
            description=f"检测到{injection_type}注入攻击",
            details={
                "pattern": pattern,
                "input_preview": user_input[:200]
            }
        )
        
        observer.record_counter("injection_detected_total", 1,
                               {"type": injection_type})
        
        observer.record_event(EventType.INJECTION_DETECTED, {
            "session_id": session_id,
            "type": injection_type,
            "pattern": pattern
        })
    
    def record_security_event(self, event_type: str, session_id: str,
                             severity: str, description: str,
                             details: Dict[str, Any] = None):
        """记录安全事件"""
        record = SecurityEventRecord(
            event_type=event_type,
            session_id=session_id,
            timestamp=time.time(),
            severity=severity,
            description=description,
            details=details or {}
        )
        
        self.security_events.append(record)
        
        # 记录指标
        observer.record_counter("security_events_total", 1,
                               {"event_type": event_type, "severity": severity})
        
        observer.record_event(EventType.HARNESS_CHECK, record.to_dict())
    
    def get_input_validation_stats(self) -> Dict[str, Any]:
        """获取输入验证统计"""
        total = len(self.input_validations)
        failed = sum(1 for v in self.input_validations if not v.is_valid)
        
        keyword_counts = {}
        injection_counts = {}
        
        for v in self.input_validations:
            for kw in v.blocked_keywords:
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
            for pattern in v.injection_patterns:
                injection_counts[pattern] = injection_counts.get(pattern, 0) + 1
        
        return {
            "total_validations": total,
            "failed_validations": failed,
            "success_rate": ((total - failed) / total * 100) if total > 0 else 100,
            "blocked_keywords_top": sorted(keyword_counts.items(), key=lambda x: -x[1])[:10],
            "injection_patterns_top": sorted(injection_counts.items(), key=lambda x: -x[1])[:10],
            "avg_risk_score": sum(v.risk_score for v in self.input_validations) / total if total > 0 else 0
        }
    
    def get_output_validation_stats(self) -> Dict[str, Any]:
        """获取输出验证统计"""
        total = len(self.output_validations)
        failed = sum(1 for v in self.output_validations if not v.is_valid)
        
        risk_level_counts = {}
        for v in self.output_validations:
            risk_level_counts[v.risk_level] = risk_level_counts.get(v.risk_level, 0) + 1
        
        return {
            "total_validations": total,
            "failed_validations": failed,
            "success_rate": ((total - failed) / total * 100) if total > 0 else 100,
            "risk_level_distribution": risk_level_counts,
            "avg_risk_score": sum(v.risk_score for v in self.output_validations) / total if total > 0 else 0
        }
    
    def get_security_events_stats(self) -> Dict[str, Any]:
        """获取安全事件统计"""
        severity_counts = {}
        event_type_counts = {}
        
        for e in self.security_events:
            severity_counts[e.severity] = severity_counts.get(e.severity, 0) + 1
            event_type_counts[e.event_type] = event_type_counts.get(e.event_type, 0) + 1
        
        return {
            "total_events": len(self.security_events),
            "severity_distribution": severity_counts,
            "event_type_distribution": event_type_counts,
            "recent_events": [e.to_dict() for e in self.security_events[-10:]]
        }
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取安全监控仪表盘"""
        return {
            "input_validation": self.get_input_validation_stats(),
            "output_validation": self.get_output_validation_stats(),
            "security_events": self.get_security_events_stats(),
            "blocked_sessions": len([s for s, c in self._session_blocked_count.items() if c > 3])
        }

# 全局安全仪器化追踪器
security_instrumentor = SecurityInstrumentor()

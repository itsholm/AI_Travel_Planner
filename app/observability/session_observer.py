# app/observability/session_observer.py
"""
会话状态监控模块
监控活跃会话、上下文压缩、消息历史等
"""
import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from .observer_framework import (
    observer, EventType, MetricType
)

@dataclass
class SessionStateRecord:
    """会话状态记录"""
    session_id: str
    timestamp: float
    state: str  # active, idle, archived
    message_count: int
    context_size: int  # Token数量
    history_compression_ratio: float  # 压缩比
    active_duration: float  # 活跃持续时间
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "state": self.state,
            "message_count": self.message_count,
            "context_size": self.context_size,
            "history_compression_ratio": self.history_compression_ratio,
            "active_duration": self.active_duration
        }

@dataclass
class ContextCompressionRecord:
    """上下文压缩记录"""
    session_id: str
    timestamp: float
    original_size: int  # 原始Token数
    compressed_size: int  # 压缩后Token数
    compression_ratio: float  # 压缩比
    summary_preview: str  # 摘要预览
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "original_size": self.original_size,
            "compressed_size": self.compressed_size,
            "compression_ratio": self.compression_ratio,
            "summary_preview": self.summary_preview[:100]
        }

@dataclass
class SessionEventRecord:
    """会话事件记录"""
    session_id: str
    timestamp: float
    event_type: str  # created, resumed, modified, archived, deleted
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "details": self.details
        }

class SessionInstrumentor:
    """会话仪器化追踪器"""
    
    def __init__(self):
        self.session_states: Dict[str, SessionStateRecord] = {}
        self.context_compressions: List[ContextCompressionRecord] = []
        self.session_events: List[SessionEventRecord] = []
        self._active_sessions: Dict[str, float] = {}  # session_id -> last_active_time
        self._session_start_times: Dict[str, float] = {}  # session_id -> start_time
    
    def record_session_created(self, session_id: str):
        """记录会话创建"""
        self._active_sessions[session_id] = time.time()
        self._session_start_times[session_id] = time.time()
        
        self.session_events.append(SessionEventRecord(
            session_id=session_id,
            timestamp=time.time(),
            event_type="created",
            details={}
        ))
        
        observer.record_counter("sessions_created_total", 1)
        observer.record_gauge("active_sessions", len(self._active_sessions))
        
        observer.record_event(EventType.SESSION_START, {
            "session_id": session_id,
            "timestamp": time.time()
        })
    
    def record_session_activity(self, session_id: str):
        """记录会话活跃"""
        self._active_sessions[session_id] = time.time()
    
    def record_session_modified(self, session_id: str, message_count: int,
                              context_size: int):
        """记录会话修改"""
        if session_id in self._active_sessions:
            self._active_sessions[session_id] = time.time()
        
        self.session_events.append(SessionEventRecord(
            session_id=session_id,
            timestamp=time.time(),
            event_type="modified",
            details={
                "message_count": message_count,
                "context_size": context_size
            }
        ))
    
    def record_context_compression(self, session_id: str, original_size: int,
                                 compressed_size: int, summary_preview: str = ""):
        """记录上下文压缩"""
        compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
        
        record = ContextCompressionRecord(
            session_id=session_id,
            timestamp=time.time(),
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=compression_ratio,
            summary_preview=summary_preview
        )
        
        self.context_compressions.append(record)
        
        observer.record_counter("context_compressions_total", 1)
        observer.record_histogram("compression_ratio", compression_ratio)
        observer.record_histogram("context_size_reduction", original_size - compressed_size)
    
    def record_session_archived(self, session_id: str):
        """记录会话归档"""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
        
        active_duration = 0
        if session_id in self._session_start_times:
            active_duration = time.time() - self._session_start_times[session_id]
        
        self.session_events.append(SessionEventRecord(
            session_id=session_id,
            timestamp=time.time(),
            event_type="archived",
            details={"active_duration": active_duration}
        ))
        
        observer.record_gauge("active_sessions", len(self._active_sessions))
    
    def record_session_deleted(self, session_id: str):
        """记录会话删除"""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
        if session_id in self._session_start_times:
            del self._session_start_times[session_id]
        
        self.session_events.append(SessionEventRecord(
            session_id=session_id,
            timestamp=time.time(),
            event_type="deleted",
            details={}
        ))
        
        observer.record_counter("sessions_deleted_total", 1)
        observer.record_gauge("active_sessions", len(self._active_sessions))
    
    def update_session_state(self, session_id: str, state: str,
                           message_count: int, context_size: int):
        """更新会话状态"""
        active_duration = 0
        if session_id in self._session_start_times:
            active_duration = time.time() - self._session_start_times[session_id]
        
        record = SessionStateRecord(
            session_id=session_id,
            timestamp=time.time(),
            state=state,
            message_count=message_count,
            context_size=context_size,
            history_compression_ratio=0,  # 需要从会话获取
            active_duration=active_duration
        )
        
        self.session_states[session_id] = record
        
        # 定期检查并清理不活跃的会话
        self._cleanup_inactive_sessions()
    
    def _cleanup_inactive_sessions(self, idle_threshold: float = 3600):
        """清理不活跃的会话"""
        current_time = time.time()
        inactive_sessions = [
            sid for sid, last_active in self._active_sessions.items()
            if current_time - last_active > idle_threshold
        ]
        
        for session_id in inactive_sessions:
            self.record_session_archived(session_id)
    
    def get_active_sessions_count(self) -> int:
        """获取活跃会话数"""
        self._cleanup_inactive_sessions()
        return len(self._active_sessions)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        self._cleanup_inactive_sessions()
        
        total_sessions = len(self.session_events)
        created = sum(1 for e in self.session_events if e.event_type == "created")
        deleted = sum(1 for e in self.session_events if e.event_type == "deleted")
        
        compression_stats = {}
        if self.context_compressions:
            ratios = [c.compression_ratio for c in self.context_compressions]
            compression_stats = {
                "total_compressions": len(self.context_compressions),
                "avg_compression_ratio": sum(ratios) / len(ratios),
                "min_compression_ratio": min(ratios),
                "max_compression_ratio": max(ratios)
            }
        
        return {
            "total_sessions": total_sessions,
            "active_sessions": len(self._active_sessions),
            "sessions_created": created,
            "sessions_deleted": deleted,
            "session_events_count": len(self.session_events),
            "compression_stats": compression_stats
        }
    
    def get_context_compression_stats(self) -> Dict[str, Any]:
        """获取上下文压缩统计"""
        if not self.context_compressions:
            return {"total_compressions": 0}
        
        ratios = [c.compression_ratio for c in self.context_compressions]
        original_sizes = [c.original_size for c in self.context_compressions]
        compressed_sizes = [c.compressed_size for c in self.context_compressions]
        
        return {
            "total_compressions": len(self.context_compressions),
            "avg_compression_ratio": sum(ratios) / len(ratios),
            "avg_original_size": sum(original_sizes) / len(original_sizes),
            "avg_compressed_size": sum(compressed_sizes) / len(compressed_sizes),
            "avg_size_reduction": sum(o - c for o, c in zip(original_sizes, compressed_sizes)) / len(original_sizes)
        }
    
    def get_dashboard(self) -> Dict[str, Any]:
        """获取会话监控仪表盘"""
        return {
            "session_stats": self.get_session_stats(),
            "compression_stats": self.get_context_compression_stats(),
            "active_sessions": list(self._active_sessions.keys()),
            "recent_events": [e.to_dict() for e in self.session_events[-20:]]
        }

# 全局会话仪器化追踪器
session_instrumentor = SessionInstrumentor()

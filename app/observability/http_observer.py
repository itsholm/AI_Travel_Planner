import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List

from fastapi import FastAPI, Request

from .observer_framework import EventType, observer

logger = logging.getLogger(__name__)


@dataclass
class HttpRequestRecord:
    request_id: str
    method: str
    endpoint: str
    status_code: int
    duration: float
    response_size: int
    timestamp: str
    client_ip: str = "unknown"
    user_agent: str = ""
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "method": self.method,
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "duration": self.duration,
            "response_size": self.response_size,
            "timestamp": self.timestamp,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "error": self.error,
        }


@dataclass
class EndpointStats:
    count: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration: float = 0
    min_duration: float = float("inf")
    max_duration: float = 0
    total_response_size: int = 0
    status_codes: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def record(self, status_code: int, duration: float, response_size: int) -> None:
        self.count += 1
        if status_code < 400:
            self.successful_requests += 1
        else:
            self.failed_requests += 1

        self.total_duration += duration
        self.min_duration = min(self.min_duration, duration)
        self.max_duration = max(self.max_duration, duration)
        self.total_response_size += response_size
        self.status_codes[str(status_code)] += 1

    def to_dict(self) -> Dict[str, Any]:
        avg_duration = self.total_duration / self.count if self.count else 0
        avg_response_size = self.total_response_size / self.count if self.count else 0
        return {
            "count": self.count,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": (self.successful_requests / self.count * 100) if self.count else 100,
            "avg_duration": avg_duration,
            "min_duration": 0 if self.min_duration == float("inf") else self.min_duration,
            "max_duration": self.max_duration,
            "avg_response_size": avg_response_size,
            "status_codes": dict(self.status_codes),
        }


class HttpPerformanceInstrumentor:
    def __init__(self, max_recent_requests: int = 200):
        self.recent_requests: Deque[HttpRequestRecord] = deque(maxlen=max_recent_requests)
        self.endpoint_stats: Dict[str, EndpointStats] = defaultdict(EndpointStats)

    def record_request(
        self,
        *,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        response_size: int = 0,
        client_ip: str = "unknown",
        user_agent: str = "",
        error: str = "",
        request_id: str = "",
    ) -> HttpRequestRecord:
        request_id = request_id or f"{endpoint}_{int(time.time() * 1000)}"
        record = HttpRequestRecord(
            request_id=request_id,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            duration=duration,
            response_size=response_size,
            timestamp=datetime.now().isoformat(),
            client_ip=client_ip,
            user_agent=user_agent,
            error=error,
        )

        self.recent_requests.append(record)
        self.endpoint_stats[endpoint].record(status_code, duration, response_size)

        tags = {
            "method": method,
            "endpoint": endpoint,
            "status_code": str(status_code),
        }
        observer.record_counter("http_requests_total", 1, tags)
        observer.record_histogram("http_request_duration", duration, tags)
        if response_size:
            observer.record_histogram("http_response_size", response_size, tags)
        if status_code >= 400:
            observer.record_counter("http_errors_total", 1, tags)

        observer.record_event(EventType.HTTP_REQUEST, record.to_dict())
        return record

    def get_recent_requests(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [record.to_dict() for record in list(self.recent_requests)[-limit:]]

    def get_endpoint_stats(self) -> Dict[str, Dict[str, Any]]:
        return {
            endpoint: stats.to_dict()
            for endpoint, stats in self.endpoint_stats.items()
        }

    def get_summary(self) -> Dict[str, Any]:
        requests = list(self.recent_requests)
        total_requests = sum(stats.count for stats in self.endpoint_stats.values())
        successful_requests = sum(stats.successful_requests for stats in self.endpoint_stats.values())
        failed_requests = total_requests - successful_requests
        total_duration = sum(stats.total_duration for stats in self.endpoint_stats.values())

        all_durations = [request.duration for request in requests]
        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "success_rate": (successful_requests / total_requests * 100) if total_requests else 100,
            "overall_avg_duration": total_duration / total_requests if total_requests else 0,
            "overall_min_duration": min(all_durations) if all_durations else 0,
            "overall_max_duration": max(all_durations) if all_durations else 0,
            "endpoint_statistics": self.get_endpoint_stats(),
        }

    def get_dashboard(self) -> Dict[str, Any]:
        return {
            "summary": self.get_summary(),
            "recent_requests": self.get_recent_requests(limit=20),
        }

    def export_metrics(self, filename: str = "") -> str:
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"api_performance_metrics_{timestamp}.json"

        data = {
            "export_timestamp": datetime.now().isoformat(),
            "summary": self.get_summary(),
            "recent_requests": self.get_recent_requests(limit=len(self.recent_requests)),
            "endpoint_statistics": self.get_endpoint_stats(),
        }

        with open(filename, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

        return filename

    def reset(self) -> None:
        self.recent_requests.clear()
        self.endpoint_stats.clear()


http_instrumentor = HttpPerformanceInstrumentor()


def setup_http_observability(app: FastAPI) -> None:
    """Register lightweight HTTP request metrics on the FastAPI app."""

    @app.middleware("http")
    async def observe_http_requests(request: Request, call_next):
        start_time = time.time()
        request_info = {
            "method": request.method,
            "endpoint": request.url.path,
            "user_agent": request.headers.get("user-agent", ""),
            "client_ip": request.client.host if request.client else "unknown",
        }

        try:
            response = await call_next(request)
            duration = time.time() - start_time
            response_size = _get_response_size(response)

            http_instrumentor.record_request(
                method=request_info["method"],
                endpoint=request_info["endpoint"],
                status_code=response.status_code,
                duration=duration,
                response_size=response_size,
                client_ip=request_info["client_ip"],
                user_agent=request_info["user_agent"],
            )

            logger.info(
                "API %s %s - Duration: %.3fs - Status: %s",
                request_info["method"],
                request_info["endpoint"],
                duration,
                response.status_code,
            )

            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            return response

        except Exception as exc:
            duration = time.time() - start_time
            status_code = getattr(exc, "status_code", 500)
            http_instrumentor.record_request(
                method=request_info["method"],
                endpoint=request_info["endpoint"],
                status_code=status_code,
                duration=duration,
                client_ip=request_info["client_ip"],
                user_agent=request_info["user_agent"],
                error=str(exc),
            )

            logger.error(
                "API Error in %s: %s - Duration: %.3fs",
                request_info["endpoint"],
                exc,
                duration,
            )
            raise


def _get_response_size(response) -> int:
    if hasattr(response, "body"):
        return len(response.body)
    if hasattr(response, "content"):
        return len(response.content)
    return 0

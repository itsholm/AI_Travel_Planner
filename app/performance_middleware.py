"""
性能监控中间件 - 自动监控API性能
"""
import time
import json
import logging
from typing import Dict, Any, List
from datetime import datetime
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from metrics import metrics_collector

logger = logging.getLogger(__name__)

class PerformanceMiddleware(BaseHTTPMiddleware):
    """性能监控中间件"""

    def __init__(self, app):
        super().__init__(app)
        self.api_metrics = {}

    async def dispatch(self, request: Request, call_next):
        # 开始计时
        start_time = time.time()

        # 记录请求信息
        request_info = {
            "method": request.method,
            "url": str(request.url),
            "endpoint": request.url.path,
            "timestamp": datetime.now().isoformat(),
            "user_agent": request.headers.get("user-agent", ""),
            "client_ip": request.client.host if request.client else "unknown"
        }

        try:
            # 执行请求
            response = await call_next(request)

            # 计算耗时
            duration = time.time() - start_time

            # 记录性能指标
            # 处理不同的响应类型
            if hasattr(response, 'body'):
                response_size = len(response.body)
            elif hasattr(response, 'content'):
                response_size = len(response.content)
            else:
                response_size = 0

            metrics_data = {
                "request_id": f"{request_info['endpoint']}_{int(start_time)}",
                "request_info": request_info,
                "duration": duration,
                "status_code": response.status_code,
                "response_size": response_size,
                "timestamp": datetime.now().isoformat()
            }

            # 从response中获取额外性能数据（如果存在）
            if hasattr(response, 'headers'):
                performance_header = response.headers.get("X-Performance-Metrics")
                if performance_header:
                    try:
                        extra_metrics = json.loads(performance_header)
                        metrics_data.update(extra_metrics)
                    except json.JSONDecodeError:
                        pass

            # 存储指标
            self.api_metrics[metrics_data["request_id"]] = metrics_data

            # 记录日志
            logger.info(
                f"API {request_info['method']} {request_info['endpoint']} - "
                f"Duration: {duration:.3f}s - Status: {response.status_code}"
            )

            # 添加性能头部（用于调试）
            response.headers["X-Response-Time"] = f"{duration:.3f}s"

            # 如果是API端点，添加详细性能数据
            if request_info['endpoint'].startswith('/api/'):
                performance_json = json.dumps(metrics_data, ensure_ascii=False)
                response.headers["X-Performance-Metrics"] = performance_json

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"API Error in {request.url.path}: {str(e)} - Duration: {duration:.3f}s")

            # 创建错误响应
            from fastapi import HTTPException
            if not isinstance(e, HTTPException):
                raise e

            # 也要记录失败的请求
            error_metrics = {
                "request_id": f"{request_info['endpoint']}_{int(start_time)}",
                "request_info": request_info,
                "duration": duration,
                "status_code": e.status_code if hasattr(e, 'status_code') else 500,
                "error": str(e.detail) if hasattr(e, 'detail') else str(e),
                "timestamp": datetime.now().isoformat()
            }
            self.api_metrics[error_metrics["request_id"]] = error_metrics

            raise e

    def get_api_metrics(self, endpoint: str = None) -> List[Dict[str, Any]]:
        """获取API性能指标"""
        if endpoint:
            return [m for m in self.api_metrics.values() if m["request_info"]["endpoint"] == endpoint]
        return list(self.api_metrics.values())

    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能汇总"""
        if not self.api_metrics:
            return {}

        metrics_list = list(self.api_metrics.values())
        total_requests = len(metrics_list)
        successful_requests = len([m for m in metrics_list if m["status_code"] < 400])
        failed_requests = total_requests - successful_requests

        # 按端点分组统计
        endpoint_stats = {}
        for metric in metrics_list:
            endpoint = metric["request_info"]["endpoint"]
            if endpoint not in endpoint_stats:
                endpoint_stats[endpoint] = {
                    "count": 0,
                    "total_duration": 0,
                    "avg_duration": 0,
                    "min_duration": float('inf'),
                    "max_duration": 0
                }

            stats = endpoint_stats[endpoint]
            stats["count"] += 1
            stats["total_duration"] += metric["duration"]
            stats["min_duration"] = min(stats["min_duration"], metric["duration"])
            stats["max_duration"] = max(stats["max_duration"], metric["duration"])

        # 计算平均值
        for endpoint, stats in endpoint_stats.items():
            stats["avg_duration"] = stats["total_duration"] / stats["count"]

        # 整体统计
        all_durations = [m["duration"] for m in metrics_list]
        avg_duration = sum(all_durations) / total_requests

        return {
            "total_requests": total_requests,
            "successful_requests": successful_requests,
            "failed_requests": failed_requests,
            "success_rate": (successful_requests / total_requests) * 100,
            "overall_avg_duration": avg_duration,
            "overall_min_duration": min(all_durations),
            "overall_max_duration": max(all_durations),
            "endpoint_statistics": endpoint_stats
        }

    def export_metrics(self, filename: str = None) -> str:
        """导出性能指标到文件"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"api_performance_metrics_{timestamp}.json"

        data = {
            "export_timestamp": datetime.now().isoformat(),
            "summary": self.get_performance_summary(),
            "detailed_metrics": self.api_metrics
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"性能指标已导出到: {filename}")
        return filename
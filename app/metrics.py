"""
性能监控和指标收集模块
"""
import time
import json
import logging
from datetime import datetime
from typing import Dict, List, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

@dataclass
class RequestMetrics:
    """单次请求的指标数据"""
    request_id: str
    timestamp: str
    api_endpoint: str
    total_duration: float  # 总响应时间（秒）
    llm_calls: List[Dict[str, Any]]  # LLM调用详情
    external_calls: List[Dict[str, Any]]  # 外部服务调用详情
    token_usage: Dict[str, int]  # Token消耗统计
    response_size: int  # 响应数据大小（字节）

    def total_tokens(self) -> int:
        """计算总Token消耗"""
        return sum(self.token_usage.values())

class MetricsCollector:
    """指标收集器"""

    def __init__(self):
        self.metrics: List[RequestMetrics] = []
        self.request_count = 0

    def start_timer(self) -> float:
        """开始计时"""
        return time.time()

    def record_llm_call(self, model: str, input_tokens: int, output_tokens: int, duration: float):
        """记录LLM调用"""
        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration": duration,
            "timestamp": datetime.now().isoformat()
        }

    def record_external_call(self, service: str, operation: str, duration: float, status: str = "success"):
        """记录外部服务调用"""
        return {
            "service": service,
            "operation": operation,
            "duration": duration,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }

    def calculate_token_cost(self, input_tokens: int, output_tokens: int,
                           input_price: float = 0.001, output_price: float = 0.002) -> float:
        """计算Token成本（示例价格：输入$0.001/1K tokens，输出$0.002/1K tokens）"""
        return (input_tokens * input_price / 1000) + (output_tokens * output_price / 1000)

    def get_summary_stats(self) -> Dict[str, Any]:
        """获取汇总统计"""
        if not self.metrics:
            return {}

        total_requests = len(self.metrics)
        avg_response_time = sum(m.total_duration for m in self.metrics) / total_requests
        total_tokens = sum(m.total_tokens() for m in self.metrics)
        avg_tokens_per_request = total_tokens / total_requests

        # Token成本统计
        total_cost = sum(
            self.calculate_token_cost(
                sum(llm["input_tokens"] for llm in m.llm_calls),
                sum(llm["output_tokens"] for llm in m.llm_calls)
            ) for m in self.metrics
        )

        return {
            "total_requests": total_requests,
            "avg_response_time_sec": round(avg_response_time, 3),
            "total_tokens": total_tokens,
            "avg_tokens_per_request": round(avg_tokens_per_request, 2),
            "estimated_cost_usd": round(total_cost, 4),
            "external_api_calls": sum(len(m.external_calls) for m in self.metrics)
        }

# 全局指标收集器
metrics_collector = MetricsCollector()

def monitor_api_performance(endpoint: str):
    """API性能监控装饰器"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = metrics_collector.start_timer()
            request_id = f"req_{metrics_collector.request_count + 1}"
            metrics_collector.request_count += 1

            try:
                # 执行API调用
                result = await func(*args, **kwargs)

                # 计算总耗时
                duration = time.time() - start_time

                # 记录指标（需要在API内部添加更多细节）
                metrics = RequestMetrics(
                    request_id=request_id,
                    timestamp=datetime.now().isoformat(),
                    api_endpoint=endpoint,
                    total_duration=duration,
                    llm_calls=[],  # 需要在LLM客户端填充
                    external_calls=[],  # 需要在外部服务调用时填充
                    token_usage={},  # 需要在LLM调用后填充
                    response_size=len(str(result).encode()) if result else 0
                )

                metrics_collector.metrics.append(metrics)

                logger.info(f"API {endpoint} completed in {duration:.3f}s")
                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"API {endpoint} failed after {duration:.3f}s: {str(e)}")
                raise e

        return wrapper
    return decorator
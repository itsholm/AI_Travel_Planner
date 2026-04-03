"""
性能基准测试工具 - 对比串行vs并行版本的性能
"""
import asyncio
import time
from typing import Dict, List, Any
from trip_planner import TripMaster
from parallel_planner import ParallelTripPlanner
from llm_client import HelloAgentLLM
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
import json

class PerformanceBenchmark:
    """性能基准测试类"""

    def __init__(self):
        self.results = []

    async def setup_environment(self):
        """测试环境初始化"""
        from dotenv import load_dotenv
        load_dotenv()

        # 模拟MCP会话（用于测试，不连接真实API）
        stack = AsyncExitStack()
        mock_session = None  # 在实际测试中需要真实连接

        # 初始化LLM
        llm = HelloAgentLLM()
        master = TripMaster(llm, mock_session)
        await master.initialize_team()

        parallel_planner = ParallelTripPlanner(master)

        return master, parallel_planner

    def create_test_request(self) -> Dict[str, Any]:
        """创建测试请求数据"""
        return {
            "city": "北京",
            "start_date": "2024-01-15",
            "end_date": "2024-01-17",
            "travel_days": 3,
            "transportation": "地铁",
            "accommodation": "经济型",
            "preferences": ["历史文化", "美食"],
            "free_text_input": "希望安排一些当地特色餐厅"
        }

    async def run_serial_benchmark(self, master: TripMaster, request_data: Dict) -> Dict[str, Any]:
        """运行串行版本基准测试"""
        print("\n🔄 运行串行版本基准测试...")

        request_obj = TripRequest(**request_data)
        start_time = time.time()

        try:
            # 这里需要修改trip_planner以支持独立测试
            # 由于实际代码依赖MCP连接，这里模拟测试流程
            plan = await master.create_plan(request_obj)
            duration = time.time() - start_time

            return {
                "method": "serial",
                "duration": duration,
                "success": True,
                "estimated_calls": 4  # 4个串行LLM调用
            }
        except Exception as e:
            return {
                "method": "serial",
                "duration": time.time() - start_time,
                "success": False,
                "error": str(e)
            }

    async def run_parallel_benchmark(self, parallel_planner: ParallelTripPlanner, request_data: Dict) -> Dict[str, Any]:
        """运行并行版本基准测试"""
        print("\n⚡ 运行并行版本基准测试...")

        request_obj = TripRequest(**request_data)
        start_time = time.time()

        try:
            plan = await parallel_planner.create_plan_optimized(request_obj)
            duration = time.time() - start_time

            return {
                "method": "parallel",
                "duration": duration,
                "success": True,
                "estimated_calls": 4  # 4个并行LLM调用
            }
        except Exception as e:
            return {
                "method": "parallel",
                "duration": time.time() - start_time,
                "success": False,
                "error": str(e)
            }

    def calculate_improvement(self, serial_result: Dict, parallel_result: Dict) -> Dict[str, Any]:
        """计算性能提升"""
        if not serial_result["success"] or not parallel_result["success"]:
            return {"improvement": "N/A", "error": "One or both tests failed"}

        serial_time = serial_result["duration"]
        parallel_time = parallel_result["duration"]
        improvement = ((serial_time - parallel_time) / serial_time) * 100

        return {
            "serial_time": serial_time,
            "parallel_time": parallel_time,
            "improvement_percent": round(improvement, 2),
            "speedup_factor": round(serial_time / parallel_time, 2),
            "absolute_reduction": round(serial_time - parallel_time, 3)
        }

    async def run_full_benchmark(self, num_tests: int = 3) -> Dict[str, Any]:
        """运行完整基准测试"""
        print(f"🧪 开始运行基准测试（{num_tests}轮）...")

        master, parallel_planner = await self.setup_environment()
        test_request = self.create_test_request()

        serial_results = []
        parallel_results = []

        for i in range(num_tests):
            print(f"\n--- 第 {i+1} 轮测试 ---")

            # 串行测试
            serial_result = await self.run_serial_benchmark(master, test_request)
            serial_results.append(serial_result)

            # 并行测试
            parallel_result = await self.run_parallel_benchmark(parallel_planner, test_request)
            parallel_results.append(parallel_result)

            # 计算本轮改进
            improvement = self.calculate_improvement(serial_result, parallel_result)
            print(f"本轮改进: {improvement['improvement_percent']}%")

        # 汇总结果
        avg_serial = sum(r["duration"] for r in serial_results if r["success"]) / len(serial_results)
        avg_parallel = sum(r["duration"] for r in parallel_results if r["success"]) / len(parallel_results)

        summary = {
            "total_tests": num_tests,
            "avg_serial_time": round(avg_serial, 3),
            "avg_parallel_time": round(avg_parallel, 3),
            "avg_improvement": round(((avg_serial - avg_parallel) / avg_serial) * 100, 2),
            "individual_results": {
                "serial": serial_results,
                "parallel": parallel_results
            }
        }

        # 保存结果
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        with open(f"benchmark_results_{timestamp}.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"\n📊 基准测试完成！结果已保存到 benchmark_results_{timestamp}.json")
        return summary

# 使用示例
async def main():
    benchmark = PerformanceBenchmark()
    results = await benchmark.run_full_benchmark(num_tests=3)

    print("\n🎯 性能提升总结:")
    print(f"平均串行响应时间: {results['avg_serial_time']}秒")
    print(f"平均并行响应时间: {results['avg_parallel_time']}秒")
    print(f"平均性能提升: {results['avg_improvement']}%")

if __name__ == "__main__":
    asyncio.run(main())
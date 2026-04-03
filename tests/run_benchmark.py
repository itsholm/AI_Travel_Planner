#!/usr/bin/env python3
"""
运行性能基准测试脚本
"""
import asyncio
import requests
import time
import json
from datetime import datetime

async def test_serial_vs_parallel():
    """对比串行和并行版本的性能"""

    # 测试数据
    test_request = {
        "city": "北京",
        "start_date": "2026-04-2",
        "end_date": "2026-04-5",
        "travel_days": 3,
        "transportation": "公共交通",
        "accommodation": "经济型",
        "preferences": ["历史文化", "美食"],
        "free_text_input": "希望安排一些当地特色餐厅"
    }

    base_url = "http://localhost:5173"

    print("🚀 开始性能基准测试...")
    print("=" * 50)

    # 测试多次取平均值
    test_count = 3
    results = []

    for i in range(1, test_count + 1):
        print(f"\n--- 第 {i} 次测试 ---")

        # 发送请求
        start_time = time.time()
        try:
            response = requests.post(
                f"{base_url}/api/plan",
                json=test_request,
                headers={"Content-Type": "application/json"}
            )
            duration = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                metrics = data.get("performance_metrics", {})

                result = {
                    "test_number": i,
                    "duration": duration,
                    "status": "success",
                    "metrics": metrics
                }

                print(f"✅ 请求成功")
                print(f"   响应时间: {duration:.3f}秒")
                print(f"   Token使用: {metrics.get('tokens_used', 'N/A')}")
                print(f"   是否优化: {metrics.get('is_optimized', False)}")

            else:
                result = {
                    "test_number": i,
                    "duration": duration,
                    "status": "error",
                    "error": response.text
                }
                print(f"❌ 请求失败: {response.status_code}")

        except Exception as e:
            duration = time.time() - start_time
            result = {
                "test_number": i,
                "duration": duration,
                "status": "error",
                "error": str(e)
            }
            print(f"❌ 请求异常: {str(e)}")

        results.append(result)

    # 计算平均值
    successful_results = [r for r in results if r["status"] == "success"]

    if successful_results:
        avg_duration = sum(r["duration"] for r in successful_results) / len(successful_results)
        avg_tokens = sum(r["metrics"].get("tokens_used", 0) for r in successful_results) / len(successful_results)

        print("\n" + "=" * 50)
        print("📊 测试结果汇总:")
        print(f"总测试次数: {test_count}")
        print(f"成功次数: {len(successful_results)}")
        print(f"失败次数: {test_count - len(successful_results)}")
        print(f"平均响应时间: {avg_duration:.3f}秒")
        print(f"平均Token消耗: {avg_tokens:.0f}")

        # 保存结果
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_results_{timestamp}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "test_count": test_count,
                "results": results,
                "summary": {
                    "avg_duration": avg_duration,
                    "avg_tokens": avg_tokens,
                    "success_rate": len(successful_results) / test_count * 100
                }
            }, f, indent=2, ensure_ascii=False)

        print(f"\n📁 详细结果已保存到: {filename}")
    else:
        print("\n❌ 所有测试都失败了，请检查服务是否正常运行")

if __name__ == "__main__":
    asyncio.run(test_serial_vs_parallel())
"""
并行旅行规划器 - 大幅降低响应延迟
"""
import asyncio
import time
from typing import Dict, Any
from trip_planner import TripMaster
from models.schemas import TripRequest, TripPlan

class ParallelTripPlanner:
    """并行旅行规划器"""

    def __init__(self, master: TripMaster):
        self.master = master

    async def create_plan_optimized(self, request: TripRequest) -> Dict[str, Any]:
        """优化的并行规划流程"""
        start_time = time.time()

        print("🚀 启动并行规划模式...")

        # 并行获取天气和景点信息
        weather_task = asyncio.create_task(
            self._get_weather_info(request)
        )
        attractions_task = asyncio.create_task(
            self._get_attractions_info(request)
        )

        # 等待前两个完成
        weather_data, attractions_data = await asyncio.gather(
            weather_task, attractions_task,
            return_exceptions=True
        )

        # 从景点数据提取坐标
        last_poi_coord = self.master.extract_last_coord(attractions_data)

        # 并行获取酒店信息
        hotel_task = asyncio.create_task(
            self._get_hotels_info(request, last_poi_coord)
        )

        # 等待酒店信息
        hotels_data = await hotel_task

        # 最后整合规划（必须串行，因为需要整合所有数据）
        print("📋 整合所有数据生成最终行程...")
        planner_query = self._build_final_planner_prompt(
            request, attractions_data, weather_data, hotels_data
        )

        trip_plan = await self.master.agents["trip_planner"].run_structured(
            planner_query, TripPlan
        )

        total_time = time.time() - start_time
        print(f"✅ 并行规划完成，耗时: {total_time:.2f}秒")

        return trip_plan

    async def _get_weather_info(self, request: TripRequest) -> str:
        """获取天气信息"""
        print("🌤️ 并行：获取天气信息...")
        weather_query = f"查询{request.city}在 {request.start_date} 到{request.end_date}期间的天气预报。"
        return await self.master.agents["weather_expert"].run(weather_query)

    async def _get_attractions_info(self, request: TripRequest) -> str:
        """获取景点信息"""
        print("📍 并行：获取景点信息...")
        attr_query = f"请根据预期天气搜索{request.city}中关于'{', '.join(request.preferences)}'偏好的景点。"
        return await self.master.agents["attraction_agent"].run(attr_query)

    async def _get_hotels_info(self, request: TripRequest, coord: str) -> str:
        """获取酒店信息"""
        print("🏨 并行：获取酒店信息...")
        hotel_query = f"请基于坐标 {coord}搜索该坐标附近符合'{request.accommodation}'标准或者交通便利的酒店。"
        return await self.master.agents["hotel_expert"].run(hotel_query)

    def _build_final_planner_prompt(self, request: TripRequest,
                                   attractions: str, weather: str, hotels: str) -> str:
        """构建最终的上下文 Prompt"""
        return f"""请根据以下多方数据，为用户规划一个完美的旅行计划。
        ### 1. 用户基本需求
- 目的地: {request.city}
- 日期: {request.start_date} 至 {request.end_date} ({request.travel_days}天)
- 交通/住宿偏好: {request.transportation} / {request.accommodation}
- 兴趣偏好: {', '.join(request.preferences)}
- 额外备注: {request.free_text_input or "无"}

### 2. 外部参考信息 (并行获取)
- **景点备选**:
{attractions}
- **天气参考**:
{weather}
- **酒店推荐**:
{hotels}

### 3. 要求
1. 每天安排2-3个景点
2. 每天的行程必须包含景点列表 (`attractions`) 和至少三餐 (`meals`)。
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 景点经纬度必须基于搜索结果中的真实数据。
6.`overall_suggestions` 需要结合天气情况给出穿衣或出行建议。
7. 必须严格遵守TripPlan的JSON结构,返回完整的JSON格式数据
"""
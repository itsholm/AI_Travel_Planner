import asyncio
import time

from models.schemas import TripPlan, TripRequest
from services.planner_prompt_service import (
    build_attractions_query,
    build_final_planner_prompt,
    build_hotels_query,
    build_weather_query,
)
from trip_planner import TripMaster


class ParallelTripPlanner:
    """并行旅行规划器，负责并发调度各专家智能体。"""

    def __init__(self, master: TripMaster):
        self.master = master

    async def create_plan_optimized(
        self,
        request: TripRequest,
        memory_context: str = "",
    ) -> TripPlan:
        """执行并行规划流程，并返回结构化旅行计划。"""
        start_time = time.time()
        print("Starting parallel planning flow...")

        weather_task = asyncio.create_task(self._get_weather_info(request))
        attractions_task = asyncio.create_task(
            self._get_attractions_info(request, memory_context)
        )
        weather_data, attractions_data = await asyncio.gather(
            weather_task,
            attractions_task,
        )

        last_poi_coord = self.master.extract_last_coord(attractions_data)
        hotels_data = await self._get_hotels_info(request, last_poi_coord, memory_context)

        print("Building final plan from parallel lookup results...")
        planner_query = build_final_planner_prompt(
            request,
            attractions_data,
            weather_data,
            hotels_data,
            "parallel expert workflow",
            memory_context,
        )
        trip_plan = await self.master.agents["trip_planner"].run_structured(
            planner_query,
            TripPlan,
        )

        total_time = time.time() - start_time
        print(f"Parallel planning completed in {total_time:.2f}s.")
        return trip_plan

    async def _get_weather_info(self, request: TripRequest) -> str:
        """并行获取天气信息。"""
        print("Parallel step: fetching weather data...")
        return await self.master.agents["weather_expert"].run(build_weather_query(request))

    async def _get_attractions_info(
        self,
        request: TripRequest,
        memory_context: str = "",
    ) -> str:
        """并行获取景点候选信息。"""
        print("Parallel step: fetching attraction candidates...")
        return await self.master.agents["attraction_agent"].run(
            build_attractions_query(request, memory_context=memory_context)
        )

    async def _get_hotels_info(
        self,
        request: TripRequest,
        coord: str,
        memory_context: str = "",
    ) -> str:
        """获取候选景点附近的酒店建议。"""
        print("Parallel step: fetching hotel suggestions...")
        return await self.master.agents["hotel_expert"].run(
            build_hotels_query(request, coord, memory_context)
        )

    def _build_final_planner_prompt(self, request, attractions, weather, hotels):
        return build_final_planner_prompt(request, attractions, weather, hotels,
                                          "parallel expert workflow")

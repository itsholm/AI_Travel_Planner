import re
from amap_mcp import AmapMCPBatch
from SimpleAgent import SimpleAgent
from models.schemas import TripPlan
from services.planner_prompt_service import build_single_agent_planner_prompt
from system_prompt import WEATHER_AGENT_PROMPT, ATTRACTION_AGENT_PROMPT, HOTEL_AGENT_PROMPT, PLANNER_AGENT_PROMPT

class TripMaster:
    def __init__(self, llm, mcp_session, planning_mode="multi_agent"):
        if planning_mode not in {"multi_agent", "single_agent"}:
            raise ValueError("PLANNING_MODE must be multi_agent or single_agent")
        self.llm, self.session = llm, mcp_session
        self.planning_mode = planning_mode
        self.agents = {}

    async def initialize_team(self):
        config = {
            "weather_expert": ("天气专家", WEATHER_AGENT_PROMPT, ["weather"]),
            "attraction_agent": ("景点专家", ATTRACTION_AGENT_PROMPT, ["text_search", "poi_detail"]),
            "hotel_expert": ("酒店专家", HOTEL_AGENT_PROMPT, ["hotel_search", "poi_detail", "search_nearby"]),
            "trip_planner": ("行程规划专家", PLANNER_AGENT_PROMPT, []),
        }
        if self.planning_mode == "single_agent":
            config = {"trip_planner": ("行程规划专家", PLANNER_AGENT_PROMPT, None)}
        for key, (name, prompt, keywords) in config.items():
            agent = SimpleAgent(name, self.llm, prompt)
            if keywords is None or keywords:
                await agent.add_tool(AmapMCPBatch(self.session, include_keywords=keywords))
            self.agents[key] = agent

    def reset_agent_histories(self):
        for agent in self.agents.values():
            agent.reset_runtime_state()

    async def create_plan(self, request, memory_context=""):
        if self.planning_mode == "single_agent":
            return await self.agents["trip_planner"].run_structured(
                build_single_agent_planner_prompt(request, memory_context), TripPlan)
        from parallel_planner import ParallelTripPlanner
        return await ParallelTripPlanner(self).create_plan_optimized(request, memory_context)

    def extract_last_coord(self, text):
        coords = re.findall(r"(\d+\.\d+),\s*(\d+\.\d+)", text)
        return ",".join(coords[-1]) if coords else ""

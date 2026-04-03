#==================Orchestrator（总控）=====================#
import re
import traceback
from pyexpat import model

from pydantic_core import SchemaSerializer
from requests import models
from amap_mcp import AmapMCPBatch
from SimpleAgent import SimpleAgent
from system_prompt import ATTRACTION_AGENT_PROMPT,HOTEL_AGENT_PROMPT,WEATHER_AGENT_PROMPT,PLANNER_AGENT_PROMPT
from models.schemas import TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo, Location, Hotel
class TripMaster:
    def __init__(self, llm, mcp_session): #接收已经建立好的session,连接与业务分离
        self.llm = llm
        self.session = mcp_session
        self.agents = {} #

    async def initialize_team(self):
        """
        一键初始化函数：封装了工具注册和 Agent 创建
        """
        # 1. 定义专家及其需要的工具关键词
        team_config = {
            "weather_expert": {
                "role": "天气专家",
                "prompt": WEATHER_AGENT_PROMPT,
                "keywords": ["weather"]
            },
            "attraction_agent":{
                "role":"景点推荐专家",
                "prompt":ATTRACTION_AGENT_PROMPT,
                "keywords":["text_search","get_poi_photo"]
            },
            "hotel_expert": {
                "role": "酒店推荐专家",
                "prompt": HOTEL_AGENT_PROMPT,
                "keywords": ["hotel_search", "poi_detail","search_nearby"]
            },
            "trip_planner": {
                "role": "行程规划专家",
                "prompt": PLANNER_AGENT_PROMPT,#你负责整合信息，规划完整的旅游行程和路径。
                "keywords": ["search_nearby"] #行程规划专家不需要调用工具了
                #"direction", "text_search", "weather"
            }
        }

        # 2. 自动化循环创建并配发工具
        for key, cfg in team_config.items():
            # 逐个创建 Agent
            agent = SimpleAgent(
                name=cfg["role"],
                llm=self.llm,
                system_prompt=cfg["prompt"]
            )
            # 自动化按需索取工具
            if agent.name != "行程规划专家":
                batch = AmapMCPBatch(self.session, include_keywords=cfg["keywords"])
                await agent.add_tool(batch)
            
            self.agents[key] = agent
            print(f"--{agent.name}已创建--")
        
        print(f"旅行专家团初始化完成：已激活 {len(self.agents)} 名专家。")

    async def create_plan(self,request:TripRequest):
        """
        使用多智能体协作生成旅行计划
        Args:
            request: 旅行请求
        Returns:
            旅行计划
        """
        try:
            # 1. 获取天气概况
            print("🌤️ 步骤 1: 正在同步气象信息...")
            weather_query = f"查询{request.city}在 {request.start_date} 到{request.end_date}期间的天气预报。"
            weather_data = await self.agents["weather_expert"].run(weather_query)
            #weather=weather_data[]
            # 2. 获取景点数据
            print("📍 步骤 2: 正在检索目的地景点...")
            attr_query = f"请根据{weather_data}搜索{request.city}中关于'{', '.join(request.preferences)}'偏好的景点。"
            attractions_data = await self.agents["attraction_agent"].run(attr_query)
            last_poi_coord = self.extract_last_coord(attractions_data)

            # 3. 获取住宿建议
            print("🏨 步骤 3: 正在筛选酒店...")
            hotel_query = f"请基于坐标 {last_poi_coord}搜索该坐标附近符合'{request.accommodation}'标准或者交通便利的酒店。"
            hotels_data = await self.agents["hotel_expert"].run(hotel_query)

            # 4. 结构化整合生成最终计划
            print("📋 步骤 4: 整合全量数据并生成结构化行程...")
            planner_query = self._build_final_planner_prompt(request, attractions_data, weather_data, hotels_data)

            # 核心修改：利用 run_structured 直接获取 Pydantic 对象
            trip_plan = await self.agents["trip_planner"].run_structured(planner_query, TripPlan)
            return trip_plan
        except Exception as e:
            print(f"❌ 规划失败: {str(e)}")
            traceback.print_exc()
            # 这里可以调用一个 fallback 逻辑返回基础行程
            raise e
    
    def _build_final_planner_prompt(self, request: TripRequest, attractions: str, weather: str, hotels: str) -> str:
        """构建最终的上下文 Prompt"""
        final_query =  f"""请根据以下多方数据，为用户规划一个完美的旅行计划。
        ### 1. 用户基本需求
- 目的地: {request.city}
- 日期: {request.start_date} 至 {request.end_date} ({request.travel_days}天)
- 交通/住宿偏好: {request.transportation} / {request.accommodation}
- 兴趣偏好: {', '.join(request.preferences)}
- 额外备注: {request.free_text_input or "无"}

### 2. 外部参考信息 (由专家Agent提供)
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

        return final_query


# 💡 核心修复：新增辅助方法用于提取坐标
    def extract_last_coord(self, text: str) -> str:
        """从专家返回的文本中提取最后一组经纬度坐标"""
        # 匹配格式如 [116.39, 39.91] 或 116.39, 39.91
        coords = re.findall(r"(\d+\.\d+),\s*(\d+\.\d+)", text)
        if coords:
            last = coords[-1]
            return f"{last[0]},{last[1]}"
        return ""
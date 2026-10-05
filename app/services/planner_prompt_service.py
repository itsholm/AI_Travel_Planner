from models.schemas import TripRequest


def _memory_block(memory_context: str = "") -> str:
    """把长期记忆格式化为可拼接到提示词中的片段。"""
    if not memory_context:
        return ""
    return f"\n\n### 用户长期记忆\n{memory_context}"


def build_weather_query(request: TripRequest) -> str:
    """构建天气专家使用的查询提示词。"""
    return (
        f"查询{request.city}在 {request.start_date} 到 {request.end_date} "
        "期间的天气预报。"
    )


def build_attractions_query(
    request: TripRequest,
    weather_data: str | None = None,
    memory_context: str = "",
) -> str:
    """构建景点专家使用的查询提示词。"""
    preferences = ", ".join(request.preferences) if request.preferences else "城市经典景点"
    memory = _memory_block(memory_context)
    if weather_data:
        return (
            f"请根据以下天气信息：{weather_data}，搜索{request.city}中与"
            f"{preferences}相关的景点，并优先推荐适合当前天气的安排。"
            f"{memory}"
        )
    return (
        f"请根据预期天气情况，搜索{request.city}中与{preferences}相关的景点。"
        f"{memory}"
    )


def build_hotels_query(request: TripRequest, coord: str, memory_context: str = "") -> str:
    """构建酒店专家使用的查询提示词。"""
    return (
        f"请基于坐标 {coord} 搜索附近符合“{request.accommodation}”标准，"
        "或交通便利的酒店。"
        f"{_memory_block(memory_context)}"
    )




def build_single_agent_planner_prompt(
    request: TripRequest,
    memory_context: str = "",
) -> str:
    """构建单 Agent 实验中由行程规划器直接执行的任务提示词。"""
    preferences = ", ".join(request.preferences) if request.preferences else "无特别偏好"
    note = request.free_text_input or "无"
    memory = _memory_block(memory_context)
    return f"""当前是单 Agent 行程规划实验：你是唯一的执行者，不会收到天气、景点或酒店专家的预处理结果。

请基于用户需求自行判断并调用必要的 MCP 工具，获取天气、景点、酒店和路线等实时信息，再生成完整的旅行计划。工具调用应以完成行程为目标；不要为了实验而无意义地调用工具。

### 用户本次需求
- 目的地: {request.city}
- 日期: {request.start_date} 至 {request.end_date} ({request.travel_days}天)
- 交通 / 住宿偏好: {request.transportation} / {request.accommodation}
- 兴趣偏好: {preferences}
- 额外备注: {note}
{memory}

### 规划要求
1. 优先使用工具返回的真实景点、酒店和坐标；天气、景点、酒店信息均由你直接查询。
2. 每天安排 2-3 个景点，并根据景点位置考虑交通和酒店选址。
3. 每天包含至少三餐；`overall_suggestions` 结合天气给出出行建议。
4. 工具不可用时可以基于常识补全，但须在 `overall_suggestions` 中说明部分实时数据获取失败。
5. 最终仅输出完整的 TripPlan JSON。"""

def build_final_planner_prompt(
    request: TripRequest,
    attractions: str,
    weather: str,
    hotels: str,
    source_label: str,
    memory_context: str = "",
) -> str:
    """构建串行和并行规划器共用的最终规划提示词。"""
    preferences = ", ".join(request.preferences) if request.preferences else "无特别偏好"
    note = request.free_text_input or "无"
    memory = _memory_block(memory_context)
    return f"""请根据以下多方数据，为用户规划一份完整的旅行计划。
### 1. 用户本次需求
- 目的地: {request.city}
- 日期: {request.start_date} 至 {request.end_date} ({request.travel_days}天)
- 交通 / 住宿偏好: {request.transportation} / {request.accommodation}
- 兴趣偏好: {preferences}
- 额外备注: {note}
{memory}

### 2. 外部参考信息({source_label})
- 景点候选:
{attractions}

- 天气参考:
{weather}

- 酒店推荐:
{hotels}

### 3. 输出要求
1. 每天安排 2-3 个景点。
2. 每天的行程必须包含景点列表(`attractions`)和至少三餐(`meals`)。
3. 每天推荐一个具体酒店，优先从酒店信息中选择。
4. 考虑景点之间的距离和交通方式。
5. 景点经纬度必须基于搜索结果中的真实数据。
6. `overall_suggestions` 需要结合天气给出穿衣或出行建议。
7. 必须严格遵守 TripPlan 的 JSON 结构，返回完整 JSON 数据。"""

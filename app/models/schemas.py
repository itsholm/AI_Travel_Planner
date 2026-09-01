#---------自底向上的数据模型--------------
from enum import Enum
from pydantic import BaseModel,Field, field_validator
from typing import Optional,List, Dict, Any

# ============ 请求模型 ============

class TripRequest(BaseModel):
    """旅行规划请求"""
    city: str = Field(..., description="目的地城市", example="北京")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD", example="2025-06-01")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD", example="2025-06-03")
    travel_days: int = Field(..., description="旅行天数", ge=1, le=30, example=3)
    transportation: str = Field(..., description="交通方式", example="公共交通")
    accommodation: str = Field(..., description="住宿偏好", example="经济型酒店")
    preferences: List[str] = Field(default=[], description="旅行偏好标签", example=["历史文化", "美食"])
    free_text_input: Optional[str] = Field(default="", description="额外要求", example="希望多安排一些博物馆")
    
    class Config:
        json_schema_extra = {
            "example": {
                "city": "北京",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "travel_days": 3,
                "transportation": "公共交通",
                "accommodation": "经济型酒店",
                "preferences": ["历史文化", "美食"],
                "free_text_input": "希望多安排一些博物馆"
            }
        }


class POISearchRequest(BaseModel):
    """POI搜索请求"""
    keywords: str = Field(..., description="搜索关键词", example="故宫")
    city: str = Field(..., description="城市", example="北京")
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class RouteRequest(BaseModel):
    """路线规划请求"""
    origin_address: str = Field(..., description="起点地址", example="北京市朝阳区阜通东大街6号")
    destination_address: str = Field(..., description="终点地址", example="北京市海淀区上地十街10号")
    origin_city: Optional[str] = Field(default=None, description="起点城市")
    destination_city: Optional[str] = Field(default=None, description="终点城市")
    route_type: str = Field(default="walking", description="路线类型: walking/driving/transit")



#=======================响应模型==========================
class Location(BaseModel):
    """位置信息(经纬度坐标)"""
    longitude: float = Field(...,description="经度",ge=-180,le=180) #...表示必填
    latitude: float = Field(...,description="纬度",ge=-90,le=90)

class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(...,description="景点名称")
    address: str = Field(...,description="地址")
    location: Location = Field(...,description="经纬度坐标")
    visit_duration: int = Field(...,description="建议游览时间(分钟)",gt=0)
    description: str = Field(...,description="景点描述")
    category: Optional[str] = Field(default="景点",description="景点类别")
    ticket_price: int = Field(default=0,ge=0,description="门票价格(元)")

class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(...,description="餐饮类型：早餐/午餐/晚餐/小吃")
    name: str = Field(...,description="餐饮名称")
    address: Optional[str] = Field(default=None,description="地址")
    location: Optional[Location] = Field(default=None,description="经纬度坐标")
    description: Optional[str] = Field(default=None,description="描述")
    estimated_cost: int = Field(default=0,description="预估费用(元)")

class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(...,description="酒店名称")
    address: str = Field(default="",description="酒店地址")
    location: Optional[Location] = Field(default=None,description="酒店位置")
    price_range: str = Field(default="",description="价格范围")
    rating: str = Field(default="",description="评分")
    distance: str = Field(default="",description="距离景点距离")
    type: str = Field(default="",description="酒店类型")
    estimated_cost: int = Field(default=0,description="预估费用(元/晚)")

class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0,description="景点门票总费用")
    total_hotels: int = Field(default=0,description="酒店总费用")
    total_meals: int = Field(default=0,description="餐饮总费用")
    total_transportation: int = Field(default=0,description="交通总费用")
    total: int = Field(default=0,description="总费用")

class DayPlan(BaseModel):
    """
    单日行程计划
    对齐前端 TravelResult.vue 中的 {{ day.weather }} 和 {{ day.date }}
    """
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="天数索引")
    description: str = Field(..., description="今日行程概述")
    weather: str = Field(default="晴", description="当日天气描述，对齐前端显示")
    transportation: str = Field(..., description="交通方式建议")
    accommodation: str = Field(..., description="建议住宿类型")
    hotel: Optional[Hotel] = Field(default=None, description="建议酒店详情")
    attractions: List[Attraction] = Field(default_factory=list, description="景点列表")
    meals: List[Meal] = Field(default_factory=list, description="餐饮安排")

class WeatherInfo(BaseModel):
    """天气信息"""
    date: str = Field(...,description="日期")
    day_weather: str = Field(...,description="当日天气")
    night_weather: str = Field(...,description="夜间天气")
    day_temp: int = Field(...,description="白天温度(摄氏度)")
    night_temp: int = Field(...,description="夜间温度(摄氏度)")
    wind_direction: Optional[str] = Field(default="无数据",description="风向")
    wind_power: Optional[str] = Field(default="无数据",description="风力")
    
    @field_validator('day_temp','night_temp',mode='before')
    def parse_temperature(cls,v):
        """解析温度字符串："16°C" -> 16"""
        if isinstance(v,str):
            v = v.replace('°C','').replace('℃','').replace('°','').strip()
            try:
                return int(v)
            except ValueError:
                return 0  # 容错处理
        return v

class TripPlan(BaseModel):
    """旅行计划"""
    city: str = Field(...,description="目的地城市")
    start_date: str = Field(...,description="开始日期")
    end_date: str = Field(...,description="结束日期")
    travel_days: int = Field(default=1, description="旅行总天数")
    days: List[DayPlan] = Field(default_factory=list,description="每日行程")
    weather_info: List[WeatherInfo] = Field(default_factory=list,description="多日天气概况")
    overall_suggestions: str = Field(...,description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="总预算预估")


# ============ 会话模型 ============

class ConversationMessage(BaseModel):
    """对话消息"""
    role: str = Field(..., description="角色: user/assistant", example="user")
    content: str = Field(..., description="消息内容", example="把第二天的景点换成天坛")
    timestamp: Optional[str] = Field(default="", description="时间戳")


class Session(BaseModel):
    """会话信息"""
    session_id: str = Field(..., description="会话唯一标识", example="abc123-def456")
    user_request: Optional[TripRequest] = Field(default=None, description="用户的初始旅行请求")
    current_plan: Optional[TripPlan] = Field(default=None, description="当前行程计划")
    messages: List[ConversationMessage] = Field(default_factory=list, description="对话历史消息")
    summary: str = Field(default="", description="历史对话摘要")
    updated_at: Optional[str] = Field(default="", description="最后更新时间")


class ModifyRequest(BaseModel):
    """修改行程请求"""
    session_id: str = Field(..., description="会话ID", example="abc123-def456")
    instruction: str = Field(..., description="修改指令", example="把第二天的景点换成天坛")


# ============ 企业差旅 Runtime 模型 ============

class TaskState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RETRYING = "RETRYING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolRiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ToolCallStatus(str, Enum):
    PROPOSED = "PROPOSED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ApprovalDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class BusinessTripRequest(BaseModel):
    """企业差旅任务请求"""
    origin_city: str = Field(..., description="出发城市", example="上海")
    destination_city: str = Field(..., description="目的地城市", example="杭州")
    start_date: str = Field(..., description="出发日期 YYYY-MM-DD", example="2026-09-09")
    end_date: str = Field(..., description="返程日期 YYYY-MM-DD", example="2026-09-10")
    meeting_time: str = Field(..., description="会议时间", example="周四下午2点")
    meeting_location: str = Field(..., description="会议地点", example="滨江客户公司")
    budget_limit: int = Field(..., ge=0, description="预算上限，单位元", example=4000)
    employee_level: str = Field(default="standard", description="员工差旅等级")
    avoid_red_eye: bool = Field(default=True, description="是否避免红眼航班")
    hotel_within_km: Optional[float] = Field(default=3.0, gt=0, description="酒店距离会议地点上限")
    hotel_refundable_required: bool = Field(default=True, description="是否要求可取消酒店")
    travelers: List[str] = Field(default_factory=list, description="同行人")
    notify_emails: List[str] = Field(default_factory=list, description="行程通知邮箱")
    free_text_input: Optional[str] = Field(default="", description="额外约束")


class ToolSpec(BaseModel):
    """Runtime 可见的工具元数据"""
    name: str
    server: str = "local"
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    required_scope: str = "travel:read"
    side_effect: bool = False
    timeout_ms: int = 10000
    max_retries: int = 2
    cache_ttl: Optional[int] = None


class ToolCallRecord(BaseModel):
    call_id: str
    task_id: str
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    args_hash: str = ""
    idempotency_key: str = ""
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    side_effect: bool = False
    status: ToolCallStatus = ToolCallStatus.PROPOSED
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class Approval(BaseModel):
    approval_id: str
    task_id: str
    call_id: str
    tool_name: str
    action: str
    risk_level: ToolRiskLevel
    preview: Dict[str, Any] = Field(default_factory=dict)
    decision: ApprovalDecision = ApprovalDecision.PENDING
    created_at: str = ""
    decided_at: Optional[str] = None
    expires_at: Optional[str] = None


class Checkpoint(BaseModel):
    checkpoint_id: str
    task_id: str
    step: str
    state: TaskState
    state_json: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: str = ""


class TaskEvent(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class BusinessTripTask(BaseModel):
    task_id: str
    user_id: str = "demo-user"
    goal: str
    request: BusinessTripRequest
    state: TaskState = TaskState.CREATED
    current_step: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class CreateTaskResponse(BaseModel):
    task_id: str
    state: TaskState
    current_step: str
    events: List[TaskEvent] = Field(default_factory=list)
    pending_approval: Optional[Approval] = None
    result: Optional[Dict[str, Any]] = None

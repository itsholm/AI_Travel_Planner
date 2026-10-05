# 智能旅行规划项目优化空间梳理

本文基于当前仓库代码快照整理，时间为 2026-06-04。项目当前定位可以概括为：基于 FastAPI、Vue、MCP、高德地图、Unsplash 和多 Agent ReAct 循环的智能旅行规划助手。它已经具备“生成行程、修改行程、会话持久化、长期偏好记忆、预算估算、可观测面板”等原型能力，但距离真实业务场景中的“可用、可信、可持续优化的旅行顾问产品”还有不少优化空间。

## 1. 当前项目现状

### 1.1 已经形成的主链路

当前端提交旅行请求后，链路大致如下：

1. `frontend/src/App.vue` 收集目的地、日期、交通、住宿、兴趣偏好和额外要求。
2. `app/api.py` 的 `/api/plan` 创建 `session_id`，读取长期用户记忆，调用增强版并行规划 harness。
3. `app/parallel_planner.py` 并行获取天气和景点信息，然后根据景点坐标获取酒店，再交给规划 Agent 生成结构化行程。
4. `app/trip_planner.py` 初始化天气、景点、酒店、规划四类专家 Agent。
5. `app/SimpleAgent.py` 自研 ReAct 循环，负责组装消息、发送工具 schema、解析工具调用、执行 MCP 工具、再把观察结果喂回模型。
6. `app/amap_mcp.py` 把 MCP 工具转换为 OpenAI function calling 形式。
7. `app/services/amap_mcp_service.py` 和 `app/services/unsplash_mcp_service.py` 通过 FastMCP 暴露高德地图和图片搜索工具。
8. `app/models/schemas.py` 用 Pydantic 定义 `TripRequest`、`TripPlan`、`DayPlan`、`Attraction`、`Hotel`、`Budget` 等核心结构。
9. `app/services/session_store.py` 和 `app/services/user_memory_service.py` 分别管理短期会话和长期偏好。
10. `app/observability/` 收集 HTTP、Agent、LLM、MCP、外部服务、安全、会话等运行指标，前端 `ObservabilityDashboard.vue` 展示运行面板。

这个主链路说明项目已经不是简单 prompt demo，而是一个初步的 agentic application。

### 1.2 主要优点

- 业务对象已经结构化：请求、每日行程、景点、餐饮、酒店、天气、预算都用 Pydantic 建模。
- MCP 已经作为工具协议进入项目：高德和 Unsplash 都通过 MCP server 暴露工具，Agent 通过客户端发现并调用。
- 有多 Agent 分工：天气、景点、酒店、最终规划各自有角色提示词和工具范围。
- 已经做了并行优化：天气和景点可以并发获取，减少纯串行等待。
- 已经开始做产品闭环：支持会话恢复、行程修改、长期偏好记忆、预算、地图展示、观测面板。
- 已经有安全和可观测雏形：`harness_enhanced.py` 做输入输出校验、重试、降级；`observability/` 记录多个层面的指标。

### 1.3 当前短板

- 编排层仍然是自研线性流程，状态和分支较弱。真实旅行规划经常需要条件分支、失败重试、人工确认、候选方案对比和多次回填。
- MCP 工具结果主要是字符串，没有充分使用结构化输出、output schema、resource link、权限/风险元数据。
- 结构化输出依赖“把 JSON Schema 写进 prompt + 正则抽取 JSON”，可靠性不够。
- 旅行业务还停留在“推荐文本”，没有充分校验路线可行性、营业时间、门票、距离、拥挤度、预算真实性、用户体力等现实约束。
- 会话和长期记忆都存在于 SQLite，适合原型，但不适合多人、多设备、审计和生产部署。
- 前端已经有编辑、导出入口，但手动编辑没有后端版本化保存，导出 PDF/图片仍是占位。
- 测试主要是手动脚本和 benchmark 脚本，缺少稳定的 mock MCP、契约测试、端到端回归和 agent eval。
- 可观测目前以进程内内存聚合为主，重启后丢失，也没有接入标准化 OpenTelemetry 链路。

## 2. 真实业务场景重新定位

如果把它当作真实产品，而不是课程项目或技术 demo，建议定位为：

> 面向中国城市自由行用户的智能旅行顾问：帮助用户从“模糊想法”到“可执行行程”，并在天气、预算、交通、酒店、餐饮和临时修改之间持续做取舍。

### 2.1 目标用户场景

- 周末短途游：用户只知道目的地和天数，希望快速生成低成本、交通方便的计划。
- 家庭出行：有老人、小孩、过敏、午休、体力限制，需要更稳妥的路线和节奏。
- 商务顺带游：用户已有会议地点和时间，只能在空档安排景点。
- 情侣或朋友多人出行：成员偏好不同，需要生成候选方案并协商。
- 本地深度游：用户去过常规景点，希望避开重复推荐，加入小众路线和餐饮。
- 临时变更：天气变化、景点关闭、预算调整、用户临时想换景点，系统需要快速重排。

### 2.2 业务价值应从“生成”升级为“决策”

当前系统的核心产出是 `TripPlan`，但真实用户真正需要的是：

- 为什么这样安排。
- 今天能不能走得完。
- 哪些景点必须提前预约。
- 预算是否可信。
- 如果下雨、堵车、景点关闭怎么办。
- 能不能比较 A/B 两套方案。
- 修改后原计划如何变化。
- 最后能不能导出、分享、继续迭代。

所以后续优化不要只追求“模型回答更漂亮”，而要让系统变成可校验、可解释、可修改、可回放的规划决策系统。

## 3. 各环节优化空间

### 3.1 用户输入与需求澄清

#### 当前情况

`TripRequest` 包含城市、日期、天数、交通方式、住宿偏好、兴趣标签和自由文本。这个结构对原型足够，但对真实规划还不够。

#### 主要问题

- 缺少人数、年龄结构、预算区间、出发地、同行关系、体力水平、饮食禁忌、是否接受早起、是否需要无障碍等关键约束。
- 当前表单一次性收集信息，缺少“信息不足时动态追问”的能力。
- 自由文本被直接放入 prompt，缺少结构化抽取和冲突检测。

#### 优化建议

- 增加 `TravelerProfile` 和 `TripConstraints`：人数、年龄、预算、体力、偏好强度、禁忌、出发地、是否带行李、是否自驾等。
- 对 `free_text_input` 做结构化抽取：把“海鲜过敏”“不想早起”“想看升旗”转换成可验证约束。
- 增加缺失信息追问机制：如果用户只说“帮我安排南京三日游”，系统先生成一个最小可行方案，同时提示可补充预算、人数和偏好。
- 使用 MCP elicitation 思路做结构化追问。MCP 官方说明 elicitation 可以让 server 通过 client 向用户请求额外结构化信息，并用 JSON Schema 校验响应；这个适合“预算是多少、是否带老人、是否接受夜间交通”等旅行参数，但不要用来索取敏感信息。

#### 可落地改造

- 新增 `TripRequestDraft`：允许信息不完整。
- 新增 `TripClarification`：记录缺失字段、问题、默认值和是否必须询问。
- `/api/plan` 可分为两种模式：`auto_fill` 直接用默认值生成，`ask_first` 先返回澄清问题。
- 前端把一次性表单改成“必要字段 + 高级偏好折叠 + 生成后可补充”。

### 3.2 Agent 编排层

#### 当前情况

当前编排集中在 `TripMaster` 和 `ParallelTripPlanner`：

- 天气、景点、酒店、规划专家由 `TripMaster.initialize_team()` 创建。
- 并行流程先天气和景点并发，再用景点坐标查酒店，最后生成总计划。
- `SimpleAgent` 自己维护 ReAct 循环。

#### 主要问题

- 状态没有显式图结构，后续加入路线优化、门票检查、预算校验、方案对比时，流程会越来越难维护。
- 酒店依赖 `extract_last_coord()` 从文本里正则提取最后一个坐标，鲁棒性较弱。
- 所有专家 Agent 的返回大多是文本，最终 planner 需要再从文本中理解和重组。
- 出错后只能整体重试，难以做到“景点失败只重查景点”“天气失败用降级天气”。

#### 新技术方向

建议把编排层逐步迁移到图状态运行时，而不是继续扩大自研 ReAct 循环。

优先方向：

- LangGraph：适合状态图、checkpoint、human-in-the-loop、可恢复执行和多步 agent workflow。官方文档明确说明 checkpoint 可以支持人工中断、会话记忆、time travel debugging 和 fault-tolerant execution，也支持不同持久化强度。
- OpenAI Agents SDK：如果项目未来主要绑定 OpenAI，可以考虑用 SDK 管理 agent、handoff、工具、guardrail、trace。官方文档的定位是：当应用拥有 orchestration、tool execution、approvals 和 state 时，使用 Agents SDK 页面；简单的一次模型调用加工具可用 Responses API。

对当前项目更合理的路线是：

- 保留 MCP 作为工具协议。
- 优先用 LangGraph 替换 `ParallelTripPlanner + SimpleAgent` 的流程控制。
- 如果后续模型和运行时强绑定 OpenAI，再评估 OpenAI Agents SDK 是否替代部分自研 harness。

#### 推荐图结构

建议将规划流程拆成这些节点：

1. `parse_request`：结构化抽取用户需求和约束。
2. `load_memory`：读取长期偏好和历史目的地。
3. `weather_lookup`：天气查询。
4. `poi_search`：景点候选召回。
5. `poi_enrich`：景点评分、类型、地址、坐标、营业时间、门票等补充。
6. `route_optimize`：按距离、时间、交通方式和体力约束排序。
7. `hotel_lookup`：按路线中心点或每日终点搜索住宿。
8. `meal_lookup`：按景点附近和饮食偏好推荐餐饮。
9. `budget_estimate`：预算估算。
10. `plan_compose`：生成候选行程。
11. `plan_validate`：验证日期、景点数量、坐标、路线可行性、预算、天气建议。
12. `repair_or_finalize`：失败则局部修复，成功则输出。

每个节点输入输出都进入共享 state，最终 `TripPlan` 不再依赖从大段字符串中猜测。

### 3.3 MCP 工具层

#### 当前情况

当前 MCP server 提供高德文本搜索、天气、酒店、路线、POI 详情、周边搜索和 Unsplash 图片搜索。客户端通过 `AmapMCPBatch` 拉取工具列表，并按关键词给不同 Agent 分配工具。

#### 主要问题

- 工具返回值大多是字符串，缺少机器可验证的数据结构。
- 工具没有 output schema，客户端无法稳定验证。
- 工具没有风险等级、缓存策略、调用成本、数据来源、限流信息等元数据。
- 当前只使用 MCP tools，没有充分使用 prompts、resources、elicitation。
- 生产场景下如果 MCP server 从 stdio 发展到远程 HTTP transport，需要更严格的授权和 token audience 校验。

#### 结合 MCP 官方能力的优化

MCP 官方把 server primitives 分为：

- Prompts：用户可控的模板或指令。
- Resources：应用控制的结构化数据或上下文。
- Tools：模型可调用的执行函数。

当前项目主要使用 Tools，后续可以扩展为：

- Tools：执行搜索、路线、天气、图片、票务、酒店价格等动作。
- Resources：暴露已缓存的 POI 详情、城市攻略、用户当前计划、历史计划版本、天气快照。
- Prompts：暴露“亲子游规划”“商务空档游”“雨天备选路线”“低预算路线”等可复用模板。
- Elicitation：工具发现关键字段缺失时，通过客户端请求用户补充。

#### 工具返回格式建议

建议定义统一工具结果：

```json
{
  "success": true,
  "source": "amap",
  "operation": "text_search",
  "data": {},
  "raw": {},
  "error": null,
  "cache_ttl_seconds": 3600,
  "confidence": 0.86
}
```

对每个 MCP tool 增加：

- `inputSchema`
- `outputSchema`
- `risk_level`
- `side_effects`
- `cache_policy`
- `quota_cost`
- `required_scope`
- `source`
- `freshness`

MCP tools 官方规范已经支持 structured content 和 output schema；工具如果声明 output schema，server 应返回符合 schema 的结构化结果，client 应验证结构化结果。

#### 生产授权建议

当前 stdio transport 从环境变量读取 API key 可以继续用于本地开发。若后续改为 HTTP-based MCP server，需要：

- 使用 OAuth 2.1 风格授权。
- 每个 MCP server 有明确 resource identifier。
- token 只发给目标 MCP server，不做 token passthrough。
- 采用最小权限 scope，例如 `mcp:amap.read.basic`、`mcp:amap.route`、`mcp:image.search`。
- 对高风险工具使用逐步提权和用户确认。

MCP 安全最佳实践强调 progressive least-privilege scope model，避免 wildcard、full-access 或一次性暴露所有权限。

### 3.4 LLM 调用与结构化输出

#### 当前情况

`llm_client.py` 使用 OpenAI Chat Completions 兼容协议；`SimpleAgent.run_structured()` 把 Pydantic JSON Schema 拼进 prompt，再用正则提取 JSON 并验证。

#### 主要问题

- prompt 中要求 JSON 不等于模型一定输出合法 JSON。
- 正则提取 `{.*}` 容易误匹配。
- 解析失败后只有报错，没有修复 loop 或局部重试。
- 结构化输出和工具调用混在同一个自研循环里，后续维护成本会增加。

#### 优化建议

- 如果模型供应商支持，优先使用 structured output 或 `response_format/json_schema`，减少“提示词强迫 JSON”的不确定性。OpenAI 官方 structured outputs 明确用于让输出遵循 JSON Schema，且区分了 function calling 和最终响应结构化输出的使用场景。
- 保留 Pydantic 二次校验，不要完全依赖模型输出。
- 对结构化失败做“修复型重试”：只把错误字段和 schema 片段发给模型修复，而不是重跑整个行程。
- 把最终输出拆成多个结构化阶段：
  - `CandidateAttractions`
  - `RoutePlan`
  - `HotelCandidates`
  - `MealCandidates`
  - `TripPlan`
  - `PlanValidationResult`
- 引入 `plan_validate` 节点，验证：
  - `travel_days` 和 `days` 数量一致。
  - 日期连续。
  - 每天景点数符合规则。
  - 坐标合法且来自工具结果。
  - 餐饮至少覆盖三餐。
  - 酒店价格和预算字段一致。
  - 如果天气恶劣，路线有备选建议。

### 3.5 旅行业务智能

#### 当前情况

项目能生成景点、酒店、餐饮、天气和预算，但业务推理还偏粗。

#### 主要问题

- 路线只是地图连线，没有真正按交通耗时优化。
- 酒店根据“最后一个景点坐标”查找，可能导致住宿位置不合理。
- 景点营业时间、闭馆日、门票、预约、拥挤程度没有纳入。
- 预算估算里交通是固定 `50 * travel_days`，酒店、餐饮、门票高度依赖模型输出。
- 没有多方案比较，也没有雨天/拥挤/预算超限备选。

#### 优化建议

- 增加路线可行性模型：
  - 每天总步行距离。
  - 景点之间交通时长。
  - 景点游览时长。
  - 用餐时间。
  - 午休或亲子缓冲时间。
- 增加酒店位置策略：
  - 按每日路线中心点。
  - 按第一天/最后一天交通枢纽。
  - 按预算和地铁便利度。
  - 按用户偏好在候选酒店中排序。
- 增加场景模板：
  - 低预算路线。
  - 亲子路线。
  - 老人友好路线。
  - 雨天路线。
  - 摄影路线。
  - 美食优先路线。
- 增加候选方案：
  - 标准方案。
  - 轻松方案。
  - 高强度打卡方案。
  - 雨天备选方案。
- 增加解释字段：
  - `why_this_route`
  - `tradeoffs`
  - `risk_notes`
  - `alternatives`

### 3.6 会话、记忆与用户画像

#### 当前情况

`session_store.py` 用 SQLite 存储会话，`user_memory_service.py` 存储默认用户的长期偏好。长期记忆包括交通偏好、住宿偏好、兴趣、历史城市和 notes。

#### 主要问题

- 当前只有 `default` 用户，没有真实用户身份。
- 长期记忆没有用户授权、删除、导出、过期和冲突策略。
- 自由文本 notes 容易把短期需求当成长期偏好。
- 手动编辑没有形成计划版本。

#### 优化建议

- 区分三类记忆：
  - 会话记忆：本次规划和修改。
  - 用户长期偏好：稳定偏好，如住宿、交通、兴趣、禁忌。
  - 业务事实记忆：城市攻略、POI、历史价格、天气快照。
- 给长期记忆增加来源和置信度：
  - `source_session_id`
  - `evidence`
  - `confidence`
  - `last_seen_at`
  - `user_confirmed`
- 增加用户可控能力：
  - 查看记忆。
  - 删除单条记忆。
  - 暂停个性化。
  - 导出个人数据。
- 增加计划版本表：
  - `plan_revisions`
  - `revision_id`
  - `session_id`
  - `plan_json`
  - `change_source`: AI modify / manual edit / regenerate
  - `diff_summary`
  - `created_at`

### 3.7 数据存储和缓存

#### 当前情况

SQLite 对原型足够，外部服务结果没有明显缓存。图片每次前端打开结果页时按景点名调用 `/api/poi/photo`。

#### 主要问题

- 外部 API 调用成本和延迟不可控。
- 高德和 Unsplash 返回可能波动，同一次计划再次打开时结果可能变化。
- 观测数据进程内存储，重启丢失。
- 缺少数据库迁移和数据版本。

#### 优化建议

- 原型期继续 SQLite，但增加 schema migration。
- 产品化后改为：
  - PostgreSQL：用户、会话、计划版本、工具调用记录。
  - Redis：短期缓存、限流、任务状态。
  - pgvector 或向量库：城市攻略、用户偏好、历史计划、POI 语义召回。
- 对外部 API 做缓存：
  - 天气：按城市和日期缓存，TTL 较短。
  - POI：按城市、关键词、类别缓存，TTL 中等。
  - 图片：按景点名缓存，TTL 较长。
  - 路线：按起终点和交通方式缓存，TTL 中等。
- 工具结果写入 `tool_call_records`，便于回放、评估和审计。

### 3.8 性能优化

#### 当前情况

项目已经并行执行天气和景点查询，并记录 tokens 和耗时。

#### 主要问题

- MCP server 中大量使用同步 `requests`，在高并发下容易阻塞。
- 外部服务缺少统一 retry、timeout、backoff、circuit breaker。
- 每个 Agent 仍然可能拿到较多工具 schema，后续工具增加后会有 prompt bloat。
- `TripPlan` schema 很大，每次结构化输出都塞进 prompt，token 成本高。

#### 优化建议

- MCP server 改用 `httpx.AsyncClient` 或异步请求池。
- 为外部服务封装统一客户端：
  - timeout
  - retry with exponential backoff
  - circuit breaker
  - rate limit
  - cache
  - fallback
- 做工具检索路由：
  - 不把全部工具 schema 都发给模型。
  - 先按任务选择候选工具，再暴露给模型。
  - 对每个 Agent 使用最小工具集。
- 对固定 prompt、schema、工具说明使用 prompt cache 或 schema cache。
- 前端使用 SSE/WebSocket 展示规划进度：
  - 正在查天气。
  - 正在找景点。
  - 正在优化路线。
  - 正在生成预算。
  - 正在校验结果。
- 对最终计划生成做分阶段流式返回，用户先看到候选景点和路线，再看到完整计划。

### 3.9 安全、权限与治理

#### 当前情况

`harness_enhanced.py` 通过关键词、正则、长度、预算上限等做输入输出检查；可观测层记录安全事件。

#### 主要问题

- 关键词规则对 prompt injection 和工具滥用防护较弱。
- 当前工具都是读类工具，风险还可控；如果以后接入酒店预订、支付、发短信、发邮件等动作，需要权限模型。
- 长期记忆涉及用户偏好和潜在敏感信息，需要明确授权。

#### 优化建议

- 建立工具风险分级：
  - L0：纯读缓存。
  - L1：外部搜索。
  - L2：读取用户私有数据。
  - L3：写入或修改计划。
  - L4：交易、预订、支付、发送消息。
- 每次工具调用记录：
  - tool name
  - arguments
  - data source
  - risk level
  - user/session
  - approval state
  - result hash
- 对高风险工具加入人工确认。
- 对 MCP remote server 使用最小权限 scope。
- 对长期记忆提供显式开关和删除能力。
- 对外部图片和第三方数据增加来源标记，避免版权和可信度问题。
- 将 `observability/reset` 这类测试接口限制在开发环境或加鉴权。

### 3.10 可观测性与 AgentOps

#### 当前情况

项目已经有自定义 observer，覆盖 HTTP、Agent、LLM、工具调用、外部服务、会话压缩、安全等维度，前端也能展示 dashboard。

#### 主要问题

- 指标和 trace 只在内存里。
- trace id 没有真正贯穿 HTTP 请求、Agent、LLM、MCP、外部 API。
- 指标命名还没有对齐行业标准。
- 没有 eval 指标，无法判断“计划质量”是否提升。

#### 新技术方向

建议逐步接入 OpenTelemetry，并对齐 GenAI semantic conventions。OpenTelemetry 官方已经提供 GenAI 相关 signals，包括 events、exceptions、metrics、model spans、agent spans，并列出 OpenAI、MCP 等技术相关语义约定。

#### 优化建议

- 每个 `/api/plan` 生成一个全链路 trace id。
- span 分层：
  - HTTP request
  - harness validation
  - agent node
  - LLM call
  - MCP tool call
  - external API call
  - schema validation
  - session save
- 导出到 Jaeger/Tempo/Zipkin 或 OpenTelemetry Collector。
- 指标增加业务质量：
  - plan_json_valid_rate
  - plan_repair_rate
  - route_feasible_rate
  - user_modify_rate
  - first_plan_accept_rate
  - average_tool_calls_per_plan
  - external_api_failure_rate
  - cost_per_successful_plan
- 对失败计划做自动回放和 eval。

### 3.11 前端产品体验

#### 当前情况

前端有规划表单、结果页、地图、预算、天气、每日行程、智能修改、手动编辑入口和可观测面板。

#### 主要问题

- 手动编辑只是直接改 props 中的对象，没有保存到后端。
- 导出图片/PDF 是占位。
- 地图展示的是景点连线，不是真实路线。
- 没有规划进度流。
- 没有 A/B 方案选择。
- 长期记忆对用户不可见。

#### 优化建议

- 结果页增加“版本历史”和“撤销/恢复”。
- 手动编辑保存到 `/api/session/{id}/revision`。
- 支持拖拽调整景点顺序，并触发路线、预算重新计算。
- 导出 PDF、图片、Markdown 和分享链接。
- 地图展示真实路线段、距离、交通耗时。
- 加入“为什么这样安排”的解释面板。
- 加入“雨天备选”“轻松版”“预算优先版”切换。
- 加入用户反馈：
  - 喜欢/不喜欢某景点。
  - 预算是否合理。
  - 路线是否太累。
  - 是否采纳方案。
- 可观测面板保留给开发/运维，不建议默认暴露给普通用户。

### 3.12 测试、评估与质量保障

#### 当前情况

`tests/` 下有 benchmark 和手动 session 测试，但自动化程度还不够。`tests/benchmark.py` 依赖真实 MCP/LLM 环境，mock_session 为 `None` 时很难稳定运行；`manual_test_session.py` 是手动脚本。

#### 优化建议

- 建立 mock MCP server：
  - 固定返回天气。
  - 固定返回 POI。
  - 固定返回酒店。
  - 固定返回路线。
- 建立契约测试：
  - 每个 MCP tool 的 input/output schema。
  - `TripPlan` schema。
  - `/api/plan` 和 `/api/modify` response contract。
- 建立 golden scenarios：
  - 北京三日历史文化。
  - 南京亲子两日。
  - 上海商务半日。
  - 成都美食三日。
  - 雨天备选。
  - 预算超限。
  - 景点关闭或工具失败。
- 建立 agent eval：
  - JSON 合法率。
  - 计划完整率。
  - 坐标真实率。
  - 每天景点数量合规率。
  - 路线总耗时合理率。
  - 用户偏好覆盖率。
  - 修改指令遵循率。
- 对外部 API 异常做 chaos tests：
  - 高德超时。
  - Unsplash 无结果。
  - LLM 空响应。
  - 工具返回脏数据。
  - JSON 解析失败。

### 3.13 部署与工程化

#### 当前情况

README 提供了本地启动方式。后端启动时直接拉起两个 MCP stdio 子进程，数据库默认 `sessions.db`。

#### 主要问题

- 环境变量、数据库路径、CORS、开发/生产开关没有集中配置。
- 后端启动依赖 MCP 子服务成功，缺少健康检查和部分降级。
- 没有 Docker、CI、数据库迁移、日志持久化。
- 前后端路径和 README 部分描述与当前文件树存在漂移。

#### 优化建议

- 增加 `app/config.py`，用 Pydantic Settings 管理配置。
- 增加健康检查：
  - `/health`
  - `/health/mcp`
  - `/health/external-services`
- MCP 子服务启动失败时允许部分功能降级。
- Docker Compose：
  - backend
  - frontend
  - postgres
  - redis
  - otel-collector
- CI：
  - Python import check
  - unit tests
  - frontend type check
  - schema contract test
  - mock end-to-end test
- 文档同步：
  - README 更新到当前 observability 和 docs/archive 结构。
  - 删除或说明旧文件引用。

## 4. 推荐技术路线

### 4.1 短期原则

不要一上来大重构。当前项目已经能跑通完整链路，最合理的是围绕“可靠性”和“业务闭环”做增量升级。

### 4.2 技术选型建议

| 环节 | 当前方案 | 推荐升级 | 原因 |
| --- | --- | --- | --- |
| Agent 编排 | 自研 `SimpleAgent` + `ParallelTripPlanner` | LangGraph 状态图 | 支持 checkpoint、恢复、分支、人审和更复杂的工作流 |
| 工具协议 | MCP tools | MCP tools + resources + prompts + elicitation | 更完整地利用 MCP 标准能力 |
| 工具结果 | 字符串 | structuredContent + outputSchema + Pydantic | 降低最终规划 hallucination |
| LLM 输出 | prompt 要求 JSON + 正则解析 | Structured Outputs / response_format + Pydantic 校验 | 提高结构化稳定性 |
| 观测 | 自定义内存 observer | OpenTelemetry + GenAI semconv | 标准化 trace、metrics、logs |
| 存储 | SQLite | 原型保留 SQLite，生产转 Postgres + Redis | 支持多用户、版本、缓存、审计 |
| 前端 | 单次生成 + 本地编辑 | 版本化编辑 + 进度流 + 方案对比 | 更接近真实旅行顾问体验 |
| 测试 | 手动脚本 | mock MCP + contract test + agent eval | 能持续判断质量是否提升 |

### 4.3 LangGraph 与 OpenAI Agents SDK 的取舍

建议不要把这两个看成互斥：

- 如果目标是多模型、多供应商、MCP 标准工具、强状态图控制，优先 LangGraph + MCP。
- 如果目标是 OpenAI-first，并希望更快获得 handoff、guardrail、trace、工具运行的一体化能力，可以评估 OpenAI Agents SDK。
- 当前项目已经有 MCP 和自研 FastAPI 业务层，最稳妥路径是先引入 LangGraph 管理状态和节点，再逐步替换自研 ReAct 循环。

## 5. 分阶段路线图

### 第一阶段：1 到 2 周，补可靠性

- 为 MCP 工具定义统一结构化返回。
- 给高德天气、POI、酒店、路线工具增加 output schema。
- 改造 `run_structured()`，支持 structured output 或修复型重试。
- 建立 mock MCP server 和 5 个 golden scenario。
- 手动编辑保存到后端，生成 plan revision。
- README 和架构文档同步当前文件结构。

### 第二阶段：2 到 4 周，补业务可行性

- 增加路线优化节点，使用高德 direction 工具计算真实距离和时间。
- 增加计划校验节点，检查日期、景点数、坐标、餐饮、预算和天气建议。
- 增加雨天备选和轻松版/标准版/紧凑版方案。
- 增加 SSE 规划进度。
- 图片结果缓存。
- 增加 `/health` 和外部服务健康检查。

### 第三阶段：1 到 2 个月，补 AgentOps 和产品闭环

- 引入 LangGraph 状态图，替换线性并行规划器。
- 引入 OpenTelemetry trace，打通 HTTP、Agent、LLM、MCP、外部 API。
- 建立 agent eval dashboard。
- 长期记忆支持查看、删除、确认和禁用。
- 支持 PDF/Markdown 导出和分享链接。
- 支持用户反馈进入偏好画像。

### 第四阶段：3 个月以上，形成商业化能力

- 接入更多旅行数据源：票务、酒店价格、交通时刻、开放时间、点评。
- 支持多人偏好协商。
- 支持动态重排：天气变更、景点关闭、时间不足。
- 支持订单/预订前的人审确认。
- 形成城市攻略知识库和个性化推荐模型。

## 6. 最高优先级的 10 个改动

1. 把 MCP 工具输出从字符串升级为结构化结果。
2. 给最终 `TripPlan` 增加结构化输出模式和修复型重试。
3. 增加计划校验器，避免无效日期、缺餐、坐标错误和预算不一致。
4. 使用真实路线距离和时间，而不是简单地图连线。
5. 手动编辑保存到后端，并建立计划版本。
6. 建立 mock MCP 和 golden scenario 自动化测试。
7. 对外部 API 增加缓存、超时、重试和熔断。
8. 引入全链路 trace id，后续对接 OpenTelemetry。
9. 把长期记忆做成用户可见、可删除、可确认。
10. 将线性编排逐步迁移到 LangGraph 状态图。

## 7. 参考资料

- [MCP Server Overview](https://modelcontextprotocol.io/specification/2025-06-18/server/index)
- [MCP Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- [MCP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [MCP Elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation)
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [OpenAI Agents SDK Guide](https://developers.openai.com/api/docs/guides/agents)
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI Agents SDK Guardrails](https://openai.github.io/openai-agents-python/guardrails/)
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

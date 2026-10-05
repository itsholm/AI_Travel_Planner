# 多轮对话功能说明

## 功能概述

系统已支持多轮对话功能，用户可以在生成初始行程后，通过自然语言持续修改和完善行程。

## 主要特性

### 1. 会话管理
- 每次初始规划自动生成 `session_id`
- 会话数据持久化存储（SQLite）
- 支持跨浏览器标签页的对话延续

### 2. 智能修改
- 基于"ReAct + 历史上下文"的智能修改
- 保持原有数据结构，只修改用户指定部分
- 自动重新计算预算

### 3. 对话历史
- 记录每次用户指令和助手回复
- 历史摘要压缩功能（每10条消息压缩）
- 显示最近3条对话记录

## 使用方法

### 初始规划
```python
# 用户填写表单，提交 POST /api/plan
{
  "city": "北京",
  "start_date": "2025-03-01",
  "end_date": "2025-03-03",
  ...
}
# 返回
{
  "plan": {...},
  "session_id": "abc123-def456"
}
```

### 多轮修改
```python
# 用户点击"智能修改"按钮
POST /api/modify
{
  "session_id": "abc123-def456",
  "instruction": "把第二天的景点换成天坛"
}

# 返回更新后的完整行程
{
  "plan": {...updated plan...},
  "session_id": "abc123-def456"
}
```

## API 文档

### 1. POST /api/plan - 创建新会话
- **请求**: TripRequest
- **响应**: TripPlan + session_id

### 2. POST /api/modify - 修改行程
- **请求**: ModifyRequest (session_id + instruction)
- **响应**: TripPlan + session_id

### 3. GET /api/session/{session_id} - 获取会话详情
- **响应**: Session 对象（包含历史消息）

### 4. DELETE /api/session/{session_id} - 删除会话
- **响应**: {success: true}

## 技术实现

### 1. 数据模型
```python
class Session:
    session_id: str                    # 会话ID
    user_request: TripRequest          # 初始请求
    current_plan: TripPlan            # 当前行程
    messages: List[ConversationMessage] # 对话历史
    summary: str                      # 历史摘要
    updated_at: str                   # 更新时间
```

### 2. 存储服务
- SQLite 数据库
- 自动建表
- JSON 序列化存储复杂数据

### 3. 上下文传递
- 修改时包含完整行程 JSON
- 历史摘要提示 LLM
- 保持数据结构一致性

## 用户体验

### 前端界面
- "🤖 智能修改" 按钮（需要会话ID）
- 修改对话框（示例提示）
- 对话历史显示

### 使用流程
1. 用户填写表单 → 生成初始行程
2. 点击"🤖 智能修改" → 输入修改要求
3. AI 基于历史修改 → 返回更新后行程
4. 可继续修改直到满意

## 示例对话

**用户**: 请为北京规划3天行程  
**AI**: 已生成北京3天行程...  
**用户**: 把第二天的景点换成天坛  
**AI**: 已将天坛添加到第二天行程...  
**用户**: 增加第三天的午餐预算到100元  
**AI**: 已调整第三天午餐预算...  

## 测试

运行测试脚本：
```bash
cd app
python test_session.py
```

## 注意事项

1. 每次修改都会返回完整的 TripPlan，前端需要处理更新
2. 对话历史会自动压缩，避免过载
3. 会话数据长期保留，可定期清理旧数据
4. 修改功能依赖于 LLM 的理解能力，可能需要多次调整
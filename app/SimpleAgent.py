#-----------Agent基类------------#
#==============维护ReAct循环主逻辑，组装上下文、调用llm、执行工具并记录结果=====================
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field,ValidationError
from typing import List, Optional, Any,Literal,TypeVar,Type,Dict
from llm_client import HelloAgentLLM
from tools.registry import ToolRegistry # 假设你把新代码存在了 tools/registry.py
import json
import re

T = TypeVar("T", bound=BaseModel)
class Message:
    """定义统一的消息格式"""
    def __init__(self, role: str, content: str, tool_calls: Optional[List] = None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（OpenAI API格式）"""
        return {
            "role": self.role,
            "content": self.content
        }

class Config:
    """Agent 配置类"""
    def __init__(self, temperature: float = 0.7, max_tokens: int = 4096):
        self.temperature = temperature
        self.max_tokens = max_tokens

class SimpleAgent(ABC):
    def __init__(
        self,
        name: str,
        llm: Any,  # 你的 LLM 客户端对象
        system_prompt: Optional[str] = None,
        config: Optional[Config] = None
    ):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt
        self.config = config or Config()
        self._history: List[Message] = []
        self._summary = ""      # 新增：存压缩摘要
        self.MAX_HISTORY = 6    # 新增：最多保留6条完整历史
        # --- 核心修改：使用注册表代替普通字典 ---
        self.tool_registry = ToolRegistry()
    
    async def add_tool(self, tool: Any):
        """通过注册表添加工具，支持异步展开"""
        await self.tool_registry.add_tool(tool)
        return self

    #管理对话历史，便于在多轮对话中保持上下文连贯，把本轮message加入历史
    def add_message(self, message: Message):
        self._history.append(message)

    def clear_history(self):
        self._history.clear()

    def load_context(self, messages: List[Message], summary: str = ""):
        """
        从外部加载对话历史和摘要

        Args:
            messages: 历史消息列表
            summary: 历史摘要
        """
        self._history = messages
        self._summary = summary

    #ReAct模式的主循环逻辑
    async def run(self, input_text: str, max_iterations:int = 5,**kwargs) -> str:
        """
        Agent 的核心运行逻辑：
        1. 组装消息上下文
        2. 调用 LLM
        3. 如果 LLM 要求调用工具，执行工具并再次调用 LLM
        """
        # 构造发送给 LLM 的消息列表
        messages = []
        system_content = self.system_prompt or ""
        
        # 添加历史记录
        # for m in self._history:
        #     messages.append({"role": m.role, "content": m.content})
        if self._summary:
            system_content += f"\n\n【历史背景】{self._summary}"
        if system_content:
            messages.append({"role": "system", "content": system_content})  # 只添加一次
  
        # 3. 只带最近6条完整历史
        for m in self._history[-self.MAX_HISTORY:]:
            messages.append(m.to_dict())

        # 添加当前用户输入
        messages.append({"role": "user", "content": input_text})
        self.add_message(Message(role="user", content=input_text))

        # 迭代循环（处理工具调用）
        current_iteration = 0
        while current_iteration < max_iterations:  # 限制最大思考深度，防止死循环

            current_iteration += 1
            #给LLM看每个工具的说明书，让LLM知道有什么工具，需要哪些参数
            #直接从注册表获取所有工具说明
            tool_schemas = self.tool_registry.get_all_tool_schemas() #tool_registry是一个batch，其中的列表包含了多个mcptool实例，通过类方法得到所有工具的说明书
            #tool_schemas = [t.to_dict() for t in self.tools.values()] if self.tools else None #之前的说明书实现在agent内部，现在解耦到注册表中实现。agent只需要接收写好的说明书
            
            # 调用 LLM 客户端，返回LLM的content和tools_call
            # 注意：这里需要根据你实际的 llm_client 接口调整
            response = await self.llm.generate_response(
                messages=messages, #包括上一轮模型的回复，工具调用结果
                tools=tool_schemas if tool_schemas else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )
            #print(f"LLM客户端解析后的内容:\ncontent:{response.content}\ntools_call{response.tool_calls}")
            #发送给LLM的messages中，openai要校验'tool'都必须对应前一条 assistant 消息中的一个 tool_call ID

            # 2. 【核心修正】构造并添加 assistant 消息字典
            assistant_msg = {
                "role": "assistant",
                "content": response.content or ""
            }
            # 必须把完整的 tool_calls 列表放回去，LLM 才能对齐 ID
            if response.tool_calls:
                # 注意：这里需要将你的 ToolCall 对象转换回 OpenAI 期望的 dict 格式
                # 或者确保 llm_client 返回的是符合标准的结构
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": json.dumps(tc.function.arguments) if isinstance(tc.function.arguments, dict) else tc.function.arguments
                        }
                    } for tc in response.tool_calls
                ]

            # 记录回复
            self.add_message(Message(role="assistant", content=response.content, tool_calls=response.tool_calls)) #LLM回复加入历史消息
            messages.append(assistant_msg) #assistant只加入LLM回复的内容，没有加入tool_call ID

            # 如果没有工具调用需求，直接结束返回
            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                return response.content #最终回复

            # llm_client已经将LLM的返回解析为JSON格式并存为tool_calls列表
            # agent解析LLM调用的工具 遍历每个tool_call执行工具
            # 工具类变得更通用，GitHubMCPTool 或 GoogleSearchTool的接口是一样的
            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                # 从注册表检索对应的工具对象
                tool_obj = self.tool_registry.get_tool(tool_name)
                
                if tool_obj:
                    observation = await tool_obj.run(**tool_call.function.arguments)
                    print(f"  > 工具返回结果摘要: {str(observation)[:50]}...") # 新增：确认工具结果
                    #等于调用 bridge_tool.run(**tool_args) 是异步的，需要await
                    #print(f"  > Agent [{self.name}] 正在调用工具: {tool_name}")
                    #observation = await self.tools[tool_name].run(**tool_args) #Bridge 对象调用 session.call_tool，通过标准输入输出 (Stdio) 将指令发送给高德 MCP 服务。
                    # 将工具结果反馈给 LLM
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(observation)
                    }
                    #在 OpenAI 的协议中，tool 角色的消息不能孤立存在，它必须紧跟在一个带有 tool_calls 列表的 assistant 消息之后。
                    messages.append(tool_msg) #工具调用结果
                    self.add_message(Message(role="tool", content=str(observation))) #加入历史,没有把 tool_call_id 存进去
            
            #print(f"message列表:{messages}")
            # 4. 历史超过阈值时，压缩旧历史为摘要
        if len(self._history) > self.MAX_HISTORY:
            await self._compress_history()
        
        return "达到最大迭代次数，未能完成任务。"

    async def run_with_memory(self, input_text: str, max_iterations: int = 5) -> str:
        """
        带记忆的运行（复用已加载的历史）

        Args:
            input_text: 用户输入
            max_iterations: 最大迭代次数

        Returns:
            LLM 回复内容
        """
        # 构造发送给 LLM 的消息列表
        messages = []
        system_content = self.system_prompt or ""

        # 添加历史摘要
        if self._summary:
            system_content += f"\n\n【历史背景】{self._summary}"
        messages.append({"role": "system", "content": system_content})

        # 只带最近的历史消息
        for m in self._history[-self.MAX_HISTORY:]:
            messages.append(m.to_dict())

        # 添加当前用户输入
        messages.append({"role": "user", "content": input_text})
        self.add_message(Message(role="user", content=input_text))

        # 迭代循环（处理工具调用）
        current_iteration = 0
        while current_iteration < max_iterations:
            current_iteration += 1

            # 获取工具说明
            tool_schemas = self.tool_registry.get_all_tool_schemas()

            # 调用 LLM
            response = await self.llm.generate_response(
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )

            # 构造 assistant 消息
            assistant_msg = {
                "role": "assistant",
                "content": response.content or ""
            }
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": json.dumps(tc.function.arguments) if isinstance(tc.function.arguments, dict) else tc.function.arguments
                        }
                    } for tc in response.tool_calls
                ]

            # 记录回复
            self.add_message(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            messages.append(assistant_msg)

            # 如果没有工具调用需求，直接结束
            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                return response.content

            # 执行工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call.function.name
                tool_obj = self.tool_registry.get_tool(tool_name)

                if tool_obj:
                    observation = await tool_obj.run(**tool_call.function.arguments)
                    print(f"  > 工具返回结果摘要: {str(observation)[:50]}...")

                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": str(observation)
                    }
                    messages.append(tool_msg)
                    self.add_message(Message(role="tool", content=str(observation)))

        # 历史超过阈值时压缩
        if len(self._history) > self.MAX_HISTORY:
            await self._compress_history()

        return "达到最大迭代次数，未能完成任务。"

    async def run_structured(self, user_query: str, response_model: Type[T]) -> T:
        """
        1. 运行 ReAct 逻辑获取最终答案
        2. 强制解析答案为 Pydantic 模型
        """
        # 告知 LLM 必须返回 JSON 格式
        schema_json = json.dumps(response_model.model_json_schema(), ensure_ascii=False)#Pydantic模型会递归解析所有嵌套字段，生成完整的结构化Schema
        structured_query = (f"{user_query}\n\n"
            f"请严格按照以下 JSON Schema 格式回复，不要包含任何 Markdown 标签或解释文字：\n"
            f"{schema_json}"
        )
        raw_response = await self.run(structured_query) 
        
        # 清洗 Markdown 标签 (如果有)
        clean_json = raw_response.strip()
        json_match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if json_match:
            clean_json = json_match.group(0)
        else:
            clean_json = raw_response.strip()
        print(clean_json)
        
        #if "```" in clean_json:
        #    clean_json = re.sub(r'```json\s*|\s*```', '', clean_json).strip()
        
        try:
            data = json.loads(clean_json,strict=False)
            return response_model.model_validate(data)#LLM返回JSON后，Pydantic会递归验证每个字段类型，自动转换类型并抛出明确的验证错误
        except ValidationError as e:
            print(f"解析失败: {e}，原始回复: {raw_response}")
            raise ValueError("AI 返回的格式不符合预期模型")

    def __str__(self) -> str:
        return f"Agent(name={self.name})"
    
    async def _compress_history(self):
        """把旧历史压缩成摘要"""
        old_messages = self._history[:-self.MAX_HISTORY]
        compress_prompt = (
            f"请将以下对话历史压缩成一段简洁的背景摘要（100字以内）：\n"
            f"{[m.to_dict() for m in old_messages]}"
        )
        response = await self.llm.generate_response(
            messages=[{"role": "user", "content": compress_prompt}]
        )
        self._summary = response.content
        # 只保留最近的历史
        self._history = self._history[-self.MAX_HISTORY:]
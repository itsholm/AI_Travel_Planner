#=------------封装LLM调用函数------------=#
import os
import json
import logging
import time
from openai import AsyncOpenAI
from observability.execution_context import record_usage
from dotenv import load_dotenv
#import traceback
load_dotenv()

#暴露参数包括messages、tools等
logger = logging.getLogger(__name__)

# 定义响应结构（模拟 OpenAI 的 message 对象）
class FunctionCall:
    def __init__(self, name: str, arguments: dict):
        self.name = name
        self.arguments = arguments  # 注意：是 dict，不是字符串

class ToolCall:
    def __init__(self, id: str, function: FunctionCall):
        self.id = id
        self.function = function

class LLMMessage:
    def __init__(self, content: str, tool_calls: list = None, usage: dict = None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage = usage or {}


class HelloAgentLLM:
    def __init__(self,model:str=None,apiKey:str=None,baseUrl:str=None):
        self.model = model or os.getenv("LLM_MODEL_ID")
        apiKey = apiKey or os.getenv("LLM_API_KEY")
        baseUrl = baseUrl or os.getenv("LLM_BASE_URL")

        if not self.model or not apiKey or not baseUrl:
            logger.error("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")
            raise ValueError("模型ID、API密钥和服务地址必须被提供或在.env文件中定义。")

        self.client = AsyncOpenAI(api_key=apiKey,base_url=baseUrl)

    async def generate_response(self,
    messages:list[dict[str,str]], tools: list[dict] = None,max_tokens:int=4096,temperature:float=0.7):
        logger.debug(f"调用LLM模型: {self.model}, max_tokens={max_tokens}, temperature={temperature}")
        start_time = time.time()
        try:
            from observability import EventType, observer
            observer.record_event(EventType.LLM_CALL_START, { #记录一次事件，哪个模型、有没有用工具、prompt消息由多少条
                "model": self.model,
                "message_count": len(messages),
                "tools_enabled": bool(tools),
                "max_tokens": max_tokens,
                "temperature": temperature,
            })
        except ImportError:
            pass

        try:
            # 构建请求参数
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                #"extra_body":{"enable_thinking": False}
            }

            # 如果提供了 tools，则加入请求，让llm知道有什么工具，以及其数据格式
            if tools:
                params["tools"] = tools
                params["tool_choice"] = "auto"  # 让模型自主决定是否调用工具

            response = await self.client.chat.completions.create(**params)
            message = response.choices[0].message
            #print(f"LLM返回的原始内容:{message}\n")

            # 提取文本内容（可能为 None，比如纯工具调用时）,如何确保提取的内容是纯文本的？
            content = (message.content or "").strip()

            #解析LLM中工具调用，返回成agent接受的格式
            tool_calls=[]
            if hasattr(message,'tool_calls') and message.tool_calls:
                for tc in message.tool_calls:
                    func_name = tc.function.name
                    try:
                        # OpenAI 返回的是 JSON 字符串，需解析为 dict
                        func_args = json.loads(tc.function.arguments)
                    except(json.JSONDecodeError,TypeError):
                        logger.warning(f"工具参数解析失败: {tc.function.arguments}")
                        func_args={}
                    function_call=FunctionCall(name=func_name,arguments=func_args)
                    tool_call = ToolCall(id=tc.id,function=function_call)
                    tool_calls.append(tool_call)

            # 记录Token使用情况
            usage = response.usage
            input_tokens = usage.prompt_tokens if hasattr(usage, 'prompt_tokens') else 0
            output_tokens = usage.completion_tokens if hasattr(usage, 'completion_tokens') else 0
            total_tokens = usage.total_tokens if hasattr(usage, 'total_tokens') else 0
            record_usage(input_tokens, output_tokens, total_tokens)
            duration = time.time() - start_time
            
            # 导入可观测性模块，写入成功指标
            try:
                from observability import EventType, observer
                tags = {"model": self.model}
                observer.record_counter("llm_calls_total", 1, tags)
                observer.record_counter("input_tokens_total", input_tokens, {"model": self.model})
                observer.record_counter("output_tokens_total", output_tokens, {"model": self.model})
                observer.record_counter("tokens_total", total_tokens, {"model": self.model})
                observer.record_histogram("llm_call_duration", duration, tags)
                observer.record_histogram("llm_tool_call_count", len(tool_calls), tags)
                if not content and not tool_calls:
                    observer.record_counter("llm_empty_response_total", 1, tags)
                observer.record_event(EventType.LLM_CALL_END, {
                    "model": self.model,
                    "duration": duration,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "tool_call_count": len(tool_calls),
                    "success": True,
                })
            except ImportError:
                pass
            
            print("调用LLM模型成功")
            logger.info(f"LLM模型调用成功，输入Token: {input_tokens}, 输出Token: {output_tokens}, 总Token: {total_tokens}")
            return LLMMessage(content=content, tool_calls=tool_calls, usage={"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens})  # 去除首尾空格
        except Exception as e:
            duration = time.time() - start_time
            try:
                from observability import EventType, observer
                tags = {"model": self.model, "error_type": type(e).__name__}
                observer.record_counter("llm_errors_total", 1, tags)
                observer.record_histogram("llm_call_duration", duration, {"model": self.model})
                observer.record_event(EventType.LLM_CALL_END, {
                    "model": self.model,
                    "duration": duration,
                    "success": False,
                    "error_type": type(e).__name__,
                    "error": str(e),
                })
            except ImportError:
                pass
            print(f"调用LLM模型失败: {e}")
            #traceback.print_exc()  # 打印完整错误堆栈，这能告诉我到底是什么问题
            logger.error(f"调用LLM模型失败: {e}", exc_info=True)
            # exc_info=True 会记录完整的异常堆栈信息
            raise

# #----测试----#
# if __name__ == "__main__":
#     llm = HelloAgentLLM() #实例化类
#     messages = [
#         {"role":"system","content":"你是一个助手，回答用户的问题。"},
#         {"role":"user","content":"你好，你是谁？"}
#     ]
#     response = llm.generate_response(messages)
#     print(response)

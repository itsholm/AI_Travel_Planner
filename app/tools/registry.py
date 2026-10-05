#注册表不再仅仅是字典，它具备了处理异步展开和统一导出 Schema 的能力。
from typing import Optional, Dict, List, Any

class ToolRegistry:
    """工具注册表：负责工具的生命周期和格式转换"""
    def __init__(self):
        self._tools: Dict[str, Any] = {}

    async def add_tool(self, tool: Any): #tool是一个batch对象
        """添加工具：如果是 MCP 批处理对象，则自动展开"""
        if hasattr(tool, 'auto_expand') and tool.auto_expand:#如果有这个字段且为true
            expanded_tools = await tool.get_expanded_tools() #batch的异步方法，从会话的MCP服务端拉取所有工具并注册为mcptools实例对象
            for et in expanded_tools:
                self.register_single_tool(et) #对于每一个mcptool，添加到注册表中。每一个mcptool
            print(f"已从 MCP 服务端自动加载 {len(expanded_tools)} 个工具")
        else:
            self.register_single_tool(tool)

    def register_single_tool(self, tool: Any):
        """注册单个工具"""
        if hasattr(tool, 'name'):
            self._tools[tool.name] = tool
            print(f"工具 '{tool.name}' 注册成功")

    def get_tool(self, name: str) -> Optional[Any]:
        """根据名称获取工具实例"""
        return self._tools.get(name)

    def get_all_tool_schemas(self) -> List[Dict]:#需要给LLM看，所以要转换成dict格式
        """汇总所有工具的 OpenAI 格式说明书"""
        return [t.to_dict() for t in self._tools.values()]

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())



# app/skills/weather_skill.py
from typing import Dict, Any, Optional
from amap_mcp import AmapMCPTool

class WeatherSkill:
    """天气查询Skill"""
    
    def __init__(self, mcp_tool: AmapMCPTool):
        """
        初始化天气Skill
        
        Args:
            mcp_tool: 底层MCP工具实例
        """
        self.mcp_tool = mcp_tool
        self.name = "get_weather"
        self.description = "获取指定城市的天气信息，包括温度、天气状况和风力等"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        转换为OpenAI工具格式
        
        Returns:
            工具说明的字典
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称，如：北京、上海、广州等"
                        },
                        "start_date": {
                            "type": "string",
                            "description": "开始日期，格式：YYYY-MM-DD"
                        },
                        "end_date": {
                            "type": "string",
                            "description": "结束日期，格式：YYYY-MM-DD"
                        }
                    },
                    "required": ["city", "start_date", "end_date"]
                }
            }
        }
    
    async def run(self, city: str, start_date: str, end_date: str) -> str:
        """
        执行天气查询
        
        Args:
            city: 城市名称
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            天气信息的字符串
        """
        try:
            # 构建查询参数
            query = f"查询{city}在 {start_date} 到{end_date}期间的天气预报"
            
            # 调用底层MCP工具
            result = await self.mcp_tool.run(query=query)
            
            # 处理结果
            if result:
                return self._format_weather_result(result, city, start_date, end_date)
            else:
                return f"无法获取{city}的天气信息"
        
        except Exception as e:
            return f"天气查询失败: {str(e)}"
    
    def _format_weather_result(self, weather_data: str, city: str, start_date: str, end_date: str) -> str:
        """
        格式化天气结果
        
        Args:
            weather_data: 原始天气数据
            city: 城市名称
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            格式化后的天气信息
        """
        # 这里可以根据实际返回的数据格式进行更复杂的处理
        return f"{city}从{start_date}到{end_date}的天气情况：\n{weather_data}"
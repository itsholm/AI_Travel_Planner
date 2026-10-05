# app/skills/skill_registry.py
from typing import Dict, List, Any
from tools.registry import ToolRegistry

class SkillRegistry:
    """Skill注册器"""
    
    def __init__(self):
        self._skills: Dict[str, Any] = {}
        self.tool_registry = ToolRegistry()
    
    async def add_skill(self, skill: Any):
        """
        添加Skill
        
        Args:
            skill: Skill实例
        """
        self._skills[skill.name] = skill
        # 同时添加到工具注册表
        await self.tool_registry.add_tool(skill)
        print(f"Skill '{skill.name}' 注册成功")
    
    def get_skill(self, name: str) -> Any:
        """
        根据名称获取Skill
        
        Args:
            name: Skill名称
        
        Returns:
            Skill实例
        """
        return self._skills.get(name)
    
    def get_all_skill_schemas(self) -> List[Dict]:
        """
        获取所有Skill的说明
        
        Returns:
            Skill说明列表
        """
        return [skill.to_dict() for skill in self._skills.values()]
    
    def list_skills(self) -> List[str]:
        """
        列出所有Skill名称
        
        Returns:
            Skill名称列表
        """
        return list(self._skills.keys())
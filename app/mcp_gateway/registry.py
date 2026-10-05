from typing import Any, Dict, List, Optional

from models.schemas import ToolRiskLevel, ToolSpec


class GatewayToolRegistry:
    """Registry enriched with reliability and risk metadata."""

    def __init__(self):
        self._tools: Dict[str, Any] = {}
        self._specs: Dict[str, ToolSpec] = {}

    def register_tool(
        self,
        tool: Any,
        *,
        server: str = "local",
        risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
        required_scope: str = "travel:read",
        side_effect: bool = False,
        timeout_ms: int = 10000,
        max_retries: int = 2,
        cache_ttl: Optional[int] = None,
    ):
        if not hasattr(tool, "name"):
            raise ValueError("Tool must expose a name attribute")

        input_schema = getattr(tool, "input_schema", {}) or {}
        description = getattr(tool, "description", "") or ""
        spec = ToolSpec(
            name=tool.name,
            server=server,
            description=description,
            input_schema=input_schema,
            risk_level=risk_level,
            required_scope=required_scope,
            side_effect=side_effect,
            timeout_ms=timeout_ms,
            max_retries=max_retries,
            cache_ttl=cache_ttl,
        )
        self._tools[tool.name] = tool
        self._specs[tool.name] = spec

    def get_tool(self, name: str) -> Optional[Any]:
        return self._tools.get(name)

    def get_spec(self, name: str) -> Optional[ToolSpec]:
        return self._specs.get(name)

    def list_specs(self) -> List[ToolSpec]:
        return list(self._specs.values())

    def to_openai_tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.input_schema,
                },
            }
            for spec in self._specs.values()
        ]

import asyncio
import hashlib
import json
import uuid
from typing import Any, Dict, Optional

from mcp_gateway.registry import GatewayToolRegistry
from models.schemas import ToolCallRecord, ToolCallStatus
from services.task_store import TaskStore


class ToolGateway:
    """Single execution path for tool calls, including retries and idempotency."""

    def __init__(self, registry: GatewayToolRegistry, store: TaskStore):
        self.registry = registry
        self.store = store

    async def execute(
        self,
        *,
        task_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> ToolCallRecord:
        spec = self.registry.get_spec(tool_name)
        tool = self.registry.get_tool(tool_name)
        if not spec or not tool:
            raise ValueError(f"Tool not registered: {tool_name}")

        if idempotency_key:
            previous = self.store.get_tool_call_by_idempotency(idempotency_key)
            if previous and previous.status == ToolCallStatus.SUCCESS:
                self.store.append_event(
                    task_id,
                    "tool.idempotent_replay",
                    {"tool_name": tool_name, "call_id": previous.call_id},
                )
                return previous
        else:
            previous = None

        record = ToolCallRecord(
            call_id=previous.call_id if previous else str(uuid.uuid4()),
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            args_hash=self._hash_args(arguments),
            idempotency_key=idempotency_key or "",
            risk_level=spec.risk_level,
            side_effect=spec.side_effect,
            status=ToolCallStatus.RUNNING,
            created_at=previous.created_at if previous else "",
        )
        self.store.upsert_tool_call(record)
        self.store.append_event(
            task_id,
            "tool.started",
            {"tool_name": tool_name, "call_id": record.call_id, "risk": spec.risk_level.value},
        )

        max_attempts = max(1, spec.max_retries + 1)
        for attempt in range(max_attempts):
            try:
                result = await asyncio.wait_for(
                    tool.run(**arguments),
                    timeout=spec.timeout_ms / 1000,
                )
                record.status = ToolCallStatus.SUCCESS
                record.result = self._normalize_result(result)
                record.error = None
                record.retry_count = attempt
                self.store.upsert_tool_call(record)
                self.store.append_event(
                    task_id,
                    "tool.completed",
                    {
                        "tool_name": tool_name,
                        "call_id": record.call_id,
                        "status": record.status.value,
                        "retry_count": record.retry_count,
                    },
                )
                return record
            except Exception as exc:
                record.retry_count = attempt
                record.error = str(exc)
                if attempt < max_attempts - 1:
                    self.store.append_event(
                        task_id,
                        "tool.retrying",
                        {
                            "tool_name": tool_name,
                            "call_id": record.call_id,
                            "attempt": attempt + 1,
                            "error": str(exc),
                        },
                    )
                    await asyncio.sleep(min(2 ** attempt, 4))
                    continue

                record.status = ToolCallStatus.FAILED
                self.store.upsert_tool_call(record)
                self.store.append_event(
                    task_id,
                    "tool.failed",
                    {"tool_name": tool_name, "call_id": record.call_id, "error": str(exc)},
                )
                return record

    def _hash_args(self, arguments: Dict[str, Any]) -> str:
        raw = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _normalize_result(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return {"text": str(result)}

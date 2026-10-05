import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from models.schemas import (
    Approval,
    ApprovalDecision,
    BusinessTripRequest,
    BusinessTripTask,
    Checkpoint,
    TaskEvent,
    TaskState,
    ToolCallRecord,
    ToolCallStatus,
    ToolRiskLevel,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    """SQLite-backed fact store for durable Agent task execution."""

    task_model = BusinessTripTask
    request_model = BusinessTripRequest

    def __init__(self, db_path: str = "tasks.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                user_id TEXT,
                goal TEXT,
                request_json TEXT NOT NULL,
                state TEXT NOT NULL,
                current_step TEXT,
                result_json TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS task_events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                step TEXT NOT NULL,
                state TEXT NOT NULL,
                state_json TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tool_calls (
                call_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                args_hash TEXT,
                idempotency_key TEXT,
                risk_level TEXT NOT NULL,
                side_effect INTEGER NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error TEXT,
                retry_count INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_tool_calls_idempotency
            ON tool_calls(idempotency_key)
            WHERE idempotency_key IS NOT NULL AND idempotency_key != '';

            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                call_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                action TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                preview_json TEXT NOT NULL,
                decision TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                expires_at TEXT
            );
            """
        )
        self.conn.commit()

    def create_task(
        self,
        request: BusinessTripRequest,
        goal: str,
        user_id: str = "demo-user",
    ) -> BusinessTripTask:
        now = utc_now()
        task = self.task_model(
            task_id=str(uuid.uuid4()),
            user_id=user_id,
            goal=goal,
            request=request,
            state=TaskState.CREATED,
            current_step="created",
            created_at=now,
            updated_at=now,
        )
        self.conn.execute(
            """
            INSERT INTO tasks
            (task_id, user_id, goal, request_json, state, current_step, result_json, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.task_id,
                task.user_id,
                task.goal,
                task.request.model_dump_json(),
                task.state.value,
                task.current_step,
                None,
                None,
                task.created_at,
                task.updated_at,
            ),
        )
        self.conn.commit()
        return task

    def get_task(self, task_id: str) -> Optional[BusinessTripTask]:
        row = self.conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def update_task(
        self,
        task_id: str,
        state: Optional[TaskState] = None,
        current_step: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[BusinessTripTask]:
        task = self.get_task(task_id)
        if not task:
            return None
        new_state = state or task.state
        new_step = current_step if current_step is not None else task.current_step
        result_json = json.dumps(result, ensure_ascii=False) if result is not None else (
            json.dumps(task.result, ensure_ascii=False) if task.result is not None else None
        )
        new_error = error if error is not None else task.error
        now = utc_now()
        self.conn.execute(
            """
            UPDATE tasks
            SET state = ?, current_step = ?, result_json = ?, error = ?, updated_at = ?
            WHERE task_id = ?
            """,
            (new_state.value, new_step, result_json, new_error, now, task_id),
        )
        self.conn.commit()
        return self.get_task(task_id)

    def append_event(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> TaskEvent:
        event = TaskEvent(
            event_id=str(uuid.uuid4()),
            task_id=task_id,
            event_type=event_type,
            payload=payload,
            created_at=utc_now(),
        )
        self.conn.execute(
            """
            INSERT INTO task_events (event_id, task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.task_id,
                event.event_type,
                json.dumps(event.payload, ensure_ascii=False),
                event.created_at,
            ),
        )
        self.conn.commit()
        return event

    def list_events(self, task_id: str, after_event_id: Optional[str] = None) -> List[TaskEvent]:
        if after_event_id:
            anchor = self.conn.execute(
                "SELECT created_at FROM task_events WHERE event_id = ?",
                (after_event_id,),
            ).fetchone()
            if not anchor:
                return []
            rows = self.conn.execute(
                """
                SELECT * FROM task_events
                WHERE task_id = ? AND created_at > ?
                ORDER BY created_at ASC
                """,
                (task_id, anchor["created_at"]),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def save_checkpoint(
        self,
        task_id: str,
        step: str,
        state: TaskState,
        state_json: Dict[str, Any],
    ) -> Checkpoint:
        latest = self.get_latest_checkpoint(task_id)
        version = (latest.version + 1) if latest else 1
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            task_id=task_id,
            step=step,
            state=state,
            state_json=state_json,
            version=version,
            created_at=utc_now(),
        )
        self.conn.execute(
            """
            INSERT INTO checkpoints (checkpoint_id, task_id, step, state, state_json, version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint.checkpoint_id,
                checkpoint.task_id,
                checkpoint.step,
                checkpoint.state.value,
                json.dumps(checkpoint.state_json, ensure_ascii=False),
                checkpoint.version,
                checkpoint.created_at,
            ),
        )
        self.conn.commit()
        return checkpoint

    def get_latest_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        row = self.conn.execute(
            """
            SELECT * FROM checkpoints
            WHERE task_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
        return self._row_to_checkpoint(row) if row else None

    def upsert_tool_call(self, record: ToolCallRecord) -> ToolCallRecord:
        now = utc_now()
        if not record.created_at:
            record.created_at = now
        record.updated_at = now
        self.conn.execute(
            """
            INSERT INTO tool_calls
            (call_id, task_id, tool_name, arguments_json, args_hash, idempotency_key, risk_level,
             side_effect, status, result_json, error, retry_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(call_id) DO UPDATE SET
                status = excluded.status,
                result_json = excluded.result_json,
                error = excluded.error,
                retry_count = excluded.retry_count,
                updated_at = excluded.updated_at
            """,
            (
                record.call_id,
                record.task_id,
                record.tool_name,
                json.dumps(record.arguments, ensure_ascii=False),
                record.args_hash,
                record.idempotency_key,
                record.risk_level.value,
                1 if record.side_effect else 0,
                record.status.value,
                json.dumps(record.result, ensure_ascii=False) if record.result is not None else None,
                record.error,
                record.retry_count,
                record.created_at,
                record.updated_at,
            ),
        )
        self.conn.commit()
        return record

    def get_tool_call_by_idempotency(self, idempotency_key: str) -> Optional[ToolCallRecord]:
        row = self.conn.execute(
            "SELECT * FROM tool_calls WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return self._row_to_tool_call(row) if row else None

    def get_tool_call(self, call_id: str) -> Optional[ToolCallRecord]:
        row = self.conn.execute("SELECT * FROM tool_calls WHERE call_id = ?", (call_id,)).fetchone()
        return self._row_to_tool_call(row) if row else None

    def list_tool_calls(self, task_id: str) -> List[ToolCallRecord]:
        rows = self.conn.execute(
            "SELECT * FROM tool_calls WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [self._row_to_tool_call(row) for row in rows]

    def create_approval(
        self,
        task_id: str,
        call_id: str,
        tool_name: str,
        action: str,
        risk_level: ToolRiskLevel,
        preview: Dict[str, Any],
        expires_at: Optional[str] = None,
    ) -> Approval:
        approval = Approval(
            approval_id=str(uuid.uuid4()),
            task_id=task_id,
            call_id=call_id,
            tool_name=tool_name,
            action=action,
            risk_level=risk_level,
            preview=preview,
            decision=ApprovalDecision.PENDING,
            created_at=utc_now(),
            expires_at=expires_at,
        )
        self.conn.execute(
            """
            INSERT INTO approvals
            (approval_id, task_id, call_id, tool_name, action, risk_level, preview_json,
             decision, created_at, decided_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval.approval_id,
                approval.task_id,
                approval.call_id,
                approval.tool_name,
                approval.action,
                approval.risk_level.value,
                json.dumps(approval.preview, ensure_ascii=False),
                approval.decision.value,
                approval.created_at,
                approval.decided_at,
                approval.expires_at,
            ),
        )
        self.conn.commit()
        return approval

    def get_approval(self, approval_id: str) -> Optional[Approval]:
        row = self.conn.execute(
            "SELECT * FROM approvals WHERE approval_id = ?",
            (approval_id,),
        ).fetchone()
        return self._row_to_approval(row) if row else None

    def get_pending_approval(self, task_id: str) -> Optional[Approval]:
        row = self.conn.execute(
            """
            SELECT * FROM approvals
            WHERE task_id = ? AND decision = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (task_id, ApprovalDecision.PENDING.value),
        ).fetchone()
        return self._row_to_approval(row) if row else None

    def decide_approval(self, approval_id: str, decision: ApprovalDecision) -> Optional[Approval]:
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        if approval.decision != ApprovalDecision.PENDING:
            return approval
        self.conn.execute(
            """
            UPDATE approvals
            SET decision = ?, decided_at = ?
            WHERE approval_id = ?
            """,
            (decision.value, utc_now(), approval_id),
        )
        self.conn.commit()
        return self.get_approval(approval_id)

    def close(self):
        if self.conn:
            self.conn.close()

    def _row_to_task(self, row: sqlite3.Row) -> BusinessTripTask:
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return self.task_model(
            task_id=row["task_id"],
            user_id=row["user_id"],
            goal=row["goal"],
            request=self.request_model.model_validate_json(row["request_json"]),
            state=TaskState(row["state"]),
            current_step=row["current_step"] or "",
            result=result,
            error=row["error"],
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    def _row_to_event(self, row: sqlite3.Row) -> TaskEvent:
        return TaskEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            event_type=row["event_type"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
        )

    def _row_to_checkpoint(self, row: sqlite3.Row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row["checkpoint_id"],
            task_id=row["task_id"],
            step=row["step"],
            state=TaskState(row["state"]),
            state_json=json.loads(row["state_json"]),
            version=row["version"],
            created_at=row["created_at"],
        )

    def _row_to_tool_call(self, row: sqlite3.Row) -> ToolCallRecord:
        result = json.loads(row["result_json"]) if row["result_json"] else None
        return ToolCallRecord(
            call_id=row["call_id"],
            task_id=row["task_id"],
            tool_name=row["tool_name"],
            arguments=json.loads(row["arguments_json"]),
            args_hash=row["args_hash"] or "",
            idempotency_key=row["idempotency_key"] or "",
            risk_level=ToolRiskLevel(row["risk_level"]),
            side_effect=bool(row["side_effect"]),
            status=ToolCallStatus(row["status"]),
            result=result,
            error=row["error"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_approval(self, row: sqlite3.Row) -> Approval:
        return Approval(
            approval_id=row["approval_id"],
            task_id=row["task_id"],
            call_id=row["call_id"],
            tool_name=row["tool_name"],
            action=row["action"],
            risk_level=ToolRiskLevel(row["risk_level"]),
            preview=json.loads(row["preview_json"]),
            decision=ApprovalDecision(row["decision"]),
            created_at=row["created_at"],
            decided_at=row["decided_at"],
            expires_at=row["expires_at"],
        )


_task_store = None


def get_task_store(db_path: str = None) -> TaskStore:
    global _task_store
    if _task_store is None:
        _task_store = TaskStore(db_path or "tasks.db")
    return _task_store

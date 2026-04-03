# 会话存储服务 - 支持多轮对话的持久化
import sqlite3
import json
import os
from datetime import datetime
from typing import Optional
from models.schemas import Session, TripRequest, TripPlan, ConversationMessage


class SessionStore:
    """会话存储管理器，使用 SQLite 持久化对话历史"""

    def __init__(self, db_path: str = "sessions.db"):
        """初始化存储服务"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 允许通过列名访问
        self._init_db()

    def _init_db(self):
        """初始化数据库表"""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_request TEXT,
                current_plan TEXT,
                messages TEXT,
                summary TEXT,
                updated_at TEXT
            )
        """)
        self.conn.commit()

    def save_session(self, session: Session) -> bool:
        """
        保存或更新会话

        Args:
            session: 会话对象

        Returns:
            是否保存成功
        """
        try:
            # 转换为 JSON 字符串存储
            user_request_json = (
                json.dumps(session.user_request.model_dump(), ensure_ascii=False)
                if session.user_request else None
            )
            current_plan_json = (
                json.dumps(session.current_plan.model_dump(), ensure_ascii=False)
                if session.current_plan else None
            )
            messages_json = json.dumps(
                [msg.model_dump() for msg in session.messages],
                ensure_ascii=False
            )

            updated_at = session.updated_at or datetime.now().isoformat()

            self.conn.execute("""
                INSERT OR REPLACE INTO sessions
                (session_id, user_request, current_plan, messages, summary, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session.session_id,
                user_request_json,
                current_plan_json,
                messages_json,
                session.summary,
                updated_at
            ))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"保存会话失败: {e}")
            return False

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        根据会话ID获取会话

        Args:
            session_id: 会话ID

        Returns:
            会话对象，不存在则返回 None
        """
        cursor = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        try:
            # 解析 JSON 数据
            user_request = None
            if row['user_request']:
                user_request = TripRequest.model_validate_json(row['user_request'])

            current_plan = None
            if row['current_plan']:
                current_plan = TripPlan.model_validate_json(row['current_plan'])

            messages = []
            if row['messages']:
                messages_data = json.loads(row['messages'])
                messages = [ConversationMessage.model_validate(msg) for msg in messages_data]

            return Session(
                session_id=row['session_id'],
                user_request=user_request,
                current_plan=current_plan,
                messages=messages,
                summary=row['summary'] or "",
                updated_at=row['updated_at'] or ""
            )
        except Exception as e:
            print(f"解析会话数据失败: {e}")
            return None

    def list_sessions(self, limit: int = 10) -> list:
        """
        列出最近的会话

        Args:
            limit: 返回数量限制

        Returns:
            会话ID和更新时间的列表
        """
        cursor = self.conn.execute("""
            SELECT session_id, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        return cursor.fetchall()

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        try:
            self.conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,)
            )
            self.conn.commit()
            return True
        except Exception as e:
            print(f"删除会话失败: {e}")
            return False

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()


# 全局单例
_session_store = None


def get_session_store(db_path: str = None) -> SessionStore:
    """获取全局会话存储单例"""
    global _session_store
    if _session_store is None:
        _session_store = SessionStore(db_path)
    return _session_store

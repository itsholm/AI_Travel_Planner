import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from models.schemas import TripRequest


class UserMemoryService:
    """管理长期结构化用户记忆，并提供规划提示词注入内容。"""

    def __init__(self, db_path: str = "sessions.db"):
        """初始化长期记忆存储。"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """初始化长期记忆表。"""
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_memory_profiles (
                user_id TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def get_profile(self, user_id: str = "default") -> Dict[str, Any]:
        """读取用户画像；不存在时返回空画像。"""
        row = self.conn.execute(
            "SELECT profile_json FROM user_memory_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not row:
            return self._empty_profile(user_id)

        try:
            profile = json.loads(row["profile_json"])
            return {**self._empty_profile(user_id), **profile}
        except json.JSONDecodeError:
            return self._empty_profile(user_id)

    def update_from_request(self, request: TripRequest, user_id: str = "default") -> Dict[str, Any]:
        """从一次成功规划请求中提取稳定偏好并更新用户画像。"""
        profile = self.get_profile(user_id)

        if request.transportation:
            profile["transportation_preference"] = request.transportation
        if request.accommodation:
            profile["accommodation_preference"] = request.accommodation

        self._append_unique(profile["preferred_cities"], request.city)
        for preference in request.preferences or []:
            self._append_unique(profile["interests"], preference)

        note = (request.free_text_input or "").strip()
        if note:
            self._append_unique(profile["notes"], note)
            profile["notes"] = profile["notes"][-10:]

        profile["updated_at"] = datetime.now().isoformat()
        self._save_profile(user_id, profile)
        return profile

    def build_memory_context(self, user_id: str = "default") -> str:
        """构建可注入 LLM 提示词的长期记忆上下文。"""
        profile = self.get_profile(user_id)
        lines: List[str] = []

        if profile["transportation_preference"]:
            lines.append(f"- 常用交通偏好: {profile['transportation_preference']}")
        if profile["accommodation_preference"]:
            lines.append(f"- 常用住宿偏好: {profile['accommodation_preference']}")
        if profile["interests"]:
            lines.append(f"- 兴趣偏好: {', '.join(profile['interests'])}")
        if profile["preferred_cities"]:
            lines.append(f"- 历史目的地: {', '.join(profile['preferred_cities'][-5:])}")
        if profile["notes"]:
            lines.append(f"- 其他长期偏好: {'; '.join(profile['notes'][-3:])}")

        if not lines:
            return ""

        return (
            "以下是用户长期结构化记忆。若与本次明确输入冲突，以本次输入为准：\n"
            + "\n".join(lines)
        )

    def reset_profile(self, user_id: str = "default") -> bool:
        """清空指定用户的长期记忆。"""
        cursor = self.conn.execute(
            "DELETE FROM user_memory_profiles WHERE user_id = ?",
            (user_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def close(self):
        """关闭长期记忆数据库连接。"""
        if self.conn:
            self.conn.close()

    def _save_profile(self, user_id: str, profile: Dict[str, Any]):
        """保存用户画像。"""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO user_memory_profiles (user_id, profile_json, updated_at)
            VALUES (?, ?, ?)
            """,
            (
                user_id,
                json.dumps(profile, ensure_ascii=False),
                profile["updated_at"],
            ),
        )
        self.conn.commit()

    @staticmethod
    def _append_unique(values: List[str], value: str):
        """按顺序追加非空且未出现过的值。"""
        value = (value or "").strip()
        if value and value not in values:
            values.append(value)

    @staticmethod
    def _empty_profile(user_id: str) -> Dict[str, Any]:
        """创建空用户画像。"""
        return {
            "user_id": user_id,
            "transportation_preference": "",
            "accommodation_preference": "",
            "interests": [],
            "preferred_cities": [],
            "notes": [],
            "updated_at": "",
        }


_user_memory_service = None


def get_user_memory_service(db_path: str = "sessions.db") -> UserMemoryService:
    """获取长期记忆服务单例。"""
    global _user_memory_service
    if _user_memory_service is None:
        _user_memory_service = UserMemoryService(db_path)
    return _user_memory_service

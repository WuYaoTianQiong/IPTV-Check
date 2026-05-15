import os
import json
import time
import logging
import asyncio
from typing import Optional, Any, List
from datetime import datetime

from sqlmodel import SQLModel, Field, create_engine, Session, select
from sqlalchemy import Index, func, text as sa_text

logger = logging.getLogger(__name__)


class CheckEventBase(SQLModel):
    event_type: str = Field(index=True)
    payload: str = Field(default="{}")
    session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class CheckEventModel(CheckEventBase, table=True):
    __tablename__ = "check_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    __table_args__ = (
        Index("ix_events_session_type", "session_id", "event_type"),
    )


class EventStore:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._engine = None
        self._current_session_id: str = ""
        self._write_semaphore = asyncio.Semaphore(1)
        # Initialize engine first to ensure tables exist
        _ = self.engine
        self._load_latest_session()
        # Seed history from existing completed sessions if table is empty
        self._seed_history_from_events()

    def _seed_history_from_events(self):
        """从现有事件数据中导入历史记录（一次性操作）"""
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                count = conn.execute(text("SELECT COUNT(*) FROM check_history")).fetchone()[0]
                if count > 0:
                    return
                logger.info("正在从事件数据导入历史记录...")
                result = conn.execute(
                    text("""
                        SELECT session_id, COUNT(*) as total
                        FROM check_events 
                        WHERE event_type='channel_checked'
                        GROUP BY session_id
                        HAVING total > 0
                        ORDER BY session_id DESC
                    """)
                ).fetchall()
                for row in result:
                    sid, total = row[0], row[1]
                    valid = conn.execute(
                        text("SELECT COUNT(*) FROM check_events WHERE session_id=:sid AND event_type='channel_checked' AND json_extract(payload, '$.is_valid') = 1"),
                        {"sid": sid}
                    ).fetchone()[0]
                    conn.execute(
                        text("INSERT OR IGNORE INTO check_history (session_id, total, valid, invalid, elapsed, created_at) VALUES (:sid, :total, :valid, :invalid, 0, '')"),
                        {"sid": sid, "total": total, "valid": valid, "invalid": total - valid}
                    )
                conn.commit()
                logger.info("已导入 %d 条历史记录", len(result))
        except Exception as e:
            logger.warning("导入历史记录失败: %s", e)

    def _load_latest_session(self):
        """Load the latest completed session on startup"""
        try:
            latest_id = self.get_latest_session_id()
            if latest_id:
                self._current_session_id = latest_id
                logger.info("恢复上次检测会话: %s", latest_id)
        except Exception as e:
            logger.warning("无法恢复上次检测会话: %s", e)

    @property
    def engine(self):
        if self._engine is None:
            db_dir = os.path.dirname(self._db_path)
            os.makedirs(db_dir, exist_ok=True)
            self._engine = create_engine(
                f"sqlite:///{self._db_path}",
                echo=False,
                pool_pre_ping=True,
            )
            SQLModel.metadata.create_all(self._engine)
            # Ensure check_history table exists
            with self._engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS check_history (
                            session_id TEXT PRIMARY KEY,
                            total INTEGER NOT NULL DEFAULT 0,
                            valid INTEGER NOT NULL DEFAULT 0,
                            invalid INTEGER NOT NULL DEFAULT 0,
                            elapsed REAL NOT NULL DEFAULT 0.0,
                            created_at TEXT NOT NULL
                        )
                    """)
                )
                conn.commit()
            logger.info("EventStore 初始化: %s", self._db_path)
        return self._engine

    def get_session(self) -> Session:
        return Session(self.engine)

    @property
    def current_session_id(self) -> str:
        return self._current_session_id

    def new_session(self) -> str:
        self._current_session_id = f"chk_{int(time.time() * 1000)}"
        return self._current_session_id

    async def append(self, event_type: str, payload: dict = None, session_id: str = None) -> int:
        async with self._write_semaphore:
            return await asyncio.to_thread(self._sync_append, event_type, payload, session_id)

    def _sync_append(self, event_type: str, payload: dict = None, session_id: str = None) -> int:
        with self.get_session() as session:
            event = CheckEventModel(
                event_type=event_type,
                payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
                session_id=session_id or self._current_session_id,
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.id

    async def append_batch(self, events: list[tuple[str, dict]], session_id: str = None) -> list[int]:
        async with self._write_semaphore:
            return await asyncio.to_thread(self._sync_append_batch, events, session_id)

    def _sync_append_batch(self, events: list[tuple[str, dict]], session_id: str = None) -> list[int]:
        with self.get_session() as session:
            ids = []
            sid = session_id or self._current_session_id
            for event_type, payload in events:
                event = CheckEventModel(
                    event_type=event_type,
                    payload=json.dumps(payload or {}, ensure_ascii=False, default=str),
                    session_id=sid,
                )
                session.add(event)
                session.flush()
                ids.append(event.id)
            session.commit()
            return ids

    def get_events(self, session_id: str = None, event_type: str = None, limit: int = 1000) -> list[dict]:
        with self.get_session() as session:
            query = select(CheckEventModel)
            if session_id:
                query = query.where(CheckEventModel.session_id == session_id)
            if event_type:
                query = query.where(CheckEventModel.event_type == event_type)
            query = query.order_by(CheckEventModel.created_at.asc()).limit(limit)
            results = session.exec(query).all()
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "payload": json.loads(e.payload) if e.payload else {},
                    "session_id": e.session_id,
                    "created_at": e.created_at.isoformat(),
                }
                for e in results
            ]

    def save_history(self, session_id: str, total: int = 0, valid: int = 0, invalid: int = 0, elapsed: float = 0.0) -> None:
        """保存本次检测的历史记录到 check_history 表"""
        from datetime import datetime
        from sqlalchemy import text
        
        try:
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT OR REPLACE INTO check_history (session_id, total, valid, invalid, elapsed, created_at)
                        VALUES (:session_id, :total, :valid, :invalid, :elapsed, :created_at)
                    """),
                    {
                        "session_id": session_id,
                        "total": total,
                        "valid": valid,
                        "invalid": invalid,
                        "elapsed": elapsed,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                )
                conn.commit()
            logger.info("保存检测历史: session=%s, total=%d, valid=%d, invalid=%d", session_id, total, valid, invalid)
        except Exception as e:
            logger.warning("保存检测历史失败: %s", e)

    def get_latest_session_id(self) -> str:
        """获取最新完成的会话ID（按channel_checked数量最多的会话）"""
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                # Find session with most channel_checked events
                result = conn.execute(
                    text("""
                        SELECT session_id, COUNT(*) as cnt 
                        FROM check_events 
                        WHERE event_type='channel_checked' 
                        GROUP BY session_id 
                        ORDER BY cnt DESC, session_id DESC 
                        LIMIT 1
                    """)
                ).fetchone()
                if result and result[1] > 0:
                    logger.info("找到最新会话: %s (%d 个频道)", result[0], result[1])
                    return result[0]
                return ""
        except Exception as e:
            logger.warning("获取最新会话失败: %s", e)
            return ""

    def get_history(self, limit: int = 20) -> list[dict]:
        """获取历史检测记录"""
        from sqlalchemy import text
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT session_id, total, valid, invalid, elapsed, created_at FROM check_history ORDER BY created_at DESC LIMIT :limit"),
                    {"limit": limit}
                ).fetchall()
                return [
                    {
                        "session_id": row[0],
                        "total": row[1],
                        "valid": row[2],
                        "invalid": row[3],
                        "elapsed": row[4],
                        "created_at": row[5],
                    }
                    for row in result
                ]
        except Exception as e:
            logger.warning("获取历史记录失败: %s", e)
            return []

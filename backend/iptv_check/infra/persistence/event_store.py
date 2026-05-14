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

    def get_latest_session_id(self) -> Optional[str]:
        with self.get_session() as session:
            result = session.exec(
                select(CheckEventModel.session_id)
                .where(CheckEventModel.event_type == "check_started")
                .order_by(CheckEventModel.created_at.desc())
                .limit(1)
            ).first()
            return result

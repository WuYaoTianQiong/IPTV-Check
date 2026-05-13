import os
import json
import time
import logging
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

from sqlmodel import SQLModel, Field, create_engine, Session, select, col
from sqlalchemy import Index, func

logger = logging.getLogger(__name__)


class ChannelBase(SQLModel):
    name: str = Field(index=True)
    url: str = Field(unique=True)
    group: Optional[str] = Field(default=None, index=True)
    sources: str = Field(default="[]")
    url_key: str = Field(default="", index=True)


class ChannelModel(ChannelBase, table=True):
    __tablename__ = "channels"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CheckResultBase(SQLModel):
    channel_id: int = Field(foreign_key="channels.id", index=True)
    is_valid: bool = Field(index=True)
    latency: float = Field(default=0)
    speed: str = Field(default="-")
    details: str = Field(default="")
    tag: str = Field(default="", index=True)
    checked_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class CheckResultModel(CheckResultBase, table=True):
    __tablename__ = "check_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    __table_args__ = (
        Index("ix_check_results_channel_checked", "channel_id", "checked_at"),
    )


class CheckHistoryBase(SQLModel):
    name: str = Field(default="")
    total_count: int = Field(default=0)
    valid_count: int = Field(default=0)
    invalid_count: int = Field(default=0)
    elapsed_seconds: float = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class CheckHistoryModel(CheckHistoryBase, table=True):
    __tablename__ = "check_history"
    
    id: Optional[int] = Field(default=None, primary_key=True)


class FavoriteBase(SQLModel):
    channel_id: int = Field(foreign_key="channels.id", index=True)
    name: str = Field(default="")
    url: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FavoriteModel(FavoriteBase, table=True):
    __tablename__ = "favorites"
    
    id: Optional[int] = Field(default=None, primary_key=True)


class DatabaseManager:
    def __init__(self, db_path: str = None):
        self._db_path = db_path
        self._engine = None

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
            logger.info("数据库初始化: %s", self._db_path)
        return self._engine

    def get_session(self) -> Session:
        return Session(self.engine)

    @asynccontextmanager
    async def async_session(self):
        with self.get_session() as session:
            yield session

    def save_check_result(self, results: List[dict], history_name: str = "") -> int:
        """保存检测结果并返回历史记录ID"""
        with self.get_session() as session:
            channel_ids = []
            history_id = None
            
            for r in results:
                channel_data = r.get("channel", {})
                channel = session.exec(
                    select(ChannelModel).where(ChannelModel.url == channel_data.get("url", ""))
                ).first()
                
                if not channel:
                    channel = ChannelModel(
                        name=channel_data.get("name", "未知"),
                        url=channel_data.get("url", ""),
                        group=channel_data.get("group"),
                        sources=json.dumps(channel_data.get("sources", []), ensure_ascii=False),
                        url_key=channel_data.get("url_key", ""),
                    )
                    session.add(channel)
                    session.flush()
                
                check_result = CheckResultModel(
                    channel_id=channel.id,
                    is_valid=r.get("is_valid", False),
                    latency=r.get("latency", 0),
                    speed=r.get("speed", "-"),
                    details=r.get("details", ""),
                    tag=r.get("tag", ""),
                    checked_at=datetime.utcnow(),
                )
                session.add(check_result)
                channel_ids.append(channel.id)
            
            valid_count = sum(1 for r in results if r.get("is_valid"))
            invalid_count = len(results) - valid_count
            
            history = CheckHistoryModel(
                name=history_name,
                total_count=len(results),
                valid_count=valid_count,
                invalid_count=invalid_count,
                elapsed_seconds=0,
            )
            session.add(history)
            session.flush()
            history_id = history.id
            
            session.commit()
            logger.info("保存检测结果: 总数=%d, 有效=%d, history_id=%d", len(results), valid_count, history_id)
            return history_id

    def load_latest_results(self) -> List[dict]:
        """加载最近一次的检测结果"""
        with self.get_session() as session:
            latest_history = session.exec(
                select(CheckHistoryModel).order_by(CheckHistoryModel.created_at.desc()).limit(1)
            ).first()
            
            if not latest_history:
                return []
            
            cutoff = latest_history.created_at
            one_hour_before = cutoff
            
            results = session.exec(
                select(CheckResultModel, ChannelModel)
                .join(ChannelModel)
                .where(CheckResultModel.checked_at >= one_hour_before)
                .order_by(CheckResultModel.checked_at.desc())
            ).all()
            
            return [
                {
                    "channel": {
                        "id": ch.id,
                        "name": ch.name,
                        "url": ch.url,
                        "group": ch.group,
                        "sources": json.loads(ch.sources) if ch.sources else [],
                        "url_key": ch.url_key,
                    },
                    "is_valid": cr.is_valid,
                    "latency": cr.latency,
                    "speed": cr.speed,
                    "details": cr.details,
                    "tag": cr.tag,
                    "checked_at": cr.checked_at.isoformat(),
                }
                for cr, ch in results
            ]

    def get_check_history(self, limit: int = 20) -> List[dict]:
        with self.get_session() as session:
            items = session.exec(
                select(CheckHistoryModel).order_by(CheckHistoryModel.created_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "id": h.id,
                    "name": h.name,
                    "total_count": h.total_count,
                    "valid_count": h.valid_count,
                    "invalid_count": h.invalid_count,
                    "elapsed_seconds": h.elapsed_seconds,
                    "created_at": h.created_at.isoformat(),
                }
                for h in items
            ]

    def get_stats(self) -> dict:
        with self.get_session() as session:
            total_channels = session.exec(select(func.count(ChannelModel.id))).one()
            total_checks = session.exec(select(func.count(CheckHistoryModel.id))).one()
            latest = session.exec(
                select(CheckHistoryModel).order_by(CheckHistoryModel.created_at.desc()).limit(1)
            ).first()
            return {
                "total_channels": total_channels,
                "total_checks": total_checks,
                "latest_check": latest.created_at.isoformat() if latest else None,
                "latest_valid": latest.valid_count if latest else 0,
            }

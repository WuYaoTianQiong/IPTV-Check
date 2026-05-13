import os
import json
import time
import logging
from typing import Optional, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlmodel import SQLModel, Field, create_engine, Session, select, col
from sqlalchemy import Index, func, text

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

    def get_channel_trend(self, channel_id: int, days: int = 7) -> List[dict]:
        """获取频道历史检测趋势"""
        with self.get_session() as session:
            cutoff = datetime.utcnow() - __import__('datetime', fromlist=['timedelta']).timedelta(days=days)
            results = session.exec(
                select(CheckResultModel)
                .where(CheckResultModel.channel_id == channel_id)
                .where(CheckResultModel.checked_at >= cutoff)
                .order_by(CheckResultModel.checked_at.asc())
            ).all()
            return [
                {
                    "checked_at": r.checked_at.isoformat(),
                    "is_valid": r.is_valid,
                    "latency": r.latency,
                    "speed": r.speed,
                    "details": r.details,
                }
                for r in results
            ]

    def get_channel_stability_stats(self, channel_id: int, days: int = 7) -> dict:
        """获取频道稳定性统计"""
        with self.get_session() as session:
            cutoff = datetime.utcnow() - __import__('datetime', fromlist=['timedelta']).timedelta(days=days)
            results = session.exec(
                select(CheckResultModel)
                .where(CheckResultModel.channel_id == channel_id)
                .where(CheckResultModel.checked_at >= cutoff)
            ).all()

            if not results:
                return {"total_checks": 0, "online_rate": 0, "avg_latency": 0, "stability": "unknown"}

            total = len(results)
            valid = sum(1 for r in results if r.is_valid)
            latencies = [r.latency for r in results if r.is_valid and r.latency > 0]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0

            # 计算稳定性（基于在线率和延迟波动）
            online_rate = valid / total * 100
            latency_std = 0
            if len(latencies) > 1:
                mean = sum(latencies) / len(latencies)
                variance = sum((x - mean) ** 2 for x in latencies) / len(latencies)
                latency_std = variance ** 0.5

            # 稳定性评级
            if online_rate >= 90 and latency_std < 50:
                stability = "excellent"
            elif online_rate >= 70 and latency_std < 100:
                stability = "good"
            elif online_rate >= 50:
                stability = "fair"
            else:
                stability = "poor"

            return {
                "total_checks": total,
                "online_count": valid,
                "online_rate": round(online_rate, 1),
                "avg_latency": round(avg_latency, 0),
                "min_latency": min(latencies) if latencies else 0,
                "max_latency": max(latencies) if latencies else 0,
                "latency_std": round(latency_std, 0),
                "stability": stability,
            }

    def get_top_stable_channels(self, days: int = 7, limit: int = 50) -> List[dict]:
        """获取最稳定的频道列表"""
        with self.get_session() as session:
            cutoff = datetime.utcnow() - __import__('datetime', fromlist=['timedelta']).timedelta(days=days)
            
            # 获取所有频道在该时间段内的检测结果
            query = text("""
                SELECT 
                    c.id, c.name, c.url, c.group,
                    COUNT(cr.id) as total_checks,
                    SUM(CASE WHEN cr.is_valid = 1 THEN 1 ELSE 0 END) as valid_count,
                    AVG(CASE WHEN cr.is_valid = 1 AND cr.latency > 0 THEN cr.latency END) as avg_latency
                FROM channels c
                JOIN check_results cr ON c.id = cr.channel_id
                WHERE cr.checked_at >= :cutoff
                GROUP BY c.id
                HAVING total_checks >= 2
                ORDER BY (valid_count * 1.0 / total_checks) DESC, avg_latency ASC
                LIMIT :limit
            """)
            
            results = session.exec(query.params(cutoff=cutoff, limit=limit)).all()
            return [
                {
                    "id": r[0],
                    "name": r[1],
                    "url": r[2],
                    "group": r[3],
                    "total_checks": r[4],
                    "valid_count": r[5],
                    "online_rate": round(r[5] / r[4] * 100, 1) if r[4] > 0 else 0,
                    "avg_latency": round(r[6], 0) if r[6] else 0,
                }
                for r in results
            ]

    def get_history_comparison(self, history_id_1: int, history_id_2: int) -> dict:
        """对比两次检测历史"""
        with self.get_session() as session:
            history_1 = session.get(CheckHistoryModel, history_id_1)
            history_2 = session.get(CheckHistoryModel, history_id_2)
            
            if not history_1 or not history_2:
                return {"error": "历史记录不存在"}

            return {
                "history_1": {
                    "id": history_1.id,
                    "name": history_1.name,
                    "total_count": history_1.total_count,
                    "valid_count": history_1.valid_count,
                    "invalid_count": history_1.invalid_count,
                    "valid_rate": round(history_1.valid_count / history_1.total_count * 100, 1) if history_1.total_count > 0 else 0,
                    "created_at": history_1.created_at.isoformat(),
                },
                "history_2": {
                    "id": history_2.id,
                    "name": history_2.name,
                    "total_count": history_2.total_count,
                    "valid_count": history_2.valid_count,
                    "invalid_count": history_2.invalid_count,
                    "valid_rate": round(history_2.valid_count / history_2.total_count * 100, 1) if history_2.total_count > 0 else 0,
                    "created_at": history_2.created_at.isoformat(),
                },
            }

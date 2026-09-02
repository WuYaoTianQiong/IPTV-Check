import os
import json
import time
import logging
from typing import Optional, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from sqlmodel import SQLModel, Field, create_engine, Session, select, col
from sqlalchemy import Index, func, text, case as sa_case, Float
from iptv_check.infra.cn_time import cn_now

logger = logging.getLogger(__name__)


class ChannelBase(SQLModel):
    name: str = Field(index=True)
    url: str = Field(unique=True)
    group: Optional[str] = Field(default=None, index=True)
    sources: str = Field(default="[]")
    url_key: str = Field(default="", index=True)
    resolution: str = Field(default="")


class ChannelModel(ChannelBase, table=True):
    __tablename__ = "channels"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=cn_now)


class CheckResultBase(SQLModel):
    channel_id: int = Field(foreign_key="channels.id", index=True)
    is_valid: bool = Field(index=True)
    quality_tier: str = Field(default="", index=True)
    latency: float = Field(default=0)
    speed: str = Field(default="-")
    details: str = Field(default="")
    tag: str = Field(default="", index=True)
    checked_at: datetime = Field(default_factory=cn_now, index=True)


class CheckResultModel(CheckResultBase, table=True):
    __tablename__ = "check_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    __table_args__ = (
        Index("ix_check_results_channel_checked", "channel_id", "checked_at"),
    )


class CheckHistoryBase(SQLModel):
    session_id: str = Field(default="", index=True)
    name: str = Field(default="")
    total_count: int = Field(default=0)
    valid_count: int = Field(default=0)
    invalid_count: int = Field(default=0)
    elapsed_seconds: float = Field(default=0)
    created_at: datetime = Field(default_factory=cn_now, index=True)
    # 二次复检完成时间（前端"最后更新"展示；由 alembic 迁移补充到已有库）
    last_updated: Optional[datetime] = Field(default=None)
    # 检测方案（quick/standard/deep）与来源会话（细筛自哪个粗筛 session；由 alembic 迁移补充）
    check_mode: str = Field(default="")
    parent_session_id: str = Field(default="", index=True)


class CheckHistoryModel(CheckHistoryBase, table=True):
    __tablename__ = "check_history"

    id: Optional[int] = Field(default=None, primary_key=True)


class FavoriteFolderBase(SQLModel):
    name: str = Field(default="")
    icon: str = Field(default="")
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=cn_now)


class FavoriteFolderModel(FavoriteFolderBase, table=True):
    __tablename__ = "favorite_folders"

    id: Optional[int] = Field(default=None, primary_key=True)


class CustomChannelBase(SQLModel):
    name: str = Field(default="")
    url: str = Field(default="", unique=True)
    group: str = Field(default="")
    folder_id: Optional[int] = Field(default=None, foreign_key="favorite_folders.id", index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=cn_now)


class CustomChannelModel(CustomChannelBase, table=True):
    __tablename__ = "custom_channels"

    id: Optional[int] = Field(default=None, primary_key=True)


class FavoriteBase(SQLModel):
    channel_id: int = Field(default=0, index=True)
    name: str = Field(default="")
    name_cn: str = Field(default="")
    url: str = Field(default="")
    folder_id: Optional[int] = Field(default=None, foreign_key="favorite_folders.id", index=True)
    channel_group: str = Field(default="")
    sort_order: int = Field(default=0)
    latency: float = Field(default=0.0)
    latency_updated_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=cn_now)


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
                connect_args={"timeout": 30},
            )
            self._configure_pragma(self._engine)
            self._ensure_alembic_managed()
            logger.info("数据库初始化: %s", self._db_path)
        return self._engine

    @staticmethod
    def _configure_pragma(engine):
        from sqlalchemy import event as sa_event, text as sa_text

        @sa_event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA wal_autocheckpoint=1000")
            cursor.close()

        with engine.connect() as conn:
            conn.execute(sa_text("PRAGMA journal_mode=WAL"))
            conn.execute(sa_text("PRAGMA synchronous=NORMAL"))
            conn.execute(sa_text("PRAGMA wal_autocheckpoint=1000"))
            conn.execute(sa_text("PRAGMA busy_timeout=30000"))
            conn.commit()

    def _ensure_alembic_managed(self) -> None:
        """用 alembic 版本化迁移管理 schema。

        - 全新库：直接 upgrade 到 head（按迁移创建全部表）
        - 已有 alembic_version 的库：upgrade 到 head（增量）
        - 旧版库（表已存在但无 alembic_version）：stamp 为 head（视为 baseline）
        """
        from alembic import command
        from alembic.config import Config

        ini_path = os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")
        cfg = Config(ini_path)
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{self._db_path}")
        # script_location 按绝对路径解析，避免依赖进程工作目录
        cfg.set_main_option("script_location", os.path.join(os.path.dirname(ini_path), "alembic"))

        from sqlalchemy import text as sa_text
        with self._engine.connect() as conn:
            has_version = conn.execute(
                sa_text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
            ).first()
            has_business_table = conn.execute(
                sa_text("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
            ).first()
        if has_version:
            command.upgrade(cfg, "head")
        elif has_business_table:
            command.stamp(cfg, "head")
            logger.info("数据库已存在（旧版），已 stamp 为 alembic baseline")
        else:
            command.upgrade(cfg, "head")

    def get_session(self) -> Session:
        return Session(self.engine)

    @asynccontextmanager
    async def async_session(self):
        with self.get_session() as session:
            yield session

    def save_check_result(self, results: List[dict], history_name: str = "", session_id: str = "") -> int:
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
                        resolution=channel_data.get("resolution", ""),
                    )
                    session.add(channel)
                    session.flush()

                check_result = CheckResultModel(
                    channel_id=channel.id,
                    is_valid=r.get("is_valid", False),
                    quality_tier=r.get("quality_tier", ""),
                    latency=r.get("latency", 0),
                    speed=r.get("speed", "-"),
                    details=r.get("details", ""),
                    tag=r.get("tag", ""),
                    checked_at=cn_now(),
                )
                session.add(check_result)
                channel_ids.append(channel.id)

            valid_count = sum(1 for r in results if r.get("is_valid"))
            invalid_count = len(results) - valid_count

            history = CheckHistoryModel(
                session_id=session_id,
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
                        "resolution": ch.resolution,
                    },
                    "is_valid": cr.is_valid,
                    "quality_tier": cr.quality_tier or "",
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
            cutoff = cn_now() - timedelta(days=days)
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
        with self.get_session() as session:
            cutoff = cn_now() - timedelta(days=days)
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
            cutoff = cn_now() - timedelta(days=days)
            
            # 获取所有频道在该时间段内的检测结果
            query = text("""
                SELECT 
                    c.id, c.name, c.url, c."group" as channel_group,
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

    def query_results_paginated(
        self,
        tab: str = "all",
        page: int = 1,
        per_page: int = 50,
        search: str = "",
        sort: str = "best",
        history_id: Optional[int] = None,
    ) -> dict:
        with self.get_session() as session:
            base_query = select(CheckResultModel, ChannelModel).join(ChannelModel)

            if history_id:
                history = session.get(CheckHistoryModel, history_id)
                if history:
                    cutoff = history.created_at
                    from datetime import timedelta as _td
                    base_query = base_query.where(
                        CheckResultModel.checked_at >= cutoff - _td(minutes=5)
                    ).where(CheckResultModel.checked_at <= cutoff + _td(minutes=5))
            else:
                latest = session.exec(
                    select(CheckHistoryModel).order_by(CheckHistoryModel.created_at.desc()).limit(1)
                ).first()
                if latest:
                    cutoff = latest.created_at
                    from datetime import timedelta as _td
                    base_query = base_query.where(
                        CheckResultModel.checked_at >= cutoff - _td(minutes=5)
                    )

            if tab == "valid":
                base_query = base_query.where(CheckResultModel.is_valid == True, CheckResultModel.quality_tier == "valid")
            elif tab == "invalid":
                base_query = base_query.where(CheckResultModel.quality_tier == "invalid")
            elif tab == "likely_valid":
                base_query = base_query.where(CheckResultModel.quality_tier == "likely_valid")

            if search:
                search_lower = f"%{search.lower()}%"
                base_query = base_query.where(
                    (func.lower(ChannelModel.name).like(search_lower))
                    | (func.lower(ChannelModel.url).like(search_lower))
                )

            count_query = select(func.count()).select_from(base_query.subquery())
            total = session.exec(count_query).one()

            # Build order_by clause from sort param
            _order = [ChannelModel.name.asc()]
            if sort == "best":
                _order = [
                    sa_case(
                        (CheckResultModel.quality_tier == "valid", 0),
                        (CheckResultModel.quality_tier == "likely_valid", 1),
                        else_=2,
                    ).asc(),
                    sa_case(
                        (CheckResultModel.latency.is_(None) | (CheckResultModel.latency < 0), 999999),
                        else_=CheckResultModel.latency,
                    ).asc(),
                ]
            elif sort == "name_asc":
                _order = [ChannelModel.name.asc()]
            elif sort == "name_desc":
                _order = [ChannelModel.name.desc()]
            elif sort == "latency_asc":
                _order = [
                    sa_case(
                        (CheckResultModel.latency.is_(None) | (CheckResultModel.latency < 0), 999999),
                        else_=CheckResultModel.latency,
                    ).asc(),
                ]
            elif sort == "latency_desc":
                _order = [CheckResultModel.latency.desc()]
            elif sort == "speed_asc":
                _order = [
                    sa_case(
                        (CheckResultModel.speed == "-", 999999999),
                        else_=func.cast(CheckResultModel.speed, Float),
                    ).asc(),
                ]
            elif sort == "speed_desc":
                _order = [func.cast(CheckResultModel.speed, Float).desc()]

            offset = (page - 1) * per_page
            results = session.exec(
                base_query.order_by(*_order).offset(offset).limit(per_page)
            ).all()

            items = []
            for idx, (cr, ch) in enumerate(results):
                sources_list = json.loads(ch.sources) if ch.sources else []
                is_valid = cr.is_valid
                quality_tier = cr.quality_tier or ("valid" if is_valid else "invalid")
                items.append({
                    "index": offset + idx + 1,
                    "name": ch.name,
                    "url": ch.url,
                    "group": ch.group or "",
                    "sources": ", ".join(sources_list),
                    "is_valid": is_valid,
                    "quality_tier": quality_tier,
                    "status": "有效" if quality_tier == "valid" else ("疑似有效" if quality_tier == "likely_valid" else "无效"),
                    "latency": str(int(cr.latency)) if cr.latency >= 0 else "-",
                    "speed": cr.speed,
                    "details": cr.details,
                })

            return {"total": total, "page": page, "per_page": per_page, "items": items}

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

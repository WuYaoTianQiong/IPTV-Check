import os
import json
import time
import logging
import asyncio
from typing import Optional, Any, List
from datetime import datetime

from sqlmodel import SQLModel, Field, create_engine, Session, select
from iptv_check.infra.cn_time import cn_now
from sqlalchemy import Index, func, text as sa_text

logger = logging.getLogger(__name__)


class CheckEventBase(SQLModel):
    event_type: str = Field(index=True)
    payload: str = Field(default="{}")
    session_id: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=cn_now, index=True)


class CheckEventModel(CheckEventBase, table=True):
    __tablename__ = "check_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    __table_args__ = (
        Index("ix_events_session_type", "session_id", "event_type"),
    )


class ChannelResultModel(SQLModel, table=True):
    __tablename__ = "channel_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(default="", index=True)
    name: str = Field(default="")
    url: str = Field(default="")
    url_key: str = Field(default="")
    is_valid: int = Field(default=0)
    is_radio: int = Field(default=0)
    quality_tier: str = Field(default="invalid")
    latency: float = Field(default=-1)
    speed: str = Field(default="-")
    details: str = Field(default="")
    channel_group: str = Field(default="")
    sources: str = Field(default="[]")
    language: str = Field(default="")
    country: str = Field(default="")
    content_type: str = Field(default="")
    source_name: str = Field(default="")
    resolution: str = Field(default="")
    tvg_name: str = Field(default="")
    clean_name: str = Field(default="")
    frequency: str = Field(default="")
    created_at: datetime = Field(default_factory=cn_now)

    __table_args__ = (
        Index("ix_cr_session_valid", "session_id", "is_valid"),
        Index("ix_cr_session_name", "session_id", "name"),
        Index("ix_cr_session_group", "session_id", "channel_group"),
        Index("ix_cr_session_radio", "session_id", "is_radio"),
        Index("ix_cr_session_valid_radio", "session_id", "is_valid", "is_radio"),
        Index("ix_cr_session_valid_name", "session_id", "is_valid", "name"),
    )


class SessionSummaryModel(SQLModel, table=True):
    __tablename__ = "session_summaries"

    session_id: str = Field(default="", primary_key=True)
    total_count: int = Field(default=0)
    valid_count: int = Field(default=0)
    invalid_count: int = Field(default=0)
    likely_valid_count: int = Field(default=0)
    tv_count: int = Field(default=0)
    radio_count: int = Field(default=0)
    avg_latency: float = Field(default=0)
    elapsed_seconds: float = Field(default=0)
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=cn_now)
    updated_at: datetime = Field(default_factory=cn_now)


class OnlineSourceModel(SQLModel, table=True):
    __tablename__ = "online_sources"

    id: str = Field(default="", primary_key=True)
    name: str = Field(default="")
    url: str = Field(default="", unique=True)
    isp: str = Field(default="[]")
    protocol: str = Field(default="ipv4")
    features: str = Field(default="[]")
    description: str = Field(default="")
    category: str = Field(default="其他", index=True)
    mirror_url: Optional[str] = Field(default=None)
    disabled: int = Field(default=0)
    epg_url: Optional[str] = Field(default=None)
    logo_base_url: Optional[str] = Field(default=None)
    update_frequency: str = Field(default="daily")
    quality_rating: str = Field(default="A")
    channel_count: int = Field(default=0)
    last_updated: Optional[str] = Field(default=None)
    cache_filename: Optional[str] = Field(default=None)

    __table_args__ = (
        Index("ix_os_category", "category"),
        Index("ix_os_protocol", "protocol"),
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
                        text("INSERT OR IGNORE INTO check_history (session_id, name, total_count, valid_count, invalid_count, elapsed_seconds, created_at) VALUES (:sid, '', :total, :valid, :invalid, 0, :created_at)"),
                        {"sid": sid, "total": total, "valid": valid, "invalid": total - valid, "created_at": cn_now().isoformat()}
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
            cursor.close()

        with engine.connect() as conn:
            conn.execute(sa_text("PRAGMA journal_mode=WAL"))
            conn.execute(sa_text("PRAGMA synchronous=NORMAL"))
            conn.execute(sa_text("PRAGMA busy_timeout=30000"))
            conn.commit()

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
            SQLModel.metadata.create_all(self._engine)
            # Ensure fetched_channels table exists
            with self._engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS fetched_channels (
                            id INTEGER PRIMARY KEY,
                            url_key TEXT DEFAULT '',
                            name TEXT DEFAULT '',
                            url TEXT DEFAULT '',
                            channel_group TEXT DEFAULT '',
                            source_name TEXT DEFAULT '',
                            source_id TEXT DEFAULT '',
                            tvg_id TEXT DEFAULT '',
                            tvg_name TEXT DEFAULT '',
                            logo_url TEXT DEFAULT '',
                            language TEXT DEFAULT '',
                            country TEXT DEFAULT '',
                            is_radio INTEGER DEFAULT 0,
                            resolution TEXT DEFAULT '',
                            fetched_at TEXT DEFAULT (datetime('now'))
                        )
                    """)
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fc_url_key ON fetched_channels(url_key)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fc_source_id ON fetched_channels(source_id)"))
                conn.commit()
            # Ensure check_history table exists (schema matches CheckHistoryModel in database.py)
            with self._engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(
                    text("""
                        CREATE TABLE IF NOT EXISTS check_history (
                            session_id VARCHAR NOT NULL DEFAULT '',
                            name VARCHAR NOT NULL DEFAULT '',
                            total_count INTEGER NOT NULL DEFAULT 0,
                            valid_count INTEGER NOT NULL DEFAULT 0,
                            invalid_count INTEGER NOT NULL DEFAULT 0,
                            elapsed_seconds FLOAT NOT NULL DEFAULT 0.0,
                            created_at DATETIME NOT NULL,
                            id INTEGER PRIMARY KEY AUTOINCREMENT
                        )
                    """)
                )
                conn.commit()
                cr_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(channel_results)")).fetchall()]
                if "resolution" not in cr_cols:
                    conn.execute(text("ALTER TABLE channel_results ADD COLUMN resolution TEXT DEFAULT ''"))
                    conn.commit()
                    logger.info("迁移: channel_results 增加 resolution 列")
                if "tvg_name" not in cr_cols:
                    conn.execute(text("ALTER TABLE channel_results ADD COLUMN tvg_name TEXT DEFAULT ''"))
                    conn.commit()
                    logger.info("迁移: channel_results 增加 tvg_name 列")
                if "clean_name" not in cr_cols:
                    conn.execute(text("ALTER TABLE channel_results ADD COLUMN clean_name TEXT DEFAULT ''"))
                    conn.commit()
                    logger.info("迁移: channel_results 增加 clean_name 列")
                if "frequency" not in cr_cols:
                    conn.execute(text("ALTER TABLE channel_results ADD COLUMN frequency TEXT DEFAULT ''"))
                    conn.commit()
                    logger.info("迁移: channel_results 增加 frequency 列")
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
        from sqlalchemy import text
        
        try:
            with self.engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT OR REPLACE INTO check_history (session_id, name, total_count, valid_count, invalid_count, elapsed_seconds, created_at)
                        VALUES (:session_id, :name, :total, :valid, :invalid, :elapsed, :created_at)
                    """),
                    {
                        "session_id": session_id,
                        "name": "",
                        "total": total,
                        "valid": valid,
                        "invalid": invalid,
                        "elapsed": elapsed,
                        "created_at": cn_now().isoformat(),
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
                    text("SELECT session_id, name, total_count, valid_count, invalid_count, elapsed_seconds, created_at FROM check_history ORDER BY created_at DESC LIMIT :limit"),
                    {"limit": limit}
                ).fetchall()
                return [
                    {
                        "session_id": row[0],
                        "name": row[1],
                        "total": row[2],
                        "valid": row[3],
                        "invalid": row[4],
                        "elapsed": row[5],
                        "created_at": row[6],
                    }
                    for row in result
                ]
        except Exception as e:
            logger.warning("获取历史记录失败: %s", e)
            return []


class SourceStore:
    """频道源数据管理（替代 local_sources.json）"""

    def __init__(self, event_store: EventStore):
        self._event_store = event_store

    def _model_to_source(self, model: OnlineSourceModel) -> "OnlineSource":
        from iptv_check.models.source import OnlineSource
        return OnlineSource(
            id=model.id,
            name=model.name,
            url=model.url,
            isp=json.loads(model.isp) if model.isp else [],
            protocol=model.protocol,
            features=json.loads(model.features) if model.features else [],
            description=model.description,
            category=model.category,
            mirror_url=model.mirror_url,
            disabled=bool(model.disabled),
            epg_url=model.epg_url,
            logo_base_url=model.logo_base_url,
            update_frequency=model.update_frequency,
            quality_rating=model.quality_rating,
            channel_count=model.channel_count,
            last_updated=model.last_updated,
            cache_filename=model.cache_filename,
        )

    def _source_to_model(self, source: "OnlineSource") -> OnlineSourceModel:
        from iptv_check.models.source import OnlineSource
        return OnlineSourceModel(
            id=source.id,
            name=source.name,
            url=source.url,
            isp=json.dumps(source.isp, ensure_ascii=False),
            protocol=source.protocol,
            features=json.dumps(source.features, ensure_ascii=False),
            description=source.description,
            category=source.category,
            mirror_url=source.mirror_url,
            disabled=1 if source.disabled else 0,
            epg_url=source.epg_url,
            logo_base_url=source.logo_base_url,
            update_frequency=source.update_frequency,
            quality_rating=source.quality_rating,
            channel_count=source.channel_count,
            last_updated=source.last_updated,
            cache_filename=source.cache_filename,
        )

    def load_all(self) -> List["OnlineSource"]:
        with Session(self._event_store.engine) as session:
            results = session.exec(select(OnlineSourceModel)).all()
            return [self._model_to_source(m) for m in results]

    def save_all(self, sources: List["OnlineSource"]) -> None:
        seen_urls = set()
        deduped = []
        for s in sources:
            if s.url not in seen_urls:
                seen_urls.add(s.url)
                deduped.append(s)
        with Session(self._event_store.engine) as session:
            session.exec(sa_text("DELETE FROM online_sources"))
            for source in deduped:
                model = self._source_to_model(source)
                session.add(model)
            session.commit()
        logger.info("保存 %d 个频道源到数据库（去重后）", len(deduped))

    def count(self) -> int:
        with Session(self._event_store.engine) as session:
            return session.exec(select(func.count(OnlineSourceModel.id))).one()

    def migrate_from_json(self, json_path: str) -> int:
        """从 local_sources.json 迁移到数据库"""
        from iptv_check.models.source import OnlineSource
        if not os.path.exists(json_path):
            return 0
        existing = self.count()
        if existing > 0:
            logger.info("数据库中已有 %d 个源，跳过迁移", existing)
            return existing
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            sources_data = data.get("sources", []) if isinstance(data, dict) else data
            if not isinstance(sources_data, list):
                return 0
            sources = [OnlineSource.from_dict(s) for s in sources_data]
            self.save_all(sources)
            count = self.count()
            logger.info("从 JSON 迁移 %d 个频道源到数据库", count)
            return count
        except Exception as e:
            logger.warning("从 JSON 迁移失败: %s", e)
            return 0

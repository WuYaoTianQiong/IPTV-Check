"""
Repository Pattern for IPTV-Check data access layer
Provides type-safe, testable data access with transaction management.
"""
import json
import logging
from typing import Optional, List, Dict
from datetime import datetime, timedelta

from sqlmodel import SQLModel, Field, Session, select, col, func, text
from sqlalchemy import Index

from iptv_check.infra.database import (
    ChannelModel,
    CheckResultModel,
    CheckHistoryModel,
    FavoriteModel,
)

logger = logging.getLogger(__name__)


class RepositoryBase:
    """Base repository with session management"""
    
    def __init__(self, session: Session):
        self.session = session


class ChannelRepository(RepositoryBase):
    """Repository for channel operations"""
    
    def get_by_url(self, url: str) -> Optional[ChannelModel]:
        return self.session.exec(
            select(ChannelModel).where(ChannelModel.url == url)
        ).first()
    
    def get_by_id(self, channel_id: int) -> Optional[ChannelModel]:
        return self.session.get(ChannelModel, channel_id)
    
    def create(self, channel: ChannelModel) -> ChannelModel:
        self.session.add(channel)
        self.session.flush()
        return channel
    
    def get_all(self) -> List[ChannelModel]:
        return list(self.session.exec(select(ChannelModel)).all())
    
    def count(self) -> int:
        return self.session.exec(select(func.count(ChannelModel.id))).one()


class CheckResultRepository(RepositoryBase):
    """Repository for check result operations"""
    
    def create(self, result: CheckResultModel) -> CheckResultModel:
        self.session.add(result)
        self.session.flush()
        return result
    
    def get_by_channel_and_time(
        self,
        channel_id: int,
        start_time: datetime,
        end_time: Optional[datetime] = None,
    ) -> List[CheckResultModel]:
        query = select(CheckResultModel).where(
            CheckResultModel.channel_id == channel_id,
            CheckResultModel.checked_at >= start_time,
        )
        if end_time:
            query = query.where(CheckResultModel.checked_at <= end_time)
        return list(self.session.exec(query).all())
    
    def get_latest_results(self, cutoff: datetime) -> List[tuple]:
        return list(
            self.session.exec(
                select(CheckResultModel, ChannelModel)
                .join(ChannelModel)
                .where(CheckResultModel.checked_at >= cutoff)
                .order_by(CheckResultModel.checked_at.desc())
            ).all()
        )


class CheckHistoryRepository(RepositoryBase):
    """Repository for check history operations"""
    
    def create(self, history: CheckHistoryModel) -> CheckHistoryModel:
        self.session.add(history)
        self.session.flush()
        return history
    
    def get_latest(self) -> Optional[CheckHistoryModel]:
        return self.session.exec(
            select(CheckHistoryModel).order_by(CheckHistoryModel.created_at.desc()).limit(1)
        ).first()
    
    def get_by_id(self, history_id: int) -> Optional[CheckHistoryModel]:
        return self.session.get(CheckHistoryModel, history_id)
    
    def get_recent(self, limit: int = 20) -> List[CheckHistoryModel]:
        return list(
            self.session.exec(
                select(CheckHistoryModel).order_by(CheckHistoryModel.created_at.desc()).limit(limit)
            ).all()
        )
    
    def count(self) -> int:
        return self.session.exec(select(func.count(CheckHistoryModel.id))).one()


class FavoriteRepository(RepositoryBase):
    """Repository for favorite channels"""
    
    def create(self, favorite: FavoriteModel) -> FavoriteModel:
        self.session.add(favorite)
        self.session.flush()
        return favorite
    
    def get_by_channel_id(self, channel_id: int) -> List[FavoriteModel]:
        return list(
            self.session.exec(
                select(FavoriteModel).where(FavoriteModel.channel_id == channel_id)
            ).all()
        )
    
    def get_all(self) -> List[FavoriteModel]:
        return list(self.session.exec(select(FavoriteModel)).all())


class UnitOfWork:
    """Unit of Work pattern for transaction management"""
    
    def __init__(self, database_manager):
        self.database_manager = database_manager
        self.session: Optional[Session] = None
        
        self.channels: Optional[ChannelRepository] = None
        self.check_results: Optional[CheckResultRepository] = None
        self.check_history: Optional[CheckHistoryRepository] = None
        self.favorites: Optional[FavoriteRepository] = None
    
    def __enter__(self):
        self.session = self.database_manager.get_session()
        self.channels = ChannelRepository(self.session)
        self.check_results = CheckResultRepository(self.session)
        self.check_history = CheckHistoryRepository(self.session)
        self.favorites = FavoriteRepository(self.session)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.session.rollback()
            logger.error("Transaction rolled back due to error: %s", exc_val)
        else:
            self.session.commit()
            logger.debug("Transaction committed successfully")
        self.session.close()
    
    def commit(self):
        self.session.commit()
    
    def rollback(self):
        self.session.rollback()

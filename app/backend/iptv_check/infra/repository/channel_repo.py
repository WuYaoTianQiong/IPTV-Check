"""
Channel Repository
Specialized repository for Channel operations.
"""

from typing import Optional, List
from sqlmodel import Session, select

from iptv_check.infra.repository.base import QueryableRepository
from iptv_check.infra.database import ChannelModel


class ChannelRepository(QueryableRepository[ChannelModel]):
    """Repository for Channel entity operations."""

    def __init__(self, session: Session):
        super().__init__(session, ChannelModel)

    def get_by_url(self, url: str) -> Optional[ChannelModel]:
        """Get channel by URL."""
        statement = select(ChannelModel).where(ChannelModel.url == url)
        return self.session.exec(statement).first()

    def get_by_group(self, group: str) -> List[ChannelModel]:
        """Get all channels in a group."""
        statement = select(ChannelModel).where(ChannelModel.group == group)
        return list(self.session.exec(statement).all())

    def search(self, keyword: str, limit: int = 50) -> List[ChannelModel]:
        """Search channels by name or URL."""
        keyword_lower = keyword.lower()
        statement = select(ChannelModel).where(
            ChannelModel.name.contains(keyword_lower) |
            ChannelModel.url.contains(keyword_lower)
        ).limit(limit)
        return list(self.session.exec(statement).all())

    def get_groups(self) -> List[str]:
        """Get all unique channel groups."""
        statement = select(ChannelModel.group).distinct()
        return [g for g in self.session.exec(statement).all() if g]

"""
Favorite Repository
数据访问层：封装 favorites / favorite_folders 的查询与更新，
供 router 层使用，避免业务层直接书写原生 SQL。
"""
from typing import Dict, List, Optional, Tuple

from sqlalchemy import case as sa_case, update as sa_update
from sqlmodel import Session, select, func

from iptv_check.infra.database import FavoriteModel, FavoriteFolderModel
from iptv_check.infra.repository.base import QueryableRepository


class FavoriteRepository(QueryableRepository[FavoriteModel]):
    """Repository for Favorite entity operations."""

    def __init__(self, session: Session):
        super().__init__(session, FavoriteModel)

    def list_paginated(
        self, folder_id: Optional[int], page: int, per_page: int, sort: str = "default"
    ) -> Tuple[List[FavoriteModel], int]:
        """分页查询收藏（folder_id=None 表示全部/未分类）。"""
        stmt = select(FavoriteModel)
        if folder_id is not None:
            stmt = stmt.where(FavoriteModel.folder_id == folder_id)

        total = self.session.exec(select(func.count()).select_from(stmt.subquery())).one()

        order_by = {
            "default": (FavoriteModel.sort_order.asc(), FavoriteModel.created_at.desc()),
            "name_asc": (FavoriteModel.name.asc(),),
            "name_desc": (FavoriteModel.name.desc(),),
            "latency_asc": (
                sa_case(
                    (FavoriteModel.latency.is_(None) | (FavoriteModel.latency < 0), 999999),
                    else_=FavoriteModel.latency,
                ).asc(),
            ),
            "latency_desc": (FavoriteModel.latency.desc(),),
        }.get(sort, (FavoriteModel.sort_order.asc(), FavoriteModel.created_at.desc()))

        items = self.session.exec(
            stmt.order_by(*order_by).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total

    def fetch_all_urls(self) -> List[dict]:
        """获取所有非空 URL 的收藏（用于延迟检测）。"""
        rows = self.session.exec(
            select(FavoriteModel.id, FavoriteModel.url, FavoriteModel.name).where(FavoriteModel.url != "")
        ).all()
        return [{"id": r[0], "url": r[1], "name": r[2]} for r in rows]

    def update_latency_batch(self, updates: List[Tuple[int, float]], ts) -> int:
        """批量更新收藏延迟，返回更新条数。"""
        for fav_id, latency in updates:
            self.session.execute(
                sa_update(FavoriteModel)
                .where(FavoriteModel.id == fav_id)
                .values(latency=latency, latency_updated_at=ts)
            )
        self.session.commit()
        return len(updates)

    def list_folders_with_counts(self) -> Tuple[List[FavoriteFolderModel], Dict]:
        """列出收藏夹及其收藏数（folder_id=None 的计数归入未分类）。"""
        folders = self.session.exec(
            select(FavoriteFolderModel).order_by(FavoriteFolderModel.sort_order)
        ).all()
        count_map: Dict[Optional[int], int] = {}
        for folder_id, cnt in self.session.exec(
            select(FavoriteModel.folder_id, func.count()).group_by(FavoriteModel.folder_id)
        ).all():
            count_map[folder_id] = cnt
        return list(folders), count_map

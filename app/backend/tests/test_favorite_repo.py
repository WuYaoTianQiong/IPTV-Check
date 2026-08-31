"""
FavoriteRepository 单元测试
验证收藏分页/排序/文件夹计数/延迟批量更新等数据访问逻辑。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlmodel import Session, SQLModel, create_engine

from iptv_check.infra.database import FavoriteModel, FavoriteFolderModel
from iptv_check.infra.repository.favorite_repo import FavoriteRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
        s.close()


def _mk_fav(name, url, folder_id=None, sort_order=0, latency=-1.0):
    from iptv_check.infra.cn_time import cn_now
    return FavoriteModel(
        name=name, url=url, folder_id=folder_id,
        sort_order=sort_order, latency=latency,
        created_at=cn_now(),
    )


def test_list_paginated_default_order(session):
    session.add(_mk_fav("A", "http://a", sort_order=0))
    session.add(_mk_fav("B", "http://b", sort_order=1))
    session.commit()

    items, total = FavoriteRepository(session).list_paginated(None, 1, 50, "default")
    assert total == 2
    assert [f.name for f in items] == ["A", "B"]


def test_list_paginated_folder_filter(session):
    session.add(_mk_fav("A", "http://a", folder_id=1))
    session.add(_mk_fav("B", "http://b", folder_id=2))
    session.commit()

    items, total = FavoriteRepository(session).list_paginated(1, 1, 50, "default")
    assert total == 1
    assert items[0].name == "A"


def test_list_paginated_paging(session):
    for i in range(5):
        session.add(_mk_fav(f"ch{i}", f"http://{i}"))
    session.commit()

    items, total = FavoriteRepository(session).list_paginated(None, 2, 2, "default")
    assert total == 5
    assert len(items) == 2


def test_list_paginated_latency_sort(session):
    session.add(_mk_fav("slow", "http://s", latency=800))
    session.add(_mk_fav("fast", "http://f", latency=50))
    session.add(_mk_fav("dead", "http://d", latency=-1))
    session.commit()

    items, _ = FavoriteRepository(session).list_paginated(None, 1, 50, "latency_asc")
    assert [f.name for f in items] == ["fast", "slow", "dead"]


def test_list_paginated_name_sort(session):
    session.add(_mk_fav("Zebra", "http://z"))
    session.add(_mk_fav("Alpha", "http://a"))
    session.commit()

    items, _ = FavoriteRepository(session).list_paginated(None, 1, 50, "name_asc")
    assert [f.name for f in items] == ["Alpha", "Zebra"]


def test_fetch_all_urls(session):
    session.add(_mk_fav("A", "http://a"))
    session.add(_mk_fav("empty", ""))
    session.commit()

    urls = FavoriteRepository(session).fetch_all_urls()
    assert len(urls) == 1
    assert urls[0]["url"] == "http://a"


def test_update_latency_batch(session):
    fav = _mk_fav("A", "http://a", latency=-1)
    session.add(fav)
    session.commit()

    from iptv_check.infra.cn_time import cn_now
    n = FavoriteRepository(session).update_latency_batch([(fav.id, 123)], cn_now())
    assert n == 1

    session.refresh(fav)
    assert fav.latency == 123


def test_list_folders_with_counts(session):
    session.add(FavoriteFolderModel(name="央视", sort_order=0))
    session.add(_mk_fav("A", "http://a", folder_id=1))
    session.add(_mk_fav("B", "http://b", folder_id=1))
    session.add(_mk_fav("C", "http://c"))
    session.commit()

    folders, count_map = FavoriteRepository(session).list_folders_with_counts()
    assert len(folders) == 1
    assert count_map.get(1) == 2
    assert count_map.get(None) == 1

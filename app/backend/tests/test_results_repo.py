"""
ResultsRepository 单元测试
验证检测结果会话（channel_results / check_events）的查询与更新逻辑。
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

from iptv_check.infra.cn_time import cn_now
from iptv_check.infra.persistence.event_store import CheckEventModel, ChannelResultModel
from iptv_check.infra.repository.results_repo import ResultsRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
        s.close()


def _mk_result(sid, name, url, latency=-1.0, is_valid=0, tier="invalid", created_at=None):
    return ChannelResultModel(
        session_id=sid, name=name, url=url,
        latency=latency, is_valid=is_valid, quality_tier=tier,
        created_at=created_at or cn_now(),
    )


def _mk_event(sid, url, latency=-1.0, is_valid=False, tier="invalid"):
    return CheckEventModel(
        event_type="channel_checked",
        payload=json.dumps({"url": url, "latency": latency, "is_valid": is_valid, "quality_tier": tier}, ensure_ascii=False),
        session_id=sid,
    )


def test_latest_session_id(session):
    base = datetime.now()
    session.add(_mk_result("old", "A", "http://a", created_at=base))
    session.add(_mk_result("new", "B", "http://b", created_at=base + timedelta(seconds=1)))
    session.commit()
    assert ResultsRepository(session).latest_session_id() == "new"


def test_has_session_data(session):
    repo = ResultsRepository(session)
    assert repo.has_session_data("s1") is False
    session.add(_mk_result("s1", "A", "http://a"))
    session.commit()
    assert repo.has_session_data("s1") is True


def test_fetch_session_urls_merge(session):
    session.add(_mk_result("s1", "A", "http://a"))
    session.add(_mk_result("s1", "B", "http://b"))
    session.add(_mk_event("s1", "http://c"))
    session.add(_mk_event("s1", "http://a"))  # 与物化表重复
    session.commit()
    urls = ResultsRepository(session).fetch_session_urls("s1")
    assert set(urls) == {"http://a", "http://b", "http://c"}


def test_reset_session_latency_full(session):
    r = _mk_result("s1", "A", "http://a", latency=50, is_valid=1, tier="valid")
    session.add(r)
    e = _mk_event("s1", "http://a", latency=50, is_valid=True, tier="valid")
    session.add(e)
    session.commit()

    ResultsRepository(session).reset_session_latency("s1")

    session.refresh(r)
    assert r.latency == -1 and r.is_valid == 0 and r.quality_tier == "invalid"
    session.refresh(e)
    p = json.loads(e.payload)
    assert p["latency"] == -1 and p["is_valid"] is False and p["quality_tier"] == "invalid"


def test_reset_session_latency_subset(session):
    r1 = _mk_result("s1", "A", "http://a", latency=50, is_valid=1, tier="valid")
    r2 = _mk_result("s1", "B", "http://b", latency=60, is_valid=1, tier="valid")
    session.add(r1)
    session.add(r2)
    session.commit()

    ResultsRepository(session).reset_session_latency("s1", ["http://a"])

    session.refresh(r1)
    session.refresh(r2)
    assert r1.latency == -1 and r1.is_valid == 0
    assert r2.latency == 60 and r2.is_valid == 1


def test_update_channel_result_and_event(session):
    r = _mk_result("s1", "A", "http://a")
    session.add(r)
    e = _mk_event("s1", "http://a")
    session.add(e)
    session.commit()

    repo = ResultsRepository(session)
    repo.update_channel_result("s1", "http://a", 123, True, "valid")
    repo.update_event_payload_latency("s1", "http://a", 123, True, "valid")
    session.commit()

    session.refresh(r)
    assert r.latency == 123 and r.is_valid == 1 and r.quality_tier == "valid"
    session.refresh(e)
    p = json.loads(e.payload)
    assert p["latency"] == 123 and p["is_valid"] is True and p["quality_tier"] == "valid"

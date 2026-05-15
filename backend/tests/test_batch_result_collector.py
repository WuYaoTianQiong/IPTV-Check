import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.infra.batch_result_collector import BatchResultCollector, CheckProgress
from iptv_check.infra.persistence.event_store import EventStore


@pytest.fixture
def tmp_event_store(tmp_path):
    db_path = str(tmp_path / "test_events.db")
    return EventStore(db_path=db_path)


@pytest.fixture
def broadcast_collector():
    messages = []

    async def broadcast_fn(event, data):
        messages.append((event, data))

    return broadcast_fn, messages


class TestCheckProgress:
    def test_empty_progress(self):
        p = CheckProgress()
        assert p.total == 0
        assert p.checked == 0
        assert p.progress_percent == 0.0

    def test_progress_calculation(self):
        p = CheckProgress(total=100, checked=25, valid=20, invalid=5)
        assert p.progress_percent == 25.0
        d = p.to_dict()
        assert d["total"] == 100
        assert d["checked"] == 25
        assert d["valid"] == 20
        assert d["invalid"] == 5


class TestBatchResultCollector:
    async def test_basic_flow(self, tmp_event_store, broadcast_collector):
        broadcast_fn, messages = broadcast_collector
        collector = BatchResultCollector(
            event_store=tmp_event_store,
            broadcast_fn=broadcast_fn,
            batch_size=2,
            flush_interval=1.0,
            session_id="test_001",
        )
        await collector.start()

        await collector.submit_result({"name": "ch1", "is_valid": True, "latency": 50, "speed": "100", "details": "OK"})
        await collector.submit_result({"name": "ch2", "is_valid": False, "latency": 0, "speed": "-", "details": "超时"})
        await collector.submit_complete()

        await collector.wait_for_complete()

        progress = collector.get_progress_dict()
        assert progress["total"] == 0
        assert progress["checked"] == 2
        assert progress["valid"] == 1
        assert progress["invalid"] == 1

        events = tmp_event_store.get_events(session_id="test_001", event_type="channel_checked")
        assert len(events) == 2

        complete_msgs = [m for m in messages if m[0] == "check_completed"]
        assert len(complete_msgs) == 1
        assert complete_msgs[0][1]["valid"] == 1
        assert complete_msgs[0][1]["invalid"] == 1

    async def test_progress_snapshot(self, tmp_event_store, broadcast_collector):
        broadcast_fn, messages = broadcast_collector
        collector = BatchResultCollector(
            event_store=tmp_event_store,
            broadcast_fn=broadcast_fn,
            batch_size=3,
            flush_interval=0.5,
            session_id="test_002",
        )
        await collector.start()

        collector.set_total(100)

        for i in range(5):
            await collector.submit_result({"name": f"ch{i}", "is_valid": True, "latency": 50, "speed": "100", "details": "OK"})

        await asyncio.sleep(1.0)

        progress = collector.get_progress_dict()
        assert progress["total"] == 100
        assert progress["checked"] == 5
        assert progress["valid"] == 5

        progress_msgs = [m for m in messages if m[0] == "progress_update"]
        assert len(progress_msgs) >= 1
        assert progress_msgs[-1][1]["checked"] == 5

    async def test_stop_with_remaining(self, tmp_event_store, broadcast_collector):
        broadcast_fn, messages = broadcast_collector
        collector = BatchResultCollector(
            event_store=tmp_event_store,
            broadcast_fn=broadcast_fn,
            batch_size=100,
            flush_interval=10.0,
            session_id="test_003",
        )
        await collector.start()

        collector.set_total(50)

        for i in range(10):
            await collector.submit_result({"name": f"ch{i}", "is_valid": i % 2 == 0, "latency": 50, "speed": "100", "details": "OK"})

        await collector.stop()

        progress = collector.get_progress_dict()
        assert progress["checked"] == 10
        assert progress["valid"] == 5
        assert progress["invalid"] == 5

        events = tmp_event_store.get_events(session_id="test_003", event_type="channel_checked")
        assert len(events) == 10

        complete_msgs = [m for m in messages if m[0] == "check_completed"]
        assert len(complete_msgs) == 1

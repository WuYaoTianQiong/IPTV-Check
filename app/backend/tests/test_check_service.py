"""
CheckService 核心流程测试
覆盖检测启动、阶段广播、进度统计、停止等关键路径
"""
import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, AsyncMock
from iptv_check.application.services.check_service import CheckService
from iptv_check.models.settings import CheckConfig


class TestCheckService:
    """测试 CheckService 核心功能"""

    @pytest.fixture
    def mock_dependencies(self):
        """创建模拟依赖"""
        event_store = MagicMock()
        event_store.new_session.return_value = "test-session-001"
        event_store.append = AsyncMock()

        read_model = MagicMock()
        read_model.get_check_progress.return_value = {
            "total": 0, "checked": 0, "valid": 0, "invalid": 0, "is_running": False
        }
        read_model.get_full_state.return_value = {"phase": "idle", "metrics": {}}

        check_engine = MagicMock()
        check_engine.start = MagicMock()
        check_engine.stop = MagicMock()

        broadcast_log = []
        async def broadcast_fn(event, data):
            broadcast_log.append((event, data))

        return {
            "event_store": event_store,
            "read_model": read_model,
            "check_engine": check_engine,
            "broadcast_fn": broadcast_fn,
            "broadcast_log": broadcast_log,
        }

    @pytest.fixture
    def service(self, mock_dependencies):
        return CheckService(
            event_store=mock_dependencies["event_store"],
            read_model=mock_dependencies["read_model"],
            check_engine=mock_dependencies["check_engine"],
            broadcast_fn=mock_dependencies["broadcast_fn"],
        )

    @pytest.mark.asyncio
    async def test_start_check_creates_session(self, service, mock_dependencies):
        """启动检测应创建新会话并广播事件"""
        req = MagicMock()
        req.file_paths = []
        req.online_source_ids = []
        req.timeout_connect = 3
        req.timeout_read = 8
        req.max_threads = 80
        req.run_speed_test = True
        req.use_cache = True

        await service.start_check(req)

        assert service.session_id == "test-session-001"
        assert service.is_running is True

        broadcast_log = mock_dependencies["broadcast_log"]
        events = [e for e, _ in broadcast_log]
        assert "check_started" in events
        assert "stage_changed" in events

        # 验证 stage_changed 包含 parsing 阶段
        stage_events = [d for e, d in broadcast_log if e == "stage_changed"]
        assert any(d.get("stage") == "parsing" for d in stage_events)

    def test_get_progress_no_collector(self, service, mock_dependencies):
        """无 collector 时应从 read_model 获取进度"""
        progress = service.get_progress()
        mock_dependencies["read_model"].get_check_progress.assert_called_once()

    def test_session_id_property(self, service):
        """session_id 属性应正确返回"""
        assert service.session_id == ""

    @pytest.mark.asyncio
    async def test_stop_check_not_running(self, service):
        """停止未运行的检测应静默返回"""
        await service.stop_check()
        assert service.is_running is False

    @pytest.mark.asyncio
    async def test_get_full_state(self, service, mock_dependencies):
        """应委托给 read_model 获取完整状态"""
        state = service.get_full_state()
        mock_dependencies["read_model"].get_full_state.assert_called_once()


class TestCheckServiceConcurrency:
    """测试 CheckService 并发安全"""

    @pytest.fixture
    def service(self):
        event_store = MagicMock()
        event_store.new_session.return_value = "session-concurrent"
        event_store.append = AsyncMock()

        read_model = MagicMock()
        check_engine = MagicMock()

        async def broadcast_fn(event, data):
            pass

        return CheckService(
            event_store=event_store,
            read_model=read_model,
            check_engine=check_engine,
            broadcast_fn=broadcast_fn,
        )

    @pytest.mark.asyncio
    async def test_double_start_raises(self, service):
        """重复启动应抛出 RuntimeError"""
        req = MagicMock()
        req.file_paths = []
        req.online_source_ids = []
        req.timeout_connect = 3
        req.timeout_read = 8
        req.max_threads = 80
        req.run_speed_test = True
        req.use_cache = True

        await service.start_check(req)

        with pytest.raises(RuntimeError, match="检测正在进行中"):
            await service.start_check(req)

        assert service.is_running is True

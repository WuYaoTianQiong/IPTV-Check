"""
API 路由层测试
覆盖 /api/report, /api/export, /api/results, /api/check/* 等核心端点
使用内存 SQLite + FastAPI TestClient
"""
import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch


class TestReportAPI:
    """测试 /api/report 端点"""

    @pytest.fixture
    def client(self, tmp_path):
        from iptv_check.server.app import create_app, AppState

        AppState.reset_instance()
        app = create_app()

        with TestClient(app) as client:
            yield client

        AppState.reset_instance()

    def test_report_no_session(self, client):
        """无检测会话时应返回友好错误而非 500"""
        resp = client.get("/api/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_report_with_mock_data(self, client, monkeypatch):
        """有检测数据时应返回完整报告"""
        from iptv_check.server.app import app_state

        mock_read_model = MagicMock()
        mock_read_model.get_checked_results_raw.return_value = [
            {
                "channel": {"name": "CCTV1", "url": "http://test/1", "group": "央视", "sources": ["源A"]},
                "is_valid": True,
                "latency": 30,
                "speed": "1000",
                "details": "OK",
            },
            {
                "channel": {"name": "CCTV2", "url": "http://test/2", "group": "央视", "sources": ["源A"]},
                "is_valid": False,
                "latency": -1,
                "speed": "-",
                "details": "超时",
            },
        ]

        mock_service = MagicMock()
        mock_service.session_id = "test-session-123"

        monkeypatch.setattr(app_state, "read_model", mock_read_model)
        monkeypatch.setattr(app_state, "_check_service", mock_service)

        resp = client.get("/api/report")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["valid"] == 1
        assert data["invalid"] == 1
        assert data["valid_rate"] == 50.0
        assert "latency_distribution" in data
        assert "source_ranking" in data
        assert "group_stats" in data

    def test_report_with_corrupt_data(self, client, monkeypatch):
        """数据异常时应优雅处理而非 500"""
        from iptv_check.server.app import app_state

        mock_read_model = MagicMock()
        mock_read_model.get_checked_results_raw.return_value = [
            {
                "channel": {},  # 缺少关键字段
                "is_valid": True,
                "latency": "invalid",  # 非数字
            },
        ]

        mock_service = MagicMock()
        mock_service.session_id = "test-session"

        monkeypatch.setattr(app_state, "read_model", mock_read_model)
        monkeypatch.setattr(app_state, "_check_service", mock_service)

        resp = client.get("/api/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" not in data or "没有有效的检测结果" in data.get("error", "")


class TestExportAPI:
    """测试 /api/export 端点"""

    @pytest.fixture
    def client(self):
        from iptv_check.server.app import create_app, AppState

        AppState.reset_instance()
        app = create_app()

        with TestClient(app) as client:
            yield client

        AppState.reset_instance()

    def test_export_no_session(self, client):
        """无检测会话时应返回 400 而非 500"""
        resp = client.post("/api/export", json={"format": "m3u"})
        assert resp.status_code == 400
        assert "没有检测结果" in resp.json()["detail"]

    def test_export_with_mock_data(self, client, monkeypatch):
        """有数据时应正常导出"""
        from iptv_check.server.app import app_state

        mock_read_model = MagicMock()
        mock_read_model.get_checked_results_raw.return_value = [
            {
                "channel": {"name": "CCTV1", "url": "http://test/1", "group": "央视", "sources": ["源A"]},
                "is_valid": True,
                "latency": 30,
                "speed": "1000",
                "details": "OK",
            },
        ]

        mock_service = MagicMock()
        mock_service.session_id = "test-session"

        mock_export_engine = MagicMock()
        mock_export_engine.export_batch.return_value = {"m3u": "/path/to/file.m3u"}

        monkeypatch.setattr(app_state, "read_model", mock_read_model)
        monkeypatch.setattr(app_state, "_check_service", mock_service)
        monkeypatch.setattr(app_state, "export_engine", mock_export_engine)
        monkeypatch.setattr(app_state, "local_isp", "电信")

        resp = client.post("/api/export", json={"format": "m3u"})
        assert resp.status_code == 200
        data = resp.json()
        assert "exported" in data
        assert "dir" in data


class TestResultsAPI:
    """测试 /api/results 端点"""

    @pytest.fixture
    def client(self):
        from iptv_check.server.app import create_app, AppState

        AppState.reset_instance()
        app = create_app()

        with TestClient(app) as client:
            yield client

        AppState.reset_instance()

    def test_results_empty(self, client):
        """无数据时应返回空列表"""
        resp = client.get("/api/results")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_results_pagination(self, client):
        """分页参数应正确传递"""
        resp = client.get("/api/results?page=2&per_page=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 2
        assert data["per_page"] == 10


class TestCheckAPI:
    """测试 /api/check/* 端点"""

    @pytest.fixture
    def client(self):
        from iptv_check.server.app import create_app, AppState

        AppState.reset_instance()
        app = create_app()

        with TestClient(app) as client:
            yield client

        AppState.reset_instance()

    def test_check_start_no_service(self, client):
        """服务未初始化时应返回 500"""
        resp = client.post("/api/check/start", json={})
        assert resp.status_code == 500

    def test_check_stop_no_running(self, client):
        """无运行中检测时应返回 400"""
        resp = client.post("/api/check/stop")
        assert resp.status_code == 400
        assert "没有正在进行的检测" in resp.json()["detail"]

    def test_check_state_idle(self, client):
        """空闲状态应返回正确结构"""
        resp = client.get("/api/check/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "phase" in data
        assert data.get("phase") == "idle"

    def test_results_stats_empty(self, client):
        """无检测时应返回零值"""
        resp = client.get("/api/results/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["checked"] == 0
        assert data["valid"] == 0
        assert data["invalid"] == 0
        assert data["is_running"] is False

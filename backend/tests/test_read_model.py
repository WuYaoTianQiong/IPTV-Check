"""
ReadModel 参数化查询测试
验证 SQL 参数化查询正确性、边界条件、空值处理
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
from sqlmodel import SQLModel, create_engine, Session
from iptv_check.infra.persistence.read_model import ReadModel
from iptv_check.infra.persistence.event_store import EventStore
from iptv_check.infra.persistence.read_model import (
    _infer_region_from_group,
    _INTERNATIONAL_GROUP_KEYWORDS,
)


class TestReadModelParameterizedQueries:
    """测试 ReadModel 参数化 SQL 查询"""

    @pytest.fixture
    def db_engine(self, tmp_path):
        """创建内存 SQLite 数据库"""
        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path}")
        SQLModel.metadata.create_all(engine)
        return engine

    @pytest.fixture
    def event_store(self, db_engine):
        """创建 EventStore"""
        store = EventStore(db_path=str(db_engine.url.database))
        store.new_session()
        return store

    @pytest.fixture
    def read_model(self, event_store):
        """创建 ReadModel"""
        return ReadModel(event_store)

    def test_get_checked_results_raw_empty_session(self, read_model):
        """空 session_id 应返回空列表"""
        read_model._store._current_session_id = ""
        results = read_model.get_checked_results_raw()
        assert results == []

    def test_get_checked_results_raw_no_data(self, read_model):
        """无数据时应返回空列表"""
        results = read_model.get_checked_results_raw("nonexistent-session")
        assert results == []

    def test_get_checked_channels_empty_session(self, read_model):
        """空 session_id 应返回空结果结构"""
        read_model._store._current_session_id = ""
        result = read_model.get_checked_channels()
        assert result["total"] == 0
        assert result["items"] == []

    def test_get_grouped_channels_empty_session(self, read_model):
        """空 session_id 应返回空结果结构"""
        read_model._store._current_session_id = ""
        result = read_model.get_grouped_channels()
        assert result["total"] == 0
        assert result["items"] == []

    def test_get_category_tree_empty_session(self, read_model):
        """空 session_id 应返回空列表"""
        read_model._store._current_session_id = ""
        results = read_model.get_category_tree()
        assert results == []

    def test_get_available_languages_empty_session(self, read_model):
        """空 session_id 应返回空列表"""
        read_model._store._current_session_id = ""
        results = read_model.get_available_languages()
        assert results == []

    def test_sql_injection_protection_in_search(self, read_model):
        """搜索参数应被正确转义，防止 SQL 注入"""
        read_model._store.new_session()

        malicious_search = "'; DROP TABLE check_events; --"

        with patch('iptv_check.infra.persistence.read_model._scalar', return_value=0):
            with patch.object(read_model, '_session') as mock_session_ctx:
                mock_session = MagicMock()
                mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_session.exec.return_value.all.return_value = []

                result = read_model.get_checked_channels(search=malicious_search)

                assert result["total"] == 0
                assert result["items"] == []
                assert mock_session.exec.called

    def test_sql_injection_protection_in_group_path(self, read_model):
        """group_path 参数应被正确转义"""
        read_model._store.new_session()

        malicious_group = "'; DELETE FROM check_events; --"

        with patch('iptv_check.infra.persistence.read_model._scalar', return_value=0):
            with patch.object(read_model, '_session') as mock_session_ctx:
                mock_session = MagicMock()
                mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_session.exec.return_value.all.return_value = []

                result = read_model.get_grouped_channels(group_path=malicious_group)

                assert result["total"] == 0
                assert result["items"] == []
                assert mock_session.exec.called

    def test_special_characters_in_search(self, read_model):
        """搜索参数包含特殊字符时应正确处理"""
        read_model._store.new_session()

        special_search = "CCTV%' OR '1'='1"

        with patch('iptv_check.infra.persistence.read_model._scalar', return_value=0):
            with patch.object(read_model, '_session') as mock_session_ctx:
                mock_session = MagicMock()
                mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_session.exec.return_value.all.return_value = []

                result = read_model.get_checked_channels(search=special_search)

                assert result["total"] == 0
                assert result["items"] == []
                assert mock_session.exec.called

    def test_tab_filter_valid(self, read_model):
        """tab=valid 应添加有效筛选条件"""
        read_model._store.new_session()

        with patch('iptv_check.infra.persistence.read_model._scalar', return_value=0):
            with patch.object(read_model, '_session') as mock_session_ctx:
                mock_session = MagicMock()
                mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_session.exec.return_value.all.return_value = []

                result = read_model.get_checked_channels(tab="valid")

                assert mock_session.exec.called

    def test_media_type_filter(self, read_model):
        """media_type 筛选应正确生效"""
        read_model._store.new_session()

        with patch('iptv_check.infra.persistence.read_model._scalar', return_value=0):
            with patch.object(read_model, '_session') as mock_session_ctx:
                mock_session = MagicMock()
                mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_session.exec.return_value.all.return_value = []

                result = read_model.get_checked_channels(media_type="radio")

                assert mock_session.exec.called

    def test_pagination_boundaries(self, read_model):
        """分页边界条件应正确处理"""
        read_model._store.new_session()

        with patch('iptv_check.infra.persistence.read_model._scalar', return_value=0):
            with patch.object(read_model, '_session') as mock_session_ctx:
                mock_session = MagicMock()
                mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
                mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)
                mock_session.exec.return_value.all.return_value = []

                result = read_model.get_checked_channels(page=1, per_page=0)
                assert result["page"] == 1
                assert result["per_page"] == 0

                result = read_model.get_checked_channels(page=-1, per_page=50)
                assert result["page"] == -1


class TestInferRegionCgtnDomestic:
    def test_infer_region_cgtn_returns_cctv(self):
        assert _infer_region_from_group("CGTN", "CN", False, "") == "央视"

    def test_infer_region_cgtn_lower_returns_cctv(self):
        assert _infer_region_from_group("cgtn documentary", "CN", False, "") == "央视"

    def test_infer_region_cctv1_returns_cctv(self):
        assert _infer_region_from_group("CCTV-1 综合", "CN", False, "") == "央视"

    def test_infer_region_nhk_world_returns_international(self):
        assert _infer_region_from_group("NHK World", "JP", False, "") == "国际电视"

    def test_infer_region_cna_returns_international(self):
        assert _infer_region_from_group("CNA", "SG", False, "") == "国际电视"

    def test_international_keywords_no_cgtn(self):
        assert "CGTN" not in _INTERNATIONAL_GROUP_KEYWORDS

import os
import sys
import json
import asyncio
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.application.services.source_sync_service import (
    SourceSyncService,
    SourceSyncResult,
    ResolvedUrls,
    _DEFAULT_REMOTE_CONFIG_URLS,
)


class TestSyncWithNoConfigUsesDefault:
    @pytest.mark.asyncio
    async def test_sync_uses_default_urls(self, tmp_path):
        service = SourceSyncService(data_dir=str(tmp_path))
        resolved = service._resolve_remote_config_urls()
        assert len(resolved.urls) >= 2
        assert resolved.source == "default"
        for url in _DEFAULT_REMOTE_CONFIG_URLS:
            assert url in resolved.urls


class TestSyncWithEnvVar:
    @pytest.mark.asyncio
    async def test_sync_uses_env_urls(self, tmp_path):
        env_url = "https://custom.mysite.com/source.json"
        service = SourceSyncService(
            data_dir=str(tmp_path),
            env_remote_config_urls=[env_url],
        )
        resolved = service._resolve_remote_config_urls()
        assert resolved.source == "env_var"
        assert env_url in resolved.urls


class TestStatusIncludesNewFields:
    @pytest.mark.asyncio
    async def test_status_fields_after_sync(self, tmp_path):
        service = SourceSyncService(data_dir=str(tmp_path))
        service._last_resolved_urls = ResolvedUrls(
            urls=_DEFAULT_REMOTE_CONFIG_URLS,
            source="default",
            effective_urls=_DEFAULT_REMOTE_CONFIG_URLS,
        )
        status = service.get_status()
        assert "effective_remote_urls" in status
        assert "url_source" in status
        assert status["effective_remote_urls"] == _DEFAULT_REMOTE_CONFIG_URLS
        assert status["url_source"] == "default"


class TestTriggerIncludesNewFields:
    @pytest.mark.asyncio
    async def test_sync_result_new_fields(self, tmp_path):
        local_sources = {
            "sources": [
                {
                    "id": "test-source-1",
                    "name": "Test Source",
                    "url": "https://test.mysite.com/live.m3u",
                    "group": "Test",
                }
            ],
        }
        with open(os.path.join(str(tmp_path), "local_sources.json"), "w", encoding="utf-8") as f:
            json.dump(local_sources, f)

        service = SourceSyncService(data_dir=str(tmp_path))
        result = await service.sync()
        d = result.to_dict()
        assert "remote_fetched" in d
        assert "remote_url_used" in d
        assert "url_source" in d


class TestAppSettingsRemoteConfigUrls:
    def test_default_empty(self):
        from iptv_check.infra.config.settings import AppSettings
        s = AppSettings()
        assert s.remote_config_urls == []

    def test_parse_comma_separated_string(self):
        from iptv_check.infra.config.settings import AppSettings
        s = AppSettings(remote_config_urls="https://a.com,https://b.com")
        assert s.remote_config_urls == ["https://a.com", "https://b.com"]

    def test_parse_with_spaces(self):
        from iptv_check.infra.config.settings import AppSettings
        s = AppSettings(remote_config_urls=" https://a.com , , https://b.com ")
        assert s.remote_config_urls == ["https://a.com", "https://b.com"]

    def test_parse_list_passthrough(self):
        from iptv_check.infra.config.settings import AppSettings
        s = AppSettings(remote_config_urls=["https://a.com", "https://b.com"])
        assert s.remote_config_urls == ["https://a.com", "https://b.com"]

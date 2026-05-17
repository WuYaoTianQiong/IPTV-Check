import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from iptv_check.application.services.source_sync_service import (
    SourceSyncService,
    SourceSyncResult,
    ResolvedUrls,
    _DEFAULT_REMOTE_CONFIG_URLS,
    _classify_channel,
    _INVALID_GROUP_KEYWORDS,
)


class TestValidateUrl:
    def test_validate_url_valid_http(self):
        assert SourceSyncService._validate_url("http://github.com/user/repo/source.json") is True

    def test_validate_url_valid_https(self):
        assert SourceSyncService._validate_url("https://github.com/user/repo/source.json") is True

    def test_validate_url_invalid_protocol_ftp(self):
        assert SourceSyncService._validate_url("ftp://server.com/source.json") is False

    def test_validate_url_invalid_protocol_file(self):
        assert SourceSyncService._validate_url("file:///etc/passwd") is False

    def test_validate_url_placeholder_your_username(self):
        assert SourceSyncService._validate_url("https://your-username.github.io/repo/source.json") is False

    def test_validate_url_placeholder_example(self):
        assert SourceSyncService._validate_url("https://example.com/source.json") is False

    def test_validate_url_empty(self):
        assert SourceSyncService._validate_url("") is False

    def test_validate_url_none(self):
        assert SourceSyncService._validate_url(None) is False


class TestRedactUrlForLog:
    def test_redact_url_no_sensitive(self):
        url = "https://cdn.jsdelivr.net/gh/user/repo@main/source.json"
        assert SourceSyncService._redact_url_for_log(url) == url

    def test_redact_url_with_token(self):
        url = "https://api.server.com/source.json?token=secret123"
        result = SourceSyncService._redact_url_for_log(url)
        assert "secret123" not in result
        assert "token=***" in result

    def test_redact_url_with_key(self):
        url = "https://api.server.com/source.json?key=abc123&foo=bar"
        result = SourceSyncService._redact_url_for_log(url)
        assert "abc123" not in result
        assert "key=***" in result
        assert "foo=bar" in result

    def test_redact_url_multiple_params(self):
        url = "https://api.server.com/source.json?token=mytoken&page=1&password=mypass"
        result = SourceSyncService._redact_url_for_log(url)
        assert "mytoken" not in result
        assert "mypass" not in result
        assert "page=1" in result

    def test_redact_url_no_query(self):
        url = "https://cdn.jsdelivr.net/gh/user/repo@main/source.json"
        assert SourceSyncService._redact_url_for_log(url) == url


class TestSourceSyncResultNewFields:
    def test_to_dict_contains_new_fields(self):
        result = SourceSyncResult()
        d = result.to_dict()
        assert "remote_fetched" in d
        assert "remote_url_used" in d
        assert "url_source" in d
        assert d["remote_fetched"] is False
        assert d["remote_url_used"] is None
        assert d["url_source"] is None

    def test_to_dict_existing_fields_unchanged(self):
        result = SourceSyncResult()
        d = result.to_dict()
        assert d["success"] is False
        assert d["added"] == 0
        assert d["updated"] == 0
        assert d["unchanged"] == 0
        assert d["errors"] == []


class TestResolvedUrls:
    def test_dataclass_instantiation(self):
        ru = ResolvedUrls(urls=["http://a.com"], source="default", effective_urls=["http://a.com"])
        assert ru.urls == ["http://a.com"]
        assert ru.source == "default"
        assert ru.effective_urls == ["http://a.com"]


class TestResolveRemoteConfigUrls:
    @pytest.fixture
    def service(self, tmp_path):
        return SourceSyncService(data_dir=str(tmp_path))

    def test_resolve_urls_default_only(self, service):
        resolved = service._resolve_remote_config_urls()
        assert len(resolved.urls) > 0
        assert resolved.source == "default"
        for url in _DEFAULT_REMOTE_CONFIG_URLS:
            assert url in resolved.urls

    def test_resolve_urls_env_only(self, tmp_path):
        env_urls = ["https://custom1.com/source.json", "https://custom2.com/source.json"]
        service = SourceSyncService(data_dir=str(tmp_path), env_remote_config_urls=env_urls)
        resolved = service._resolve_remote_config_urls()
        assert resolved.source == "env_var"
        assert env_urls[0] in resolved.urls
        assert env_urls[1] in resolved.urls

    def test_resolve_urls_api_param_highest(self, tmp_path):
        api_url = "https://api.mysite.com/source.json"
        env_urls = ["https://env.mysite.com/source.json"]
        service = SourceSyncService(data_dir=str(tmp_path), env_remote_config_urls=env_urls)
        resolved = service._resolve_remote_config_urls(api_remote_url=api_url)
        assert resolved.urls[0] == api_url
        assert resolved.source == "api_param"

    def test_resolve_urls_dedup(self, tmp_path):
        dup_url = _DEFAULT_REMOTE_CONFIG_URLS[0]
        service = SourceSyncService(data_dir=str(tmp_path), env_remote_config_urls=[dup_url])
        resolved = service._resolve_remote_config_urls()
        count = resolved.urls.count(dup_url)
        assert count == 1

    def test_resolve_urls_all_invalid_env(self, tmp_path):
        service = SourceSyncService(
            data_dir=str(tmp_path),
            env_remote_config_urls=["ftp://invalid.com", ""],
        )
        resolved = service._resolve_remote_config_urls()
        assert resolved.source == "default"
        assert len(resolved.urls) > 0

    def test_resolve_urls_config_file(self, tmp_path):
        config_url = "https://config.mysite.com/source.json"
        local_sources = {"sources": [], "remote_config_url": config_url}
        with open(os.path.join(str(tmp_path), "local_sources.json"), "w", encoding="utf-8") as f:
            import json
            json.dump(local_sources, f)
        service = SourceSyncService(data_dir=str(tmp_path))
        resolved = service._resolve_remote_config_urls()
        assert resolved.source == "config_file"
        assert config_url in resolved.urls


class TestSyncDefaultUrlsAlwaysTried:
    def test_default_urls_in_urls_to_try(self, tmp_path):
        service = SourceSyncService(data_dir=str(tmp_path))
        resolved = service._resolve_remote_config_urls()
        for url in _DEFAULT_REMOTE_CONFIG_URLS:
            assert url in resolved.urls


class TestGetStatusNewFields:
    def test_status_includes_new_fields(self, tmp_path):
        service = SourceSyncService(data_dir=str(tmp_path))
        status = service.get_status()
        assert "effective_remote_urls" in status
        assert "url_source" in status
        assert status["effective_remote_urls"] == []
        assert status["url_source"] is None

    def test_status_after_resolve(self, tmp_path):
        service = SourceSyncService(data_dir=str(tmp_path))
        service._last_resolved_urls = ResolvedUrls(
            urls=_DEFAULT_REMOTE_CONFIG_URLS,
            source="default",
            effective_urls=_DEFAULT_REMOTE_CONFIG_URLS,
        )
        status = service.get_status()
        assert status["effective_remote_urls"] == _DEFAULT_REMOTE_CONFIG_URLS
        assert status["url_source"] == "default"


class TestClassifyChannel:
    def test_classify_nhk_world_international(self):
        assert _classify_channel("NHK World", "\u56fd\u9645\u7535\u89c6") == "\u56fd\u9645\u9891\u9053"

    def test_classify_france24_international(self):
        assert _classify_channel("France 24", "\u56fd\u9645\u7535\u89c6") == "\u56fd\u9645\u9891\u9053"

    def test_classify_invalid_group_still_filtered(self):
        result = _classify_channel("\u672a\u77e5\u9891\u9053", "\u66f4\u65b0\u65f6\u95f4")
        assert result is not None

    def test_classify_cgtn_as_cctv(self):
        assert _classify_channel("CGTN", "\u56fd\u9645\u7535\u89c6") == "\u592e\u89c6\u9891\u9053"

    def test_classify_cgtn_french_as_cctv(self):
        assert _classify_channel("CGTN French", "CGTN") == "\u592e\u89c6\u9891\u9053"

    def test_classify_china_global_television_as_cctv(self):
        assert _classify_channel("China Global Television Network", "\u56fd\u9645\u7535\u89c6") == "\u592e\u89c6\u9891\u9053"

    def test_classify_test_channel_fallback(self):
        result = _classify_channel("\u6d4b\u8bd5\u9891\u9053", "\u6d4b\u8bd5\u7535\u89c6")
        assert result is not None

    def test_invalid_group_keywords_no_broad_terms(self):
        broad_terms = {"\u56fd\u5185\u7535\u89c6", "\u56fd\u9645\u7535\u89c6", "\u56fd\u5185", "\u56fd\u9645", "\u7535\u89c6"}
        assert not broad_terms.intersection(set(_INVALID_GROUP_KEYWORDS))

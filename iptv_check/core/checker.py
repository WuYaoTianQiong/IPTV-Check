import time
import logging
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.network import HttpClient
from iptv_check.infra.cache import CacheManager
from iptv_check.infra.state import StateStore
from iptv_check.infra.event_bus import Events
from iptv_check.core.m3u8_validator import M3U8Validator

logger = logging.getLogger(__name__)


class CheckEngine:
    def __init__(self, http_client: HttpClient, cache: CacheManager, state: StateStore):
        self._http = http_client
        self._cache = cache
        self._state = state
        self._m3u8 = M3U8Validator(http_client)
        self._executor: Optional[ThreadPoolExecutor] = None
        self._result_queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()

    def check_channel(self, channel: Channel, config: CheckConfig) -> CheckResult:
        result = CheckResult(channel=channel, timestamp=time.time())
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        start_time = time.time()

        try:
            timeout = config.timeout_tuple
            with self._http.get(channel.url, headers=headers, timeout=timeout, stream=True) as r:
                r.raise_for_status()
                latency = int((time.time() - start_time) * 1000)
                speed = "-"
                content_type = r.headers.get("Content-Type", "").lower()
                is_m3u8 = "mpegurl" in content_type or channel.url.lower().endswith(".m3u8")

                if config.run_speed_test:
                    if is_m3u8:
                        playlist_content = r.text
                        if not playlist_content.strip().startswith("#EXTM3U"):
                            raise ValueError("非标准M3U8内容")
                        speed = self._m3u8.get_speed(channel.url, playlist_content, headers, timeout)
                    else:
                        speed = self._test_speed(r.iter_content(chunk_size=8192), config.timeout_read)
                else:
                    if is_m3u8:
                        playlist_content = r.text
                        if not playlist_content.strip().startswith("#EXTM3U"):
                            raise ValueError("非标准M3U8内容")
                        self._m3u8.validate_recursive(channel.url, playlist_content, headers, timeout)
                    elif not next(r.iter_content(chunk_size=1024), None):
                        raise ValueError("无数据流")

                result.is_valid = True
                result.latency = latency
                result.speed = speed
                result.details = f"OK ({r.status_code})"
                self._adjust_threads(True)

        except Exception as e:
            result.details = self._classify_error(e)
            result.is_valid = False
            self._adjust_threads(False)

        result.timestamp = time.time()
        return result

    def start(self, channels: List[Channel], config: CheckConfig, on_result=None, on_complete=None):
        self._state.update(is_running=True, stop_requested=False, current_stage="checking", total_count=len(channels))
        self._state.reset_counts()
        Events.check_started.send()

        def worker():
            with ThreadPoolExecutor(max_workers=config.max_threads) as executor:
                self._executor = executor
                futures = []
                for channel in channels:
                    if self._state.state.stop_requested:
                        break
                    url_key = channel.url_key
                    if config.use_cache and self._cache.has(url_key):
                        cached = self._cache.get(url_key)
                        result = CheckResult.from_cache(channel, cached)
                        self._state.increment("checked_count")
                        if result.is_valid:
                            self._state.increment("valid_count")
                        else:
                            self._state.increment("invalid_count")
                        if on_result:
                            on_result(result)
                    else:
                        future = executor.submit(self._check_and_callback, channel, config, on_result)
                        futures.append(future)

                for f in futures:
                    try:
                        f.result()
                    except Exception:
                        pass

            self._state.update(is_running=False, current_stage="done")
            Events.check_completed.send()
            if on_complete:
                on_complete()

        threading.Thread(target=worker, daemon=True).start()

    def add_channels(self, new_channels: List[Channel], config: CheckConfig, on_result=None):
        """流式添加频道并立即开始检测"""
        if not self._executor or not self._state.state.is_running:
            return

        for channel in new_channels:
            if self._state.state.stop_requested:
                break
            url_key = channel.url_key
            if config.use_cache and self._cache.has(url_key):
                cached = self._cache.get(url_key)
                result = CheckResult.from_cache(channel, cached)
                self._state.increment("checked_count")
                if result.is_valid:
                    self._state.increment("valid_count")
                else:
                    self._state.increment("invalid_count")
                if on_result:
                    on_result(result)
            else:
                self._executor.submit(self._check_and_callback, channel, config, on_result)

    def stop(self):
        self._state.update(stop_requested=True)
        if self._executor:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        Events.check_stopped.send()

    def _check_and_callback(self, channel: Channel, config: CheckConfig, on_result):
        if self._state.state.stop_requested:
            return
        result = self.check_channel(channel, config)
        url_key = channel.url_key
        self._cache.set(url_key, result.to_cache_dict())
        self._state.increment("checked_count")
        if result.is_valid:
            self._state.increment("valid_count")
        else:
            self._state.increment("invalid_count")
        Events.channel_checked.send(result=result)
        if on_result:
            on_result(result)

    def _adjust_threads(self, is_success: bool):
        with self._lock:
            state = self._state.state
            if is_success:
                new_success = state.consecutive_success + 1
                self._state.update(consecutive_success=new_success, consecutive_fail=0)
                if new_success >= 20 and state.current_workers < state.current_workers:
                    new_workers = min(state.current_workers + 5, state.current_workers)
                    self._state.update(current_workers=new_workers)
            else:
                new_fail = state.consecutive_fail + 1
                self._state.update(consecutive_success=0, consecutive_fail=new_fail)
                if new_fail >= 10 and state.current_workers > 5:
                    new_workers = max(state.current_workers // 2, 5)
                    self._state.update(current_workers=new_workers)

    @staticmethod
    def _test_speed(response_iterator, timeout: int) -> str:
        try:
            start_time = time.time()
            downloaded_size = 0
            for chunk in response_iterator:
                downloaded_size += len(chunk)
                if downloaded_size >= 256 * 1024:
                    break
                if time.time() - start_time > timeout / 2:
                    return "N/A"
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                speed_kbps = (downloaded_size / 1024) / elapsed_time
                return f"{speed_kbps:.2f}"
            return "∞"
        except Exception:
            return "N/A"

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        import requests.exceptions
        if isinstance(exc, requests.exceptions.Timeout):
            return "超时"
        if isinstance(exc, requests.exceptions.SSLError):
            return f"SSL证书错误: {str(exc)[:30]}"
        if isinstance(exc, requests.exceptions.ConnectionError):
            err_str = str(exc).lower()
            if "dns" in err_str or "name resolution" in err_str:
                return "DNS解析失败"
            if "refused" in err_str or "actively refused" in err_str:
                return "连接被拒绝"
            if "reset" in err_str:
                return "连接被重置"
            return "连接失败"
        if isinstance(exc, requests.exceptions.HTTPError):
            status = exc.response.status_code
            if status == 403:
                return "访问被拒绝(403)"
            if status == 404:
                return "资源不存在(404)"
            if status >= 500:
                return f"服务器错误({status})"
            return f"HTTP错误({status})"
        if isinstance(exc, ValueError):
            return str(exc)
        return f"未知错误: {str(exc)[:30]}"

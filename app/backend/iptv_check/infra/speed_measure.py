"""测速工具 —— 统一各引擎重复的测速实现。

此前 m3u8_validator / async_engine / stream_engine / thread_pool 各自实现
「累积读取至 256KB 或 timeout/2 秒」的测速逻辑，且 elapsed≈0 时的返回值
口径不一（"" / "∞" / "N/A"）。本模块提供唯一实现，调用方用 ``empty_result``
保留各自历史口径，避免行为变化。

``max_bytes`` / ``max_seconds`` 可覆盖默认的「256KB / timeout/2 秒」：
DEEP 细筛对慢源使用更短放弃时间（128KB / 4s），省去无谓的测速等待，
且测速超时只影响速度值精度，不影响有效/无效判定。
"""
import time
from typing import Optional


def measure_speed_sync(iterable, timeout: int, *, empty_result: str = "N/A",
                       max_bytes: int = 256 * 1024, max_seconds: Optional[float] = None) -> str:
    """同步测速：累积读取至 max_bytes 或 max_seconds（默认 timeout/2）秒，返回 KB/s。"""
    try:
        start_time = time.time()
        downloaded_size = 0
        limit_seconds = max_seconds if max_seconds is not None else timeout / 2
        for chunk in iterable:
            downloaded_size += len(chunk)
            if downloaded_size >= max_bytes:
                break
            if time.time() - start_time > limit_seconds:
                return "N/A"
        elapsed_time = time.time() - start_time
        if elapsed_time > 0:
            return f"{(downloaded_size / 1024) / elapsed_time:.2f}"
        return empty_result
    except Exception:
        return "N/A"


async def measure_speed_async(iterable, timeout: int, *, empty_result: str = "N/A",
                              max_bytes: int = 256 * 1024, max_seconds: Optional[float] = None) -> str:
    """异步测速：累积读取至 max_bytes 或 max_seconds（默认 timeout/2）秒，返回 KB/s。"""
    try:
        start_time = time.time()
        downloaded_size = 0
        limit_seconds = max_seconds if max_seconds is not None else timeout / 2
        async for chunk in iterable:
            downloaded_size += len(chunk)
            if downloaded_size >= max_bytes:
                break
            if time.time() - start_time > limit_seconds:
                return "N/A"
        elapsed_time = time.time() - start_time
        if elapsed_time > 0:
            return f"{(downloaded_size / 1024) / elapsed_time:.2f}"
        return empty_result
    except Exception:
        return "N/A"

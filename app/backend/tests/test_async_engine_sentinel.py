"""
严格测试 AsyncCheckEngine 的 sentinel 修复

验证：
1. _feed_channels 在所有频道入队后发送 _SENTINEL
2. _consumer_loop 收到 _SENTINEL 后正确触发 on_complete
3. 所有频道都被处理，不会卡在 queue.get()
"""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List

from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.check_engine.async_engine import AsyncCheckEngine, _SENTINEL


def create_test_channels(count: int) -> List[Channel]:
    """创建测试用频道"""
    channels = []
    for i in range(count):
        ch = Channel(
            name=f"Test Channel {i}",
            url=f"http://example.com/stream{i}.m3u8",
            group="Test Group",
            sources=["test"],
            index=i,
        )
        channels.append(ch)
    return channels


@pytest.mark.asyncio
async def test_sentinel_is_sent_after_feeding_channels():
    """测试：_feed_channels 在所有频道入队后发送 _SENTINEL"""
    # Mock 依赖
    mock_http = MagicMock()
    mock_cache = MagicMock()
    mock_cache.has.return_value = False  # 所有频道都需要检测
    mock_m3u8 = MagicMock()

    engine = AsyncCheckEngine(
        http_session=mock_http,
        cache=mock_cache,
        m3u8_validator=mock_m3u8,
    )

    channels = create_test_channels(10)
    config = CheckConfig(max_threads=5)

    result_collected = []
    complete_called = asyncio.Event()

    def on_result(result):
        result_collected.append(result)

    def on_complete():
        complete_called.set()

    # 启动引擎
    engine.start(channels, config, on_result=on_result, on_complete=on_complete)

    # 等待 _feed_channels 完成（所有频道入队 + _SENTINEL 发送）
    await asyncio.sleep(0.5)

    # 验证队列中有频道和 _SENTINEL
    # 注意：由于 consumer_loop 已经在处理，队列可能为空
    # 但我们可以通过 complete_called 来验证 sentinel 被正确处理

    # 等待 on_complete 被调用
    try:
        await asyncio.wait_for(complete_called.wait(), timeout=5.0)
        sentinel_processed = True
    except asyncio.TimeoutError:
        sentinel_processed = False

    assert sentinel_processed, "_SENTINEL 未被处理，on_complete 未被调用"
    assert len(result_collected) == 10, f"应该收集 10 个结果，实际收集 {len(result_collected)} 个"


@pytest.mark.asyncio
async def test_all_channels_processed_with_cache_hits():
    """测试：缓存命中的频道也通过 on_result 回调"""
    mock_http = MagicMock()
    mock_cache = MagicMock()
    mock_cache.has.return_value = True  # 所有频道都缓存命中
    mock_cache.get.return_value = {
        "is_valid": True,
        "latency": 100,
        "speed": "1024.00",
        "details": "OK",
    }
    mock_m3u8 = MagicMock()

    engine = AsyncCheckEngine(
        http_session=mock_http,
        cache=mock_cache,
        m3u8_validator=mock_m3u8,
    )

    channels = create_test_channels(5)
    config = CheckConfig(max_threads=5, use_cache=True)

    result_collected = []
    complete_called = asyncio.Event()

    def on_result(result):
        result_collected.append(result)

    def on_complete():
        complete_called.set()

    engine.start(channels, config, on_result=on_result, on_complete=on_complete)

    # 缓存命中是同步处理，应该很快完成
    try:
        await asyncio.wait_for(complete_called.wait(), timeout=2.0)
        complete_success = True
    except asyncio.TimeoutError:
        complete_success = False

    assert complete_success, "缓存命中场景下 on_complete 未被调用"
    assert len(result_collected) == 5, f"应该收集 5 个缓存结果，实际收集 {len(result_collected)} 个"


@pytest.mark.asyncio
async def test_no_deadlock_with_mixed_cache():
    """测试：混合缓存命中和未命中场景，不会死锁"""
    mock_http = MagicMock()
    mock_cache = MagicMock()
    # 交替缓存命中/未命中
    cache_status = {f"key_{i}": (i % 2 == 0) for i in range(20)}
    mock_cache.has.side_effect = lambda key: cache_status.get(key, False)
    mock_cache.get.return_value = {
        "is_valid": True,
        "latency": 50,
        "speed": "512.00",
        "details": "OK",
    }
    mock_m3u8 = MagicMock()

    engine = AsyncCheckEngine(
        http_session=mock_http,
        cache=mock_cache,
        m3u8_validator=mock_m3u8,
    )

    channels = create_test_channels(20)
    for i, ch in enumerate(channels):
        ch._url_key = f"key_{i}"  # 设置 url_key 以匹配缓存

    config = CheckConfig(max_threads=10, use_cache=True)

    result_count = 0
    complete_called = asyncio.Event()

    def on_result(result):
        nonlocal result_count
        result_count += 1

    def on_complete():
        complete_called.set()

    engine.start(channels, config, on_result=on_result, on_complete=on_complete)

    # 验证不会死锁
    try:
        await asyncio.wait_for(complete_called.wait(), timeout=10.0)
        no_deadlock = True
    except asyncio.TimeoutError:
        no_deadlock = False

    assert no_deadlock, "检测到死锁：on_complete 在 10 秒内未被调用"
    assert result_count == 20, f"应该处理 20 个频道，实际处理 {result_count} 个"


@pytest.mark.asyncio
async def test_streaming_batch_feed_with_complete():
    """测试：流式模式 start + add_channels + complete 流程，批次跨多个调用仍能全部检测"""
    mock_http = MagicMock()
    mock_cache = MagicMock()
    mock_cache.has.return_value = False  # 所有频道都需要检测
    mock_m3u8 = MagicMock()

    engine = AsyncCheckEngine(
        http_session=mock_http,
        cache=mock_cache,
        m3u8_validator=mock_m3u8,
    )

    config = CheckConfig(max_threads=5)

    result_collected = []
    complete_called = asyncio.Event()

    def on_result(result):
        result_collected.append(result)

    def on_complete():
        complete_called.set()

    # 流式启动第一批
    engine.start(create_test_channels(3), config, on_result=on_result, on_complete=on_complete, streaming=True)
    # 中途追加两批
    engine.add_channels(create_test_channels(4), config)
    engine.add_channels(create_test_channels(3), config)
    # 结束接收，触发完成标记
    engine.complete()

    try:
        await asyncio.wait_for(complete_called.wait(), timeout=5.0)
        completed = True
    except asyncio.TimeoutError:
        completed = False

    assert completed, "流式模式下 on_complete 未被调用"
    assert len(result_collected) == 10, f"应该收集 10 个结果，实际收集 {len(result_collected)} 个"


@pytest.mark.asyncio
async def test_streaming_no_complete_keeps_waiting():
    """测试：流式模式未调用 complete() 时不会提前触发 on_complete"""
    mock_http = MagicMock()
    mock_cache = MagicMock()
    mock_cache.has.return_value = False
    mock_m3u8 = MagicMock()

    engine = AsyncCheckEngine(
        http_session=mock_http,
        cache=mock_cache,
        m3u8_validator=mock_m3u8,
    )

    config = CheckConfig(max_threads=5)
    complete_called = asyncio.Event()

    def on_complete():
        complete_called.set()

    engine.start(create_test_channels(3), config, on_complete=on_complete, streaming=True)

    # 不调用 complete()，短暂等待后 on_complete 不应触发
    await asyncio.sleep(0.6)
    assert not complete_called.is_set(), "未调用 complete() 时不应触发 on_complete"

    # 再调用 complete() 后应正常完成
    engine.complete()
    try:
        await asyncio.wait_for(complete_called.wait(), timeout=5.0)
        completed = True
    except asyncio.TimeoutError:
        completed = False
    assert completed, "调用 complete() 后 on_complete 应被触发"


@pytest.mark.asyncio
async def test_queue_not_blocked_by_sentinel():
    """测试：_SENTINEL 不会阻塞队列处理"""
    from iptv_check.infra.check_engine.async_engine import _SENTINEL

    queue = asyncio.Queue()

    # 放入 5 个频道
    for i in range(5):
        await queue.put(f"channel_{i}")

    # 放入 _SENTINEL
    await queue.put(_SENTINEL)

    # 验证可以取出所有频道和 _SENTINEL
    items = []
    while True:
        item = await queue.get()
        items.append(item)
        queue.task_done()
        if item is _SENTINEL:
            break

    assert len(items) == 6, f"应该取出 6 个元素（5 个频道 + 1 个 sentinel），实际取出 {len(items)} 个"
    assert items[-1] is _SENTINEL, "最后一个元素应该是 _SENTINEL"
    assert all(f"channel_{i}" in items for i in range(5)), "所有频道都应该被取出"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

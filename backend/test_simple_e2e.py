"""
简化测试：直接验证文件解析和 AsyncCheckEngine
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

from iptv_check.core.parser import PlaylistParser
from iptv_check.models.channel import Channel
from iptv_check.models.settings import CheckConfig
from iptv_check.infra.check_engine.async_engine import AsyncCheckEngine
from iptv_check.infra.disk_cache import DiskCacheManager

# 1. 测试文件解析
print("=== 测试 1: 解析测试文件 ===")
channels = PlaylistParser.parse_file("test_channels.m3u")
print(f"解析到 {len(channels)} 个频道")
for ch in channels[:3]:
    print(f"  - {ch.name}: {ch.url}")

if len(channels) != 10:
    print(f"❌ 失败: 应该解析 10 个频道，实际解析 {len(channels)}")
    exit(1)

print("✅ 通过: 成功解析 10 个频道\n")

# 2. 测试 AsyncCheckEngine
print("=== 测试 2: AsyncCheckEngine 处理所有频道 ===")

async def test_engine():
    # 初始化缓存（使用 DiskCacheManager，与 app.py 一致）
    cache = DiskCacheManager(base_dir="iptv_check/data")
    
    # Mock HTTP session
    import aiohttp
    session = aiohttp.ClientSession()
    
    # Mock M3U8 validator
    from iptv_check.core.m3u8_validator import M3U8Validator
    m3u8_validator = M3U8Validator(session)
    
    # 创建引擎
    engine = AsyncCheckEngine(
        http_session=session,
        cache=cache,
        m3u8_validator=m3u8_validator,
    )
    
    config = CheckConfig(
        timeout_connect=2,
        timeout_read=3,
        max_threads=5,
        run_speed_test=False,
        use_cache=False,
    )
    
    result_count = 0
    complete_called = asyncio.Event()
    
    def on_result(result):
        nonlocal result_count
        result_count += 1
        status = "✅" if result.is_valid else "❌"
        print(f"  {status} {result.channel.name}: {result.details}")
    
    def on_complete():
        print(f"\n检测完成，共处理 {result_count} 个频道")
        complete_called.set()
    
    # 启动引擎
    print(f"启动检测，共 {len(channels)} 个频道")
    engine.start(channels, config, on_result=on_result, on_complete=on_complete)
    
    # 等待完成（最多 30 秒）
    try:
        await asyncio.wait_for(complete_called.wait(), timeout=30.0)
        if result_count == len(channels):
            print(f"✅ 通过: 所有 {result_count} 个频道都被处理")
            return True
        else:
            print(f"❌ 失败: 只处理了 {result_count}/{len(channels)} 个频道")
            return False
    except asyncio.TimeoutError:
        print(f"❌ 失败: 检测超时，只处理了 {result_count}/{len(channels)} 个频道")
        return False
    finally:
        await session.close()

success = asyncio.run(test_engine())
exit(0 if success else 1)

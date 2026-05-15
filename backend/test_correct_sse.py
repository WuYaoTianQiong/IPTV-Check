"""
严格的端到端测试：使用正确的 SSE 路由验证检测流程
"""
import asyncio
import aiohttp
import json
import time

BASE_URL = "http://127.0.0.1:9529"

# 创建一个包含 3 个频道的测试文件
test_m3u_content = """#EXTM3U
#EXTINF:-1 tvg-name="Test1" group-title="Test",Test1
http://example.com/test1.m3u8
#EXTINF:-1 tvg-name="Test2" group-title="Test",Test2
http://example.com/test2.m3u8
#EXTINF:-1 tvg-name="Test3" group-title="Test",Test3
http://example.com/test3.m3u8
"""

async def main():
    async with aiohttp.ClientSession() as session:
        # 1. 上传测试文件
        import base64
        content_base64 = base64.b64encode(test_m3u_content.encode("utf-8")).decode("utf-8")
        
        print("步骤 1: 上传测试文件")
        async with session.post(
            f"{BASE_URL}/api/upload",
            json={"filename": "test.m3u", "content_base64": content_base64}
        ) as resp:
            data = await resp.json()
            file_path = data.get("path")
            print(f"  文件路径: {file_path}")
        
        # 2. 先建立 SSE 连接（使用正确的路由）
        print("\n步骤 2: 建立 SSE 连接")
        sse_task = asyncio.create_task(session.get(f"{BASE_URL}/api/events/stream"))
        await asyncio.sleep(1)  # 等待 SSE 连接建立
        print("  SSE 连接已建立")
        
        # 3. 启动检测
        print("\n步骤 3: 启动检测")
        payload = {
            "file_paths": [file_path],
            "online_source_ids": [],
            "timeout_connect": 2,
            "timeout_read": 3,
            "max_threads": 3,
            "run_speed_test": False,
            "use_cache": False,
        }
        
        start_time = time.time()
        async with session.post(f"{BASE_URL}/api/check/start", json=payload) as resp:
            data = await resp.json()
            session_id = data.get("session_id")
            print(f"  Session ID: {session_id}")
        
        # 4. 监听 SSE 事件
        print("\n步骤 4: 监听 SSE 事件（最多等待 30 秒）")
        events_received = []
        max_wait = 30
        
        try:
            sse_resp = await sse_task
            async for line in sse_resp.content:
                text = line.decode('utf-8').strip()
                if not text:
                    continue
                
                if text.startswith('data: '):
                    data_str = text[6:]
                    if data_str == '[DONE]':
                        break
                    
                    try:
                        data = json.loads(data_str)
                        event = data.get("event", "")
                        events_received.append(event)
                        
                        if event == "channels_loaded":
                            print(f"  [频道加载] 总计: {data.get('total', 0)}")
                        elif event == "progress_update":
                            print(f"  [进度] 已检测: {data.get('checked', 0)}/{data.get('total', 0)}")
                        elif event == "check_completed":
                            print(f"  [完成] 检测完成")
                            break
                        elif event == "init":
                            print(f"  [初始化] 收到 init 事件")
                    except json.JSONDecodeError:
                        pass
                
                if time.time() - start_time > max_wait:
                    print(f"  [超时] 等待超过 {max_wait} 秒")
                    break
        
        except Exception as e:
            print(f"  [异常] SSE 流错误: {e}")
        
        # 5. 验证结果
        print(f"\n=== 测试结果 ===")
        print(f"  接收到的事件: {events_received}")
        
        if "check_completed" in events_received:
            print(f"\n  ✅ 通过: 检测正常完成")
        elif "channels_loaded" in events_received:
            print(f"\n  ⚠️  频道已加载，但未收到完成事件")
        else:
            print(f"\n  ❌ 失败: 未收到任何关键事件")

if __name__ == "__main__":
    asyncio.run(main())

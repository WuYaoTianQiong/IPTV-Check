"""直接调用 CheckService._run_check 来诊断问题"""
import os
import sys
import asyncio
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iptv_check.server.app import create_app, app_state

print(f"app_state: {app_state}")
print(f"app_state._check_service: {app_state._check_service}")

# 构造一个模拟的请求对象
class MockRequest:
    def __init__(self):
        self.file_paths = []
        self.online_source_ids = []
        self.timeout_connect = 2
        self.timeout_read = 3
        self.max_threads = 3
        self.run_speed_test = False
        self.use_cache = False

async def main():
    if not app_state._check_service:
        print("错误: CheckService 未初始化")
        return
    
    service = app_state._check_service
    req = MockRequest()
    
    print("调用 start_check...")
    try:
        await service.start_check(req)
        print("start_check 完成")
        
        # 等待一段时间让后台任务执行
        await asyncio.sleep(5)
        
        print(f"session_id: {service.session_id}")
        print(f"is_running: {service.is_running}")
        print(f"progress: {service.get_progress()}")
    except Exception as e:
        print(f"start_check 异常: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(main())

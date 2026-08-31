"""Router 层共享辅助函数。"""


def get_state():
    """获取全局 AppState 实例。"""
    from iptv_check.server.app import get_app_state
    return get_app_state()


def get_check_service():
    """获取 CheckService 实例（未初始化时返回 None）。"""
    return getattr(get_state(), "_check_service", None)

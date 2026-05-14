from iptv_check.server.routers.channels import router as channels_router
from iptv_check.server.routers.sources import router as sources_router
from iptv_check.server.routers.check import router as check_router
from iptv_check.server.routers.export import router as export_router
from iptv_check.server.routers.epg import router as epg_router
from iptv_check.server.routers.logos import router as logos_router
from iptv_check.server.routers.cache import router as cache_router

__all__ = [
    "channels_router", "sources_router", "check_router", "export_router",
    "epg_router", "logos_router", "cache_router",
]

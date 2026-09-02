"""收藏夹 / 收藏夹管理 / 自定义频道 路由。"""
import asyncio
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import select

from iptv_check.models.channel import Channel
from iptv_check.infra.persistence.read_model import _infer_region
from iptv_check.server.routers._common import get_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["favorites"])


class AddFavoriteRequest(BaseModel):
    url: str = ""
    name: str = ""
    folder_id: Optional[int] = None
    channel_group: str = ""


class UpdateFavoriteRequest(BaseModel):
    folder_id: Optional[int] = None
    sort_order: Optional[int] = None
    name: Optional[str] = None


class CreateFavoriteFolderRequest(BaseModel):
    name: str = "新收藏夹"
    icon: str = ""
    sort_order: int = 0


class UpdateFavoriteFolderRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class AddCustomChannelRequest(BaseModel):
    name: str = "自定义频道"
    url: str = ""
    group: str = "自定义"


@router.get("/favorites")
async def get_favorites(folder_id: Optional[int] = None, page: int = 1, per_page: int = 50, sort: str = "default"):
    state = get_state()
    from iptv_check.core.parser import _translate_channel_name, _map_group_name, _infer_country_code
    _RADIO_KW = {"广播", "电台", "radio", "fm", "am", "broadcast"}
    _RADIO_URL_KW = {"qingting.fm", "xmcdn.com", "ximalaya", "lrc.la"}
    def _is_radio(name, group, url):
        text = f"{name or ''} {group or ''} {url or ''}".lower()
        url_lower = (url or "").lower()
        return (any(kw in text for kw in _RADIO_KW) or
                any(kw in url_lower for kw in _RADIO_URL_KW) or
                bool(re.search(r"://[^/]*radio(?:\d|\.|:)", url_lower)))

    def _query():
        from iptv_check.infra.repository.favorite_repo import FavoriteRepository
        with state.database.get_session() as session:
            rows, total = FavoriteRepository(session).list_paginated(folder_id, page, per_page, sort)
            items = [
                {"id": f.id, "channel_id": f.channel_id,
                 "name": f.name,
                 "name_cn": _translate_channel_name(f.name) or "",
                 "url": f.url,
                 "folder_id": f.folder_id,
                 "sort_order": f.sort_order,
                 "latency": f.latency,
                 "channel_group": _map_group_name(f.channel_group),
                 "region": _infer_region(f.name, f.channel_group, _infer_country_code(f.name, f.channel_group)),
                 "is_radio": _is_radio(f.name, f.channel_group, f.url),
                 "country": _infer_country_code(f.name, f.channel_group),
                 "frequency": Channel._extract_frequency(f.name, f.channel_group),
                 "created_at": f.created_at.isoformat() if hasattr(f.created_at, 'isoformat') else str(f.created_at)}
                for f in rows
            ]
            return items, total
    favorites, total = await asyncio.to_thread(_query)
    return {"favorites": favorites, "total": total, "page": page, "per_page": per_page}


@router.post("/favorites/refresh-latency")
async def refresh_favorites_latency():
    """实时检测收藏夹中所有频道的延迟（HTTP HEAD请求）"""
    state = get_state()
    from iptv_check.infra.cn_time import cn_now
    import aiohttp
    import ssl

    def _fetch_favorites():
        from iptv_check.infra.repository.favorite_repo import FavoriteRepository
        with state.database.get_session() as session:
            return FavoriteRepository(session).fetch_all_urls()

    favs_data = await asyncio.to_thread(_fetch_favorites)

    if not favs_data:
        return {"updated": 0, "results": []}

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context, limit=50)
    timeout = aiohttp.ClientTimeout(total=2, connect=1)

    async def probe_one(fav, session):
        url = fav["url"]
        start = asyncio.get_event_loop().time()
        try:
            async with session.head(url, allow_redirects=True) as resp:
                elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
                return {"id": fav["id"], "latency": elapsed_ms, "status": resp.status, "ok": resp.status < 400}
        except asyncio.TimeoutError:
            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            return {"id": fav["id"], "latency": -1, "status": 0, "ok": False, "error": "超时"}
        except Exception as e:
            elapsed_ms = int((asyncio.get_event_loop().time() - start) * 1000)
            return {"id": fav["id"], "latency": -1, "status": 0, "ok": False, "error": str(e)[:50]}

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [probe_one(f, session) for f in favs_data]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    processed_results = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed_results.append({"id": favs_data[i]["id"], "latency": -1, "status": 0, "ok": False, "error": str(r)[:50]})
        else:
            processed_results.append(r)

    # Update database
    now = cn_now().isoformat()
    def _update(results):
        from iptv_check.infra.repository.favorite_repo import FavoriteRepository
        updates = [(res["id"], res["latency"]) for res in results if res["ok"] and res["latency"] > 0]
        with state.database.get_session() as session:
            return FavoriteRepository(session).update_latency_batch(updates, now)

    update_count = await asyncio.to_thread(_update, processed_results)

    return {"updated": update_count, "results": processed_results}


@router.post("/favorites")
async def add_favorite(req: AddFavoriteRequest):
    state = get_state()
    from iptv_check.infra.database import FavoriteModel, ChannelModel
    from iptv_check.core.parser import _translate_channel_name
    def _query():
        with state.database.get_session() as session:
            url = req.url
            existing = session.exec(select(FavoriteModel).where(FavoriteModel.url == url)).first()
            if existing:
                return {"id": existing.id, "name": existing.name, "url": existing.url, "folder_id": existing.folder_id, "created_at": existing.created_at.isoformat()}
            channel = session.exec(select(ChannelModel).where(ChannelModel.url == url)).first()
            channel_id = channel.id if channel else 0
            raw_name = req.name or (channel.name if channel else "")
            translated = _translate_channel_name(raw_name, channel.tvg_name if channel else "")
            name_cn = translated if translated else ""
            folder_id = req.folder_id
            channel_group = req.channel_group or (channel.group if channel else "")
            fav = FavoriteModel(channel_id=channel_id, name=raw_name, url=url, folder_id=folder_id, channel_group=channel_group, name_cn=name_cn)
            session.add(fav)
            session.commit()
            session.refresh(fav)
            return {"id": fav.id, "name": fav.name, "url": fav.url, "folder_id": fav.folder_id, "channel_group": fav.channel_group, "created_at": fav.created_at.isoformat()}
    return await asyncio.to_thread(_query)


@router.delete("/favorites/{fav_id}")
async def remove_favorite(fav_id: int):
    state = get_state()
    from iptv_check.infra.database import FavoriteModel
    def _query():
        with state.database.get_session() as session:
            fav = session.get(FavoriteModel, fav_id)
            if fav:
                session.delete(fav)
                session.commit()
                return {"deleted": True}
            raise HTTPException(404, "收藏不存在")
    return await asyncio.to_thread(_query)


@router.put("/favorites/{fav_id}")
async def update_favorite(fav_id: int, req: UpdateFavoriteRequest):
    state = get_state()
    from iptv_check.infra.database import FavoriteModel
    def _query():
        with state.database.get_session() as session:
            fav = session.get(FavoriteModel, fav_id)
            if not fav:
                raise HTTPException(404, "收藏不存在")
            if req.folder_id is not None:
                fav.folder_id = req.folder_id
            if req.sort_order is not None:
                fav.sort_order = req.sort_order
            if req.name is not None:
                fav.name = req.name
            session.commit()
            return {"id": fav.id, "name": fav.name, "folder_id": fav.folder_id}
    return await asyncio.to_thread(_query)


@router.get("/favorites/m3u")
async def export_favorites_m3u(folder_id: str = None):
    state = get_state()
    from iptv_check.infra.database import FavoriteModel
    def _query():
        with state.database.get_session() as session:
            if folder_id is not None:
                try:
                    fid = int(folder_id)
                    items = session.exec(select(FavoriteModel).where(FavoriteModel.folder_id == fid).order_by(FavoriteModel.sort_order.asc(), FavoriteModel.created_at.desc())).all()
                except ValueError:
                    items = session.exec(select(FavoriteModel).where(FavoriteModel.folder_id == None).order_by(FavoriteModel.sort_order.asc(), FavoriteModel.created_at.desc())).all()
            else:
                items = session.exec(select(FavoriteModel).order_by(FavoriteModel.sort_order.asc(), FavoriteModel.created_at.desc())).all()
            return [(f.name, f.url) for f in items]
    items = await asyncio.to_thread(_query)
    if not items:
        raise HTTPException(status_code=400, detail="没有可导出的收藏数据")
    lines = ["#EXTM3U"]
    for name, url in items:
        lines.append(f'#EXTINF:-1,{name}')
        lines.append(url)
    content = "\n".join(lines) + "\n"
    return Response(content=content, media_type="audio/mpegurl", headers={"Content-Disposition": "attachment; filename=favorites.m3u"})


@router.get("/favorite-folders")
async def get_favorite_folders():
    state = get_state()
    def _query():
        from iptv_check.infra.repository.favorite_repo import FavoriteRepository
        with state.database.get_session() as session:
            folders, count_map = FavoriteRepository(session).list_folders_with_counts()
            result = []
            for folder in folders:
                result.append({
                    "id": folder.id, "name": folder.name, "icon": folder.icon,
                    "sort_order": folder.sort_order,
                    "count": count_map.get(folder.id, 0),
                })
            unfiled = count_map.get(None, 0)
            result.append({"id": None, "name": "未分类", "icon": "", "sort_order": 999, "count": unfiled})
            return result
    folders = await asyncio.to_thread(_query)
    return {"folders": folders}


@router.post("/favorite-folders")
async def create_favorite_folder(req: CreateFavoriteFolderRequest):
    state = get_state()
    from iptv_check.infra.database import FavoriteFolderModel
    def _query():
        with state.database.get_session() as session:
            folder = FavoriteFolderModel(
                name=req.name,
                icon=req.icon,
                sort_order=req.sort_order,
            )
            session.add(folder)
            session.commit()
            session.refresh(folder)
            return {"id": folder.id, "name": folder.name, "icon": folder.icon, "sort_order": folder.sort_order}
    return await asyncio.to_thread(_query)


@router.put("/favorite-folders/{folder_id}")
async def update_favorite_folder(folder_id: int, req: UpdateFavoriteFolderRequest):
    state = get_state()
    from iptv_check.infra.database import FavoriteFolderModel
    def _query():
        with state.database.get_session() as session:
            folder = session.get(FavoriteFolderModel, folder_id)
            if not folder:
                raise HTTPException(404, "收藏夹不存在")
            if req.name is not None:
                folder.name = req.name
            if req.icon is not None:
                folder.icon = req.icon
            if req.sort_order is not None:
                folder.sort_order = req.sort_order
            session.commit()
            return {"id": folder.id, "name": folder.name}
    return await asyncio.to_thread(_query)


@router.delete("/favorite-folders/{folder_id}")
async def delete_favorite_folder(folder_id: int):
    state = get_state()
    from iptv_check.infra.database import FavoriteFolderModel, FavoriteModel
    def _query():
        with state.database.get_session() as session:
            folder = session.get(FavoriteFolderModel, folder_id)
            if not folder:
                raise HTTPException(404, "收藏夹不存在")
            favs = session.exec(select(FavoriteModel).where(FavoriteModel.folder_id == folder_id)).all()
            for f in favs:
                f.folder_id = None
            session.delete(folder)
            session.commit()
            return {"deleted": True, "moved_to_unfiled": len(favs)}
    return await asyncio.to_thread(_query)


@router.get("/custom-channels")
async def get_custom_channels():
    state = get_state()
    from iptv_check.infra.database import CustomChannelModel
    def _query():
        with state.database.get_session() as session:
            items = session.exec(select(CustomChannelModel).order_by(CustomChannelModel.sort_order)).all()
            return [
                {"id": c.id, "name": c.name, "url": c.url, "group": c.group,
                 "folder_id": c.folder_id, "sort_order": c.sort_order}
                for c in items
            ]
    channels = await asyncio.to_thread(_query)
    return {"channels": channels}


@router.post("/custom-channels")
async def add_custom_channel(req: AddCustomChannelRequest):
    state = get_state()
    from iptv_check.infra.database import CustomChannelModel
    def _query():
        with state.database.get_session() as session:
            url = req.url
            existing = session.exec(select(CustomChannelModel).where(CustomChannelModel.url == url)).first()
            if existing:
                return {"id": existing.id, "name": existing.name, "url": existing.url}
            ch = CustomChannelModel(
                name=req.name,
                url=url,
                group=req.group,
                folder_id=req.folder_id,
            )
            session.add(ch)
            session.commit()
            session.refresh(ch)
            return {"id": ch.id, "name": ch.name, "url": ch.url, "group": ch.group}
    return await asyncio.to_thread(_query)


@router.delete("/custom-channels/{channel_id}")
async def delete_custom_channel(channel_id: int):
    state = get_state()
    from iptv_check.infra.database import CustomChannelModel
    def _query():
        with state.database.get_session() as session:
            ch = session.get(CustomChannelModel, channel_id)
            if not ch:
                raise HTTPException(404, "自定义频道不存在")
            session.delete(ch)
            session.commit()
            return {"deleted": True}
    return await asyncio.to_thread(_query)

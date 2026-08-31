import asyncio
import logging
import datetime
import random
import time
import urllib.parse
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from iptv_check.models.channel import Channel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["channels"])


class UploadRequest(BaseModel):
    filename: str = "upload.m3u"
    content_base64: str = ""


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
    folder_id: Optional[int] = None


def _get_state():
    from iptv_check.server.app import get_app_state
    return get_app_state()


def _get_check_service():
    state = _get_state()
    return getattr(state, "_check_service", None)


from iptv_check.infra.persistence.read_model import _infer_region


@router.get("/results")
async def get_results(
    tab: str = "all",
    page: int = 1,
    per_page: int = 50,
    search: str = "",
    group_path: str = "",
    view_mode: str = "grouped",
    sort: str = "best",
    media_type: str = "all",
    language: str = "",
    country: str = "",
    region: str = "",
    category: str = "",
    quality: str = "",
    protocol: str = "",
    latency_min: float = -1,
    latency_max: float = -1,
    speed_min: float = -1,
    speed_max: float = -1,
    session_id: str = "",
):
    """获取检测结果，支持通过 session_id 查看历史会话"""
    import traceback
    try:
        state = _get_state()
        service = _get_check_service()

        # session_id 优先级：URL 参数 > service.session_id > event_store.current_session_id
        effective_session_id = session_id or (service.session_id if service else "") or (state.event_store.current_session_id if state else "")

        if effective_session_id:
            try:
                if view_mode == "grouped":
                    return await asyncio.to_thread(
                        state.read_model.get_grouped_channels,
                        session_id=effective_session_id,
                        tab=tab, group_path=group_path, page=page, per_page=per_page,
                        search=search, sort=sort, media_type=media_type, language=language,
                        country=country, region=region, category=category, quality=quality, protocol=protocol,
                        latency_min=latency_min, latency_max=latency_max,
                        speed_min=speed_min, speed_max=speed_max,
                    )
                return await asyncio.to_thread(
                    state.read_model.get_checked_channels,
                    session_id=effective_session_id,
                    tab=tab, page=page, per_page=per_page, search=search, sort=sort,
                    media_type=media_type, language=language,
                    country=country, region=region, category=category, quality=quality, protocol=protocol,
                    latency_min=latency_min, latency_max=latency_max,
                    speed_min=speed_min, speed_max=speed_max,
                )
            except Exception as e:
                logger.error("获取检测结果失败: %s\n%s", e, traceback.format_exc())
                return {"total": 0, "page": page, "per_page": per_page, "items": [], "error": str(e)}

        if state and not state.is_checking and state.database:
            try:
                return await asyncio.to_thread(state.database.query_results_paginated, tab=tab, page=page, per_page=per_page, search=search, sort=sort)
            except Exception as e:
                logger.error("查询历史结果失败: %s\n%s", e, traceback.format_exc())

        return {"total": 0, "page": page, "per_page": per_page, "items": []}
    except Exception as e:
        logger.critical("[CRITICAL ERROR in /api/results] %s: %s", type(e).__name__, e, exc_info=True)
        raise


@router.get("/results/category-tree")
async def get_category_tree(media_type: str = "all"):
    state = _get_state()
    service = _get_check_service()
    session_id = ""
    if service and service.session_id:
        session_id = service.session_id
    elif state and state.event_store:
        session_id = state.event_store.current_session_id
    if not session_id:
        return []
    try:
        return await asyncio.to_thread(state.read_model.get_category_tree, session_id=session_id, media_type=media_type)
    except Exception as e:
        logger.error("获取分类树失败: %s", e, exc_info=True)
        return []


@router.get("/results/languages")
async def get_available_languages():
    state = _get_state()
    service = _get_check_service()
    session_id = ""
    if service and service.session_id:
        session_id = service.session_id
    elif state and state.event_store:
        session_id = state.event_store.current_session_id
    if not session_id:
        return []
    try:
        return await asyncio.to_thread(state.read_model.get_available_languages, session_id)
    except Exception as e:
        logger.error("获取语言列表失败: %s", e, exc_info=True)
        return []


@router.get("/results/countries")
async def get_available_countries():
    """获取当前数据中可用的国家/地区列表（基于实际数据推断）"""
    state = _get_state()
    service = _get_check_service()
    session_id = ""
    if service and service.session_id:
        session_id = service.session_id
    elif state and state.event_store:
        session_id = state.event_store.current_session_id
    if not session_id:
        return []
    try:
        return await asyncio.to_thread(state.read_model.get_available_countries, session_id)
    except Exception as e:
        logger.error("获取国家列表失败: %s", e, exc_info=True)
        return []


@router.get("/results/regions")
async def get_available_regions():
    """获取中国各省级行政区的频道统计（用于二级筛选联动）"""
    state = _get_state()
    service = _get_check_service()
    session_id = ""
    if service and service.session_id:
        session_id = service.session_id
    elif state and state.event_store:
        session_id = state.event_store.current_session_id
    if not session_id:
        return []
    try:
        return await asyncio.to_thread(state.read_model.get_available_regions, session_id)
    except Exception as e:
        logger.error("获取地区列表失败: %s", e, exc_info=True)
        return []


@router.get("/results/source-health")
async def get_source_health():
    state = _get_state()
    service = _get_check_service()
    session_id = ""
    if service and service.session_id:
        session_id = service.session_id
    elif state and state.event_store:
        session_id = state.event_store.current_session_id
    if not session_id:
        return []
    try:
        return await asyncio.to_thread(state.read_model.get_source_download_stats, session_id)
    except Exception as e:
        logger.error("获取源健康状态失败: %s", e, exc_info=True)
        return []


@router.get("/results/stats")
async def get_results_stats():
    state = _get_state()
    service = _get_check_service()
    if service and service.session_id:
        progress = service.get_progress()
        return {
            "total": progress["total"],
            "checked": progress["checked"],
            "valid": progress["valid"],
            "likely_valid": progress.get("likely_valid", 0),
            "invalid": progress["invalid"],
            "is_running": progress["is_running"],
        }
    db_stats = await asyncio.to_thread(state.database.get_stats)
    return {
        "total": 0, "checked": 0, "valid": 0, "likely_valid": 0, "invalid": 0,
        "is_running": False, "db_stats": db_stats,
    }


@router.get("/results/history")
async def get_check_history():
    """获取历史检测记录"""
    state = _get_state()
    if not state:
        return []
    try:
        return await asyncio.to_thread(state.event_store.get_history, 50)
    except Exception as e:
        logger.warning("获取历史记录失败: %s", e)
        return []


class QuickCheckItem(BaseModel):
    url: str = ""
    name: str = ""


class QuickCheckResponse(BaseModel):
    results: list[dict] = []


@router.post("/results/quick-check")
async def quick_check_latency(items: list[QuickCheckItem]):
    """实时检测一批频道的当前延迟（HEAD 请求），不写入数据库"""
    if not items:
        return {"results": []}

    import aiohttp
    import ssl
    import time

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_context, limit=50)
    timeout = aiohttp.ClientTimeout(total=5, connect=3)

    async def probe_one(item: QuickCheckItem, session: aiohttp.ClientSession):
        url = item.url
        start = time.time()
        try:
            async with session.head(url, allow_redirects=True, ssl=False) as resp:
                elapsed_ms = int((time.time() - start) * 1000)
                return {
                    "url": url,
                    "name": item.name,
                    "latency": elapsed_ms,
                    "status": resp.status,
                    "ok": resp.status < 400,
                }
        except asyncio.TimeoutError:
            return {"url": url, "name": item.name, "latency": -1, "status": 0, "ok": False, "error": "超时"}
        except Exception as e:
            return {"url": url, "name": item.name, "latency": -1, "status": 0, "ok": False, "error": str(e)[:60]}

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [probe_one(item, session) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            processed.append({"url": items[i].url, "name": items[i].name, "latency": -1, "status": 0, "ok": False, "error": str(r)[:60]})
        else:
            processed.append(r)

    return {"results": processed}


@router.post("/results/refresh-latency", status_code=202)
async def refresh_results_latency(session_id: str = ""):
    """触发异步全量延迟刷新，立即返回202"""
    state = _get_state()

    if state._refresh_latency_task is not None and not state._refresh_latency_task.done():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={"error": "刷新任务正在运行中", "progress": state._refresh_latency_progress},
        )

    service = _get_check_service()
    if not session_id and service and service.session_id:
        session_id = service.session_id
    if not session_id and state.event_store and state.event_store.current_session_id:
        session_id = state.event_store.current_session_id
    if not session_id:
        def _latest_session():
            from sqlalchemy import text as sa_text
            with state.event_store.get_session() as s:
                row = s.execute(
                    sa_text("SELECT session_id FROM channel_results GROUP BY session_id ORDER BY MAX(created_at) DESC LIMIT 1")
                ).first()
                return row[0] if row else ""
        session_id = await asyncio.to_thread(_latest_session)

    if not session_id:
        raise HTTPException(400, "没有检测结果可刷新")

    def _has_data():
        from sqlalchemy import text as sa_text
        with state.event_store.get_session() as s:
            cnt = s.execute(
                sa_text("SELECT COUNT(*) FROM channel_results WHERE session_id = :sid"),
                {"sid": session_id},
            ).scalar() or 0
            return cnt > 0

    if not await asyncio.to_thread(_has_data):
        raise HTTPException(400, "该 session 没有物化数据，无法刷新")

    def _fetch_urls():
        from sqlalchemy import text as sa_text
        with state.event_store.get_session() as s:
            rows = s.execute(
                sa_text("SELECT DISTINCT url FROM channel_results WHERE session_id = :sid AND url != ''"),
                {"sid": session_id},
            ).fetchall()
            mat_urls = set(r[0] for r in rows)
            evt_rows = s.execute(
                sa_text("SELECT DISTINCT json_extract(payload, '$.url') FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.url') != ''"),
                {"sid": session_id},
            ).fetchall()
            evt_urls = set(r[0] for r in evt_rows if r[0])
            return list(mat_urls | evt_urls)

    urls = await asyncio.to_thread(_fetch_urls)
    total = len(urls)
    if total == 0:
        return {"total": 0, "checked": 0, "updated": 0}

    import random
    task_id = f"refresh_lat_{int(time.time())}_{random.randint(1000, 9999)}"
    state._refresh_latency_task_id = task_id
    state._refresh_latency_progress = {"checked": 0, "total": total, "updated": 0}
    state._refresh_latency_started_at = datetime.datetime.now().isoformat()

    def _reset_latency():
        from sqlalchemy import text as sa_text
        import json as _json
        with state.event_store.get_session() as s:
            s.execute(
                sa_text("UPDATE channel_results SET latency = -1, is_valid = 0, quality_tier = 'invalid' WHERE session_id = :sid"),
                {"sid": session_id},
            )
            rows = s.execute(
                sa_text("SELECT id, payload FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked'"),
                {"sid": session_id},
            ).fetchall()
            for row in rows:
                try:
                    p = _json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
                    p["latency"] = -1
                    p["is_valid"] = False
                    p["quality_tier"] = "invalid"
                    s.execute(
                        sa_text("UPDATE check_events SET payload = :p WHERE id = :eid"),
                        {"p": _json.dumps(p, ensure_ascii=False), "eid": row[0]},
                    )
                except Exception:
                    pass
            s.commit()
    await asyncio.to_thread(_reset_latency)

    state._refresh_latency_task = asyncio.create_task(
        _run_refresh_latency_background(state, session_id, urls, task_id)
    )

    return {"task_id": task_id, "total": total, "status": "running"}


async def _run_refresh_latency_background(state, session_id, urls, task_id):
    """后台执行全量延迟检测，通过SSE推送进度"""
    import aiohttp, ssl, time

    def _update_check_events_payload(s, sa_text, _json, sid, url, lat, is_valid, quality_tier):
        rows = s.execute(
            sa_text("SELECT id, payload FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.url') = :url"),
            {"sid": sid, "url": url},
        ).fetchall()
        for row in rows:
            try:
                p = _json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
                p["latency"] = lat
                p["is_valid"] = is_valid
                p["quality_tier"] = quality_tier
                s.execute(
                    sa_text("UPDATE check_events SET payload = :p WHERE id = :eid"),
                    {"p": _json.dumps(p, ensure_ascii=False), "eid": row[0]},
                )
            except Exception:
                pass

    total = len(urls)
    checked = 0
    updated = 0
    ok_urls = []
    last_broadcast_time = time.time()
    BROADCAST_INTERVAL = 1.0
    BROADCAST_BATCH_SIZE = 50

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=200, force_close=True, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=0.5, connect=0.3)

    async def _maybe_broadcast_progress():
        nonlocal last_broadcast_time
        now = time.time()
        if checked % BROADCAST_BATCH_SIZE == 0 or (now - last_broadcast_time >= BROADCAST_INTERVAL):
            progress = {"checked": checked, "total": total, "updated": updated}
            state._refresh_latency_progress = progress
            await state.broadcast("refresh_latency_progress", progress)
            last_broadcast_time = now

    async def probe(url):
        try:
            start_t = time.time()
            async with session.head(url, ssl=False) as r:
                elapsed_ms = int((time.time() - start_t) * 1000)
                return (url, elapsed_ms, r.status < 400)
        except:
            return (url, -1, False)

    sem = asyncio.Semaphore(200)

    async def bounded_probe(url):
        async with sem:
            return await probe(url)

    try:
        import logging as _logging
        _asyncio_logger = _logging.getLogger('asyncio')
        _orig_level = _asyncio_logger.level
        _asyncio_logger.setLevel(_logging.CRITICAL)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [bounded_probe(u) for u in urls]
            for coro in asyncio.as_completed(tasks):
                try:
                    url, lat, ok = await coro
                except:
                    continue
                checked += 1
                if ok and lat > 0:
                    ok_urls.append((lat, url))
                    updated += 1

                await _maybe_broadcast_progress()

                if len(ok_urls) >= 500:
                    batch = ok_urls[:]
                    ok_urls.clear()
                    def _write(batch):
                        from sqlalchemy import text as sa_text
                        import json as _json
                        with state.event_store.get_session() as s:
                            for lat, url in batch:
                                s.execute(
                                    sa_text("UPDATE channel_results SET latency = :lat, is_valid = 1, quality_tier = 'valid' WHERE session_id = :sid AND url = :url"),
                                    {"lat": lat, "sid": session_id, "url": url},
                                )
                                _update_check_events_payload(s, sa_text, _json, session_id, url, lat, True, "valid")
                            s.commit()
                    await asyncio.to_thread(_write, batch)

            final_progress = {"checked": total, "total": total, "updated": updated}
            state._refresh_latency_progress = final_progress
            await state.broadcast("refresh_latency_completed", {
                **final_progress,
                "task_id": task_id,
            })

            if ok_urls:
                def _write_last(batch):
                    from sqlalchemy import text as sa_text
                    import json as _json
                    with state.event_store.get_session() as s:
                        for lat, url in batch:
                            s.execute(
                                sa_text("UPDATE channel_results SET latency = :lat, is_valid = 1, quality_tier = 'valid' WHERE session_id = :sid AND url = :url"),
                                {"lat": lat, "sid": session_id, "url": url},
                            )
                            _update_check_events_payload(s, sa_text, _json, session_id, url, lat, True, "valid")
                        s.commit()
                await asyncio.to_thread(_write_last, ok_urls)

        logger.info("异步延迟刷新完成: task_id=%s, checked=%d, updated=%d", task_id, checked, updated)

    except Exception as e:
        logger.error("异步延迟刷新失败: task_id=%s, error=%s", task_id, e, exc_info=True)
        await state.broadcast("refresh_latency_failed", {
            "error": str(e)[:200],
            "task_id": task_id,
        })
    finally:
        _asyncio_logger.setLevel(_orig_level)
        state._refresh_latency_task = None
        state._refresh_latency_task_id = None


@router.post("/results/thorough-check", status_code=202)
async def thorough_check(session_id: str = "", urls: str = ""):
    """触发彻底版检测(GET+Range)，urls为逗号分隔的base64编码URL列表，空则全量"""
    state = _get_state()

    if state._refresh_latency_task is not None and not state._refresh_latency_task.done():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={"error": "检测任务正在运行中", "progress": state._refresh_latency_progress},
        )

    service = _get_check_service()
    if not session_id and service and service.session_id:
        session_id = service.session_id
    if not session_id and state.event_store and state.event_store.current_session_id:
        session_id = state.event_store.current_session_id
    if not session_id:
        def _latest_session():
            from sqlalchemy import text as sa_text
            with state.event_store.get_session() as s:
                row = s.execute(
                    sa_text("SELECT session_id FROM channel_results GROUP BY session_id ORDER BY MAX(created_at) DESC LIMIT 1")
                ).first()
                return row[0] if row else ""
        session_id = await asyncio.to_thread(_latest_session)

    if not session_id:
        raise HTTPException(400, "没有检测结果可检测")

    def _has_data():
        from sqlalchemy import text as sa_text
        with state.event_store.get_session() as s:
            cnt = s.execute(
                sa_text("SELECT COUNT(*) FROM channel_results WHERE session_id = :sid"),
                {"sid": session_id},
            ).scalar() or 0
            return cnt > 0

    if not await asyncio.to_thread(_has_data):
        raise HTTPException(400, "该 session 没有物化数据，无法检测")

    def _fetch_urls():
        from sqlalchemy import text as sa_text
        with state.event_store.get_session() as s:
            rows = s.execute(
                sa_text("SELECT DISTINCT url FROM channel_results WHERE session_id = :sid AND url != ''"),
                {"sid": session_id},
            ).fetchall()
            mat_urls = set(r[0] for r in rows)
            evt_rows = s.execute(
                sa_text("SELECT DISTINCT json_extract(payload, '$.url') FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.url') != ''"),
                {"sid": session_id},
            ).fetchall()
            evt_urls = set(r[0] for r in evt_rows if r[0])
            return list(mat_urls | evt_urls)

    if urls:
        try:
            import base64 as _b64
            decoded_urls = urllib.parse.unquote(urls)
            selected_urls = [urllib.parse.unquote(_b64.b64decode(u).decode("utf-8")) for u in decoded_urls.split(",") if u.strip()]
            logger.info(f"thorough_check: decoded {len(selected_urls)} urls from request")
        except Exception as e:
            logger.warning(f"thorough_check: url decode failed: {e}")
            selected_urls = []
        if selected_urls:
            all_urls = await asyncio.to_thread(_fetch_urls)
            all_set = set(all_urls)
            matched = [u for u in selected_urls if u in all_set]
            logger.info(f"thorough_check: {len(selected_urls)} selected, {len(all_urls)} total, {len(matched)} matched")
            urls = matched if matched else selected_urls
        else:
            urls = await asyncio.to_thread(_fetch_urls)
    else:
        urls = await asyncio.to_thread(_fetch_urls)
    total = len(urls)
    if total == 0:
        return {"total": 0, "checked": 0, "updated": 0}

    task_id = f"thorough_{int(time.time())}_{random.randint(1000, 9999)}"
    state._refresh_latency_task_id = task_id
    state._refresh_latency_progress = {"checked": 0, "total": total, "updated": 0}
    state._refresh_latency_started_at = datetime.datetime.now().isoformat()

    def _reset_latency():
        from sqlalchemy import text as sa_text
        import json as _json
        with state.event_store.get_session() as s:
            if urls:
                url_placeholders = ",".join(f":u{i}" for i in range(len(urls)))
                url_params = {f"u{i}": u for i, u in enumerate(urls)}
                s.execute(
                    sa_text(f"UPDATE channel_results SET latency = -1, is_valid = 0, quality_tier = 'invalid' WHERE session_id = :sid AND url IN ({url_placeholders})"),
                    {"sid": session_id, **url_params},
                )
                reset_rows = s.execute(
                    sa_text(f"SELECT id, payload FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.url') IN ({url_placeholders})"),
                    {"sid": session_id, **url_params},
                ).fetchall()
            else:
                s.execute(
                    sa_text("UPDATE channel_results SET latency = -1, is_valid = 0, quality_tier = 'invalid' WHERE session_id = :sid"),
                    {"sid": session_id},
                )
                reset_rows = s.execute(
                    sa_text("SELECT id, payload FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked'"),
                    {"sid": session_id},
                ).fetchall()
            for row in reset_rows:
                try:
                    p = _json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
                    p["latency"] = -1
                    p["is_valid"] = False
                    p["quality_tier"] = "invalid"
                    s.execute(
                        sa_text("UPDATE check_events SET payload = :p WHERE id = :eid"),
                        {"p": _json.dumps(p, ensure_ascii=False), "eid": row[0]},
                    )
                except Exception:
                    pass
            s.commit()
    await asyncio.to_thread(_reset_latency)

    state._refresh_latency_task = asyncio.create_task(
        _run_thorough_check_background(state, session_id, urls, task_id)
    )

    return {"task_id": task_id, "total": total, "status": "running"}


async def _run_thorough_check_background(state, session_id, urls, task_id):
    """后台执行彻底版检测(GET+Range)，通过SSE推送进度"""
    import aiohttp, ssl, time as _time

    def _update_check_events_payload(s, sa_text, _json, sid, url, lat, is_valid, quality_tier):
        rows = s.execute(
            sa_text("SELECT id, payload FROM check_events WHERE session_id = :sid AND event_type = 'channel_checked' AND json_extract(payload, '$.url') = :url"),
            {"sid": sid, "url": url},
        ).fetchall()
        for row in rows:
            try:
                p = _json.loads(row[1]) if isinstance(row[1], str) else dict(row[1])
                p["latency"] = lat
                p["is_valid"] = is_valid
                p["quality_tier"] = quality_tier
                s.execute(
                    sa_text("UPDATE check_events SET payload = :p WHERE id = :eid"),
                    {"p": _json.dumps(p, ensure_ascii=False), "eid": row[0]},
                )
            except Exception:
                pass

    total = len(urls)
    checked = 0
    updated = 0
    ok_urls = []
    last_broadcast_time = _time.time()
    BROADCAST_INTERVAL = 1.0
    BROADCAST_BATCH_SIZE = 50

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=100, force_close=True, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=8, connect=3)

    async def _maybe_broadcast_progress():
        nonlocal last_broadcast_time
        now = _time.time()
        if checked % BROADCAST_BATCH_SIZE == 0 or (now - last_broadcast_time >= BROADCAST_INTERVAL):
            progress = {"checked": checked, "total": total, "updated": updated}
            state._refresh_latency_progress = progress
            await state.broadcast("refresh_latency_progress", progress)
            last_broadcast_time = now

    async def probe_thorough(url):
        try:
            start_t = _time.time()
            async with session.get(url, headers={"Range": "bytes=0-4095"}, ssl=False, timeout=aiohttp.ClientTimeout(total=8, connect=3)) as r:
                body = await r.content.read(4096)
                elapsed_ms = int((_time.time() - start_t) * 1000)
                ok = r.status < 400 and len(body) >= 1
                return (url, elapsed_ms, ok)
        except:
            return (url, -1, False)

    sem = asyncio.Semaphore(100)

    async def bounded_probe(url):
        async with sem:
            return await probe_thorough(url)

    try:
        import logging as _logging
        _asyncio_logger = _logging.getLogger('asyncio')
        _orig_level = _asyncio_logger.level
        _asyncio_logger.setLevel(_logging.CRITICAL)

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [bounded_probe(u) for u in urls]
            for coro in asyncio.as_completed(tasks):
                try:
                    url, lat, ok = await coro
                except:
                    continue
                checked += 1
                if ok and lat > 0:
                    ok_urls.append((lat, url))
                    updated += 1

                await _maybe_broadcast_progress()

                if len(ok_urls) >= 500:
                    batch = ok_urls[:]
                    ok_urls.clear()
                    def _write(batch):
                        from sqlalchemy import text as sa_text
                        import json as _json
                        with state.event_store.get_session() as s:
                            for lat, url in batch:
                                s.execute(
                                    sa_text("UPDATE channel_results SET latency = :lat, is_valid = 1, quality_tier = 'valid' WHERE session_id = :sid AND url = :url"),
                                    {"lat": lat, "sid": session_id, "url": url},
                                )
                                _update_check_events_payload(s, sa_text, _json, session_id, url, lat, True, "valid")
                            s.commit()
                    await asyncio.to_thread(_write, batch)

            final_progress = {"checked": total, "total": total, "updated": updated}
            state._refresh_latency_progress = final_progress
            await state.broadcast("refresh_latency_completed", {
                **final_progress,
                "task_id": task_id,
            })

            if ok_urls:
                def _write_last(batch):
                    from sqlalchemy import text as sa_text
                    import json as _json
                    with state.event_store.get_session() as s:
                        for lat, url in batch:
                            s.execute(
                                sa_text("UPDATE channel_results SET latency = :lat, is_valid = 1, quality_tier = 'valid' WHERE session_id = :sid AND url = :url"),
                                {"lat": lat, "sid": session_id, "url": url},
                            )
                            _update_check_events_payload(s, sa_text, _json, session_id, url, lat, True, "valid")
                        s.commit()
                await asyncio.to_thread(_write_last, ok_urls)

        logger.info("彻底版检测完成: task_id=%s, checked=%d, updated=%d", task_id, checked, updated)

    except Exception as e:
        logger.error("彻底版检测失败: task_id=%s, error=%s", task_id, e, exc_info=True)
        await state.broadcast("refresh_latency_failed", {
            "error": str(e)[:200],
            "task_id": task_id,
        })
    finally:
        _asyncio_logger.setLevel(_orig_level)
        state._refresh_latency_task = None
        state._refresh_latency_task_id = None


@router.post("/results/refresh-latency/stop")
async def stop_refresh_latency():
    """停止正在运行的延迟刷新/彻底版检测任务"""
    state = _get_state()
    if state._refresh_latency_task is None or state._refresh_latency_task.done():
        return {"status": "not_running"}
    state._refresh_latency_task.cancel()
    state._refresh_latency_task = None
    state._refresh_latency_task_id = None
    state._refresh_latency_progress = {"checked": 0, "total": 0, "updated": 0}
    return {"status": "stopped"}


@router.get("/results/refresh-latency/status")
async def get_refresh_latency_status():
    """查询异步延迟刷新任务状态"""
    state = _get_state()
    is_running = state._refresh_latency_task is not None and not state._refresh_latency_task.done()
    return {
        "is_running": is_running,
        "progress": state._refresh_latency_progress,
        "task_id": state._refresh_latency_task_id if is_running else None,
    }


@router.post("/results/save")
async def save_results_to_db():
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        raise HTTPException(400, "没有检测结果可保存")
    results_data = await asyncio.to_thread(state.read_model.get_checked_results_raw, service.session_id)
    if not results_data:
        raise HTTPException(400, "没有检测结果可保存")
    history_id = await asyncio.to_thread(state.database.save_check_result, results_data, "", service.session_id)
    return {"history_id": history_id, "saved": len(results_data)}


@router.get("/favorites")
async def get_favorites(folder_id: Optional[int] = None, page: int = 1, per_page: int = 50, sort: str = "default"):
    state = _get_state()
    from iptv_check.infra.database import FavoriteModel, ChannelModel, CheckResultModel
    from iptv_check.core.parser import _translate_channel_name, _map_group_name, _infer_country_code
    _RADIO_KW = {"广播", "电台", "radio", "fm", "am", "broadcast"}
    _RADIO_URL_KW = {"qingting.fm", "xmcdn.com", "ximalaya", "lrc.la"}
    def _is_radio(name, group, url):
        text = f"{name or ''} {group or ''} {url or ''}".lower()
        url_lower = (url or "").lower()
        return any(kw in text for kw in _RADIO_KW) or any(kw in url_lower for kw in _RADIO_URL_KW)
    LAG_SECONDS = 6 * 3600  # 超过 6 小时未更新的延迟重新查询

    def _query():
        from iptv_check.infra.cn_time import cn_now
        from sqlalchemy import text as sa_text
        with state.database.get_session() as session:
            cols = "id,channel_id,name,url,folder_id,channel_group,sort_order,latency,latency_updated_at,created_at"
            where_clause = ""
            params = {}
            if folder_id is not None:
                where_clause = "WHERE folder_id = :fid"
                params["fid"] = folder_id

            # 查询总数
            count_sql = f"SELECT COUNT(*) FROM favorites {where_clause}"
            total = session.execute(sa_text(count_sql), params).scalar() or 0

            # 排序映射（收藏表无 speed 列，仅支持名称和延迟排序）
            _fav_sort = {
                "default":     "sort_order ASC, created_at DESC",
                "name_asc":    "name ASC",
                "name_desc":   "name DESC",
                "latency_asc": "CASE WHEN latency IS NULL OR latency < 0 THEN 999999 ELSE latency END ASC",
                "latency_desc": "latency DESC",
            }
            _fav_order = _fav_sort.get(sort, _fav_sort["default"])

            # 分页查询
            offset = (page - 1) * per_page
            data_sql = f"SELECT {cols} FROM favorites {where_clause} ORDER BY {_fav_order} LIMIT :lim OFFSET :off"
            data_params = {**params, "lim": per_page, "off": offset}
            rows = session.execute(sa_text(data_sql), data_params).fetchall()

            items = [
                {"id": r.id, "channel_id": r.channel_id,
                 "name": r.name,
                 "name_cn": _translate_channel_name(r.name) or "",
                 "url": r.url,
                 "folder_id": r.folder_id,
                 "sort_order": r.sort_order,
                 "latency": r.latency,
                 "channel_group": _map_group_name(r.channel_group),
                 "region": _infer_region(r.name, r.channel_group, _infer_country_code(r.name, r.channel_group)),
                 "is_radio": _is_radio(r.name, r.channel_group, r.url),
                 "country": _infer_country_code(r.name, r.channel_group),
                 "frequency": Channel._extract_frequency(r.name, r.channel_group),
                 "created_at": r.created_at.isoformat() if hasattr(r.created_at, 'isoformat') else str(r.created_at)}
                for r in rows
            ]
            return items, total
    favorites, total = await asyncio.to_thread(_query)
    return {"favorites": favorites, "total": total, "page": page, "per_page": per_page}

@router.post("/favorites/refresh-latency")
async def refresh_favorites_latency():
    """实时检测收藏夹中所有频道的延迟（HTTP HEAD请求）"""
    state = _get_state()
    from iptv_check.infra.cn_time import cn_now
    import aiohttp
    import ssl

    def _fetch_favorites():
        from sqlalchemy import text as sa_text
        with state.database.get_session() as session:
            rows = session.exec(sa_text("SELECT id, url, name FROM favorites WHERE url != ''")).all()
            return [{"id": r[0], "url": r[1], "name": r[2]} for r in rows]

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
        from sqlalchemy import text as sa_text
        count = 0
        with state.database.get_session() as session:
            for res in results:
                if res["ok"] and res["latency"] > 0:
                    session.execute(
                        sa_text("UPDATE favorites SET latency = :lat, latency_updated_at = :ts WHERE id = :fid"),
                        {"lat": res["latency"], "ts": now, "fid": res["id"]}
                    )
                    count += 1
            session.commit()
        return count

    update_count = await asyncio.to_thread(_update, processed_results)

    return {"updated": update_count, "results": processed_results}


@router.post("/favorites")
async def add_favorite(req: AddFavoriteRequest):
    state = _get_state()
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
    state = _get_state()
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
    state = _get_state()
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
    state = _get_state()
    from iptv_check.infra.database import FavoriteModel
    from fastapi.responses import Response
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
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="没有可导出的收藏数据")
    lines = ["#EXTM3U"]
    for name, url in items:
        lines.append(f'#EXTINF:-1,{name}')
        lines.append(url)
    content = "\n".join(lines) + "\n"
    return Response(content=content, media_type="audio/mpegurl", headers={"Content-Disposition": "attachment; filename=favorites.m3u"})


@router.get("/favorite-folders")
async def get_favorite_folders():
    state = _get_state()
    def _query():
        from sqlalchemy import text as sa_text
        with state.database.get_session() as session:
            folders = session.exec(
                sa_text("SELECT id, name, icon, sort_order FROM favorite_folders ORDER BY sort_order")
            ).all()
            # 一条 SQL 查全部文件夹的收藏数
            count_map = {}
            for row in session.exec(
                sa_text("SELECT folder_id, COUNT(*) as cnt FROM favorites GROUP BY folder_id")
            ).all():
                count_map[row.folder_id] = row.cnt
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
    state = _get_state()
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
    state = _get_state()
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
    state = _get_state()
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
    state = _get_state()
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
    state = _get_state()
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
    state = _get_state()
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


@router.get("/report")
async def get_quality_report():
    import traceback
    try:
        state = _get_state()
        if not state:
            return {"error": "服务未初始化"}

        service = _get_check_service()
        results_data = []
        if service and service.session_id:
            try:
                results_data = await asyncio.to_thread(state.read_model.get_checked_results_raw, service.session_id)
            except Exception as e:
                logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
                return {"error": f"读取检测结果失败: {str(e)}"}

        if not results_data:
            return {"error": "没有检测结果"}

        from iptv_check.models.check_result import CheckResult
        from iptv_check.models.channel import Channel
        results = []
        for rd in results_data:
            try:
                ch = Channel(
                    name=rd.get("channel", {}).get("name", "未知"),
                    url=rd.get("channel", {}).get("url", ""),
                    group=rd.get("channel", {}).get("group", ""),
                    sources=rd.get("channel", {}).get("sources", []),
                )
                r = CheckResult(
                    channel=ch,
                    is_valid=rd.get("is_valid", False),
                    quality_tier=rd.get("quality_tier", ""),
                    latency=rd.get("latency", -1),
                    speed=rd.get("speed", "-"),
                    details=rd.get("details", ""),
                )
                results.append(r)
            except Exception as e:
                logger.warning("解析检测结果项失败: %s", e)
                continue

        if not results:
            return {"error": "没有有效的检测结果"}

        valid = [r for r in results if r.quality_tier == "valid" or (not r.quality_tier and r.is_valid)]
        likely_valid = [r for r in results if r.quality_tier == "likely_valid"]
        invalid = [r for r in results if r.quality_tier == "invalid" or (not r.quality_tier and not r.is_valid)]
        latencies = []
        for r in valid:
            try:
                lv = float(r.latency) if r.latency not in ("-", "", -1) else -1
                if lv > 0:
                    latencies.append(lv)
            except (ValueError, TypeError):
                pass

        latency_ranges = {"<50ms": 0, "50-100ms": 0, "100-200ms": 0, "200-500ms": 0, "500ms+": 0}
        for l in latencies:
            if l < 50: latency_ranges["<50ms"] += 1
            elif l < 100: latency_ranges["50-100ms"] += 1
            elif l < 200: latency_ranges["100-200ms"] += 1
            elif l < 500: latency_ranges["200-500ms"] += 1
            else: latency_ranges["500ms+"] += 1

        source_stats = {}
        for r in results:
            if not r.channel:
                continue
            for src in r.channel.sources or []:
                if src not in source_stats:
                    source_stats[src] = {"total": 0, "valid": 0, "latencies": []}
                source_stats[src]["total"] += 1
                if r.is_valid:
                    source_stats[src]["valid"] += 1
                    try:
                        lat = float(r.latency)
                        if lat > 0:
                            source_stats[src]["latencies"].append(lat)
                    except (ValueError, TypeError):
                        pass

        source_ranking = []
        for name, stats in source_stats.items():
            avg_lat = sum(stats["latencies"]) / len(stats["latencies"]) if stats["latencies"] else 0
            source_ranking.append({
                "name": name, "total": stats["total"], "valid": stats["valid"],
                "invalid": stats["total"] - stats["valid"],
                "rate": round(stats["valid"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0,
                "avg_latency": round(avg_lat, 0),
            })
        source_ranking.sort(key=lambda x: x["rate"], reverse=True)

        from iptv_check.server.app import _compute_group_stats
        return {
            "total": len(results), "valid": len(valid), "likely_valid": len(likely_valid), "invalid": len(invalid),
            "valid_rate": round(len(valid) / len(results) * 100, 1) if results else 0,
            "avg_latency": round(sum(latencies) / len(latencies), 0) if latencies else 0,
            "min_latency": min(latencies) if latencies else 0,
            "max_latency": max(latencies) if latencies else 0,
            "latency_distribution": latency_ranges,
            "source_ranking": source_ranking,
            "group_stats": _compute_group_stats(results),
        }
    except Exception as e:
        logger.error("生成质量报告失败: %s\n%s", e, traceback.format_exc())
        return {"error": f"生成报告失败: {str(e)}"}


@router.get("/trends/channel/{channel_id}")
async def get_channel_trend(channel_id: int, days: int = 7):
    state = _get_state()
    trend = await asyncio.to_thread(state.database.get_channel_trend, channel_id, days)
    stability = await asyncio.to_thread(state.database.get_channel_stability_stats, channel_id, days)
    return {"trend": trend, "stability": stability, "days": days}


@router.get("/trends/stable-channels")
async def get_top_stable_channels(days: int = 7, limit: int = 50):
    state = _get_state()
    return {"channels": await asyncio.to_thread(state.database.get_top_stable_channels, days, limit)}


@router.get("/trends/history-compare")
async def compare_history(h1: int = 0, h2: int = 0):
    state = _get_state()
    history = await asyncio.to_thread(state.event_store.get_history, 20)
    if len(history) < 2:
        return {"error": "至少需要2次检测历史", "sessions": []}

    sessions = []
    for h in history[:10]:
        sid = h.get("session_id", "")
        total = h.get("total", 0)
        valid = h.get("valid", 0)
        invalid = h.get("invalid", 0)
        elapsed = h.get("elapsed", 0)
        created = h.get("created_at", "")
        valid_rate = round(valid / total * 100, 1) if total > 0 else 0
        sessions.append({
            "session_id": sid, "total": total, "valid": valid,
            "invalid": invalid, "valid_rate": valid_rate,
            "elapsed": round(elapsed, 1), "created_at": created,
        })

    if len(sessions) >= 2:
        s1, s2 = sessions[0], sessions[1]
        delta_valid_rate = round(s1["valid_rate"] - s2["valid_rate"], 1)
        delta_valid = s1["valid"] - s2["valid"]
        delta_total = s1["total"] - s2["total"]
        comparison = {
            "latest": s1,
            "previous": s2,
            "delta": {
                "valid_rate": delta_valid_rate,
                "valid": delta_valid,
                "total": delta_total,
                "trend": "up" if delta_valid_rate > 0 else ("down" if delta_valid_rate < 0 else "stable"),
            }
        }
    else:
        comparison = None

    return {"sessions": sessions, "comparison": comparison}


@router.get("/recommend")
async def get_recommendations(max_per_group: int = 3, prefer_low_latency: bool = True):
    import traceback
    try:
        state = _get_state()
        service = _get_check_service()
        if not service or not service.session_id:
            return {"error": "没有检测结果"}

        try:
            results_data = await asyncio.to_thread(state.read_model.get_checked_results_raw, service.session_id)
        except Exception as e:
            logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
            return {"error": f"读取检测结果失败: {str(e)}"}

        if not results_data:
            return {"error": "没有检测结果"}

        from iptv_check.models.check_result import CheckResult
        from iptv_check.models.channel import Channel
        check_results = []
        for rd in results_data:
            try:
                ch = Channel(
                    name=rd.get("channel", {}).get("name", "未知"),
                    url=rd.get("channel", {}).get("url", ""),
                    group=rd.get("channel", {}).get("group", ""),
                    sources=rd.get("channel", {}).get("sources", []),
                )
                r = CheckResult(
                    channel=ch,
                    is_valid=rd.get("is_valid", False),
                    quality_tier=rd.get("quality_tier", ""),
                    latency=rd.get("latency", -1),
                    speed=rd.get("speed", "-"),
                    details=rd.get("details", ""),
                )
                check_results.append(r)
            except Exception as e:
                logger.warning("解析推荐数据项失败: %s", e)
                continue

        if not check_results:
            return {"error": "没有有效的检测结果"}

        from iptv_check.core.recommender import SourceRecommender
        recs = SourceRecommender.recommend(
            check_results, local_isp=state.local_isp,
            max_channels_per_group=max_per_group, prefer_low_latency=prefer_low_latency,
        )
        total = sum(len(v) for v in recs.values())
        return {
            "recommendations": {
                name: [
                    {
                        "name": v["channel"].name, "url": v["result"].channel.url,
                        "group": v["channel"].group, "latency": v["result"].latency_display,
                        "speed": v["result"].speed, "score": v["score"],
                        "reasons": v["reasons"], "sources": v["channel"].sources,
                    }
                    for v in variants
                ]
                for name, variants in recs.items()
            },
            "total_channels": len(recs), "total_variants": total,
        }
    except Exception as e:
        logger.error("获取推荐失败: %s\n%s", e, traceback.format_exc())
        return {"error": f"获取推荐失败: {str(e)}"}


@router.get("/recommend/m3u")
async def get_recommend_m3u(max_per_group: int = 3):
    import traceback
    try:
        state = _get_state()
        service = _get_check_service()
        if not service or not service.session_id:
            raise HTTPException(400, "没有检测结果")

        try:
            results_data = await asyncio.to_thread(state.read_model.get_checked_results_raw, service.session_id)
        except Exception as e:
            logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
            raise HTTPException(500, f"读取检测结果失败: {e}")

        if not results_data:
            raise HTTPException(400, "没有检测结果")

        from iptv_check.models.check_result import CheckResult
        from iptv_check.models.channel import Channel
        check_results = []
        for rd in results_data:
            try:
                ch = Channel(
                    name=rd.get("channel", {}).get("name", "未知"),
                    url=rd.get("channel", {}).get("url", ""),
                    group=rd.get("channel", {}).get("group", ""),
                    sources=rd.get("channel", {}).get("sources", []),
                )
                r = CheckResult(
                    channel=ch,
                    is_valid=rd.get("is_valid", False),
                    quality_tier=rd.get("quality_tier", ""),
                    latency=rd.get("latency", -1),
                    speed=rd.get("speed", "-"),
                    details=rd.get("details", ""),
                )
                check_results.append(r)
            except Exception as e:
                logger.warning("解析推荐数据项失败: %s", e)
                continue

        if not check_results:
            raise HTTPException(400, "没有有效的检测结果")

        from iptv_check.core.recommender import SourceRecommender
        from fastapi.responses import Response
        recs = SourceRecommender.recommend(check_results, local_isp=state.local_isp, max_channels_per_group=max_per_group)
        m3u_content = SourceRecommender.generate_m3u(recs, local_isp=state.local_isp)
        return Response(content=m3u_content, media_type="audio/x-mpegurl", headers={"Content-Disposition": "attachment; filename=recommended.m3u"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("生成推荐 M3U 失败: %s\n%s", e, traceback.format_exc())
        raise HTTPException(500, f"生成推荐 M3U 失败: {e}")


@router.get("/recommend/isp")
async def get_isp_recommendations(target_isp: str = None):
    import traceback
    try:
        state = _get_state()
        service = _get_check_service()
        if not service or not service.session_id:
            return {"error": "没有检测结果"}

        try:
            results_data = await asyncio.to_thread(state.read_model.get_checked_results_raw, service.session_id)
        except Exception as e:
            logger.error("读取检测结果失败: %s\n%s", e, traceback.format_exc())
            return {"error": f"读取检测结果失败: {str(e)}"}

        if not results_data:
            return {"error": "没有检测结果"}

        from iptv_check.models.check_result import CheckResult
        from iptv_check.models.channel import Channel
        check_results = []
        for rd in results_data:
            try:
                ch = Channel(
                    name=rd.get("channel", {}).get("name", "未知"),
                    url=rd.get("channel", {}).get("url", ""),
                    group=rd.get("channel", {}).get("group", ""),
                    sources=rd.get("channel", {}).get("sources", []),
                )
                r = CheckResult(
                    channel=ch,
                    is_valid=rd.get("is_valid", False),
                    quality_tier=rd.get("quality_tier", ""),
                    latency=rd.get("latency", -1),
                    speed=rd.get("speed", "-"),
                    details=rd.get("details", ""),
                )
                check_results.append(r)
            except Exception as e:
                logger.warning("解析 ISP 推荐数据项失败: %s", e)
                continue

        if not check_results:
            return {"error": "没有有效的检测结果"}

        from iptv_check.core.recommender import SourceRecommender
        isp = target_isp or state.local_isp
        recs = SourceRecommender.recommend_for_isp(check_results, isp)
        return {
            "isp": isp, "total": len(recs),
            "channels": [
                {"name": r.channel.name, "url": r.channel.url, "group": r.channel.group, "latency": r.latency_display, "sources": r.channel.sources}
                for r in recs
            ],
        }
    except Exception as e:
        logger.error("获取 ISP 推荐失败: %s\n%s", e, traceback.format_exc())
        return {"error": f"获取 ISP 推荐失败: {str(e)}"}


@router.post("/upload")
async def upload_file(req: UploadRequest):
    import os
    import base64
    from iptv_check.core.parser import PlaylistParser
    from iptv_check.server.app import DATA_DIR
    upload_dir = os.path.join(DATA_DIR, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, req.filename)
    content = base64.b64decode(req.content_base64)
    with open(file_path, "wb") as f:
        f.write(content)
    channels = PlaylistParser.parse_file(file_path)
    return {"filename": req.filename, "path": file_path, "channel_count": len(channels)}


@router.get("/live-channels")
async def get_live_channels(media_type: str = "all", session_id: str = ""):
    """电视模式：获取有效频道列表（按分组聚合，每频道取最优源）"""
    state = _get_state()
    service = _get_check_service()
    effective_session_id = session_id
    if not effective_session_id:
        if service and service.session_id:
            effective_session_id = service.session_id
        elif state and state.event_store:
            effective_session_id = state.event_store.current_session_id

    if not effective_session_id:
        return {"groups": [], "total": 0}

    try:
        return await asyncio.to_thread(state.read_model.get_live_channels, effective_session_id, media_type)
    except Exception:
        return {"groups": [], "total": 0}

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


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["channels"])


class UploadRequest(BaseModel):
    filename: str = "upload.m3u"
    content_base64: str = ""


    folder_id: Optional[int] = None


def _get_state():
    from iptv_check.server.app import get_app_state
    return get_app_state()


def _get_check_service():
    state = _get_state()
    return getattr(state, "_check_service", None)




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
    source: str = "",
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
                        source=source,
                        latency_min=latency_min, latency_max=latency_max,
                        speed_min=speed_min, speed_max=speed_max,
                    )
                return await asyncio.to_thread(
                    state.read_model.get_checked_channels,
                    session_id=effective_session_id,
                    tab=tab, page=page, per_page=per_page, search=search, sort=sort,
                    media_type=media_type, language=language,
                    country=country, region=region, category=category, quality=quality, protocol=protocol,
                    source=source,
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
async def refresh_results_latency(
    session_id: str = "",
    tab: str = "all",
    media_type: str = "all",
    country: str = "",
    region: str = "",
    category: str = "",
    quality: str = "",
    protocol: str = "",
    source: str = "",
    search: str = "",
    latency_min: float = -1,
    latency_max: float = -1,
    speed_min: float = -1,
    speed_max: float = -1,
):
    """触发异步全量延迟刷新（HEAD 探测），立即返回202。
    传入 tab/country 等筛选参数时仅刷新符合条件子集，否则刷新整个 session。"""
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
            from iptv_check.infra.repository.results_repo import ResultsRepository
            with state.event_store.get_session() as s:
                return ResultsRepository(s).latest_session_id()
        session_id = await asyncio.to_thread(_latest_session)

    if not session_id:
        raise HTTPException(400, "没有检测结果可刷新")

    def _has_data():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            return ResultsRepository(s).has_session_data(session_id)

    if not await asyncio.to_thread(_has_data):
        raise HTTPException(400, "该 session 没有物化数据，无法刷新")

    def _fetch_urls():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            return ResultsRepository(s).fetch_session_urls(session_id)

    def _fetch_filtered_urls():
        if state.read_model:
            return state.read_model.fetch_filtered_urls(
                session_id, tab, media_type, "", country, region, category,
                quality, protocol, source, latency_min, latency_max, speed_min, speed_max, search,
            )
        return []

    _has_filter = (
        tab != "all" or media_type != "all" or country or region or category
        or quality or protocol or source or search
        or latency_min >= 0 or latency_max >= 0 or speed_min >= 0 or speed_max >= 0
    )
    urls = await asyncio.to_thread(_fetch_filtered_urls if _has_filter else _fetch_urls)
    total = len(urls)
    if total == 0:
        return {"total": 0, "checked": 0, "updated": 0}

    import random
    task_id = f"refresh_lat_{int(time.time())}_{random.randint(1000, 9999)}"
    state._refresh_latency_task_id = task_id
    state._refresh_latency_progress = {"checked": 0, "total": total, "updated": 0}
    state._refresh_latency_started_at = datetime.datetime.now().isoformat()

    def _reset_latency():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            ResultsRepository(s).reset_session_latency(session_id)
    await asyncio.to_thread(_reset_latency)

    state._refresh_latency_task = asyncio.create_task(
        _run_refresh_latency_background(state, session_id, urls, task_id)
    )

    return {"task_id": task_id, "total": total, "status": "running"}


async def _run_refresh_latency_background(state, session_id, urls, task_id):
    """后台执行全量延迟检测，通过SSE推送进度"""
    import aiohttp, ssl, time

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
                        from iptv_check.infra.repository.results_repo import ResultsRepository
                        with state.event_store.get_session() as s:
                            repo = ResultsRepository(s)
                            for lat, url in batch:
                                repo.update_channel_result(session_id, url, lat, True, "valid")
                                repo.update_event_payload_latency(session_id, url, lat, True, "valid")
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
                    from iptv_check.infra.repository.results_repo import ResultsRepository
                    with state.event_store.get_session() as s:
                        repo = ResultsRepository(s)
                        for lat, url in batch:
                            repo.update_channel_result(session_id, url, lat, True, "valid")
                            repo.update_event_payload_latency(session_id, url, lat, True, "valid")
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


@router.get("/results/filtered-urls")
async def get_filtered_urls(
    session_id: str = "",
    tab: str = "all",
    media_type: str = "all",
    country: str = "",
    region: str = "",
    category: str = "",
    quality: str = "",
    protocol: str = "",
    source: str = "",
    search: str = "",
    latency_min: float = -1,
    latency_max: float = -1,
    speed_min: float = -1,
    speed_max: float = -1,
):
    """返回符合当前筛选条件的全部频道 URL（跨页全集），供前端跨页全选用。"""
    state = _get_state()
    sid = session_id or (state.event_store.current_session_id if state else "")
    if not sid or not state.read_model:
        return {"urls": [], "total": 0}
    urls = await asyncio.to_thread(
        state.read_model.fetch_filtered_urls,
        sid, tab, media_type, "", country, region, category,
        quality, protocol, source, latency_min, latency_max, speed_min, speed_max, search,
    )
    return {"urls": urls, "total": len(urls)}


@router.get("/results/sources")
async def get_available_sources():
    """返回当前 session 数据中出现过的来源源列表"""
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
        return await asyncio.to_thread(state.read_model.get_available_sources, session_id)
    except Exception as e:
        logger.error("获取来源列表失败: %s", e, exc_info=True)
        return []


@router.post("/results/thorough-check", status_code=202)
async def thorough_check(
    session_id: str = "",
    urls: str = "",
    tab: str = "all",
    media_type: str = "all",
    country: str = "",
    region: str = "",
    category: str = "",
    quality: str = "",
    protocol: str = "",
    source: str = "",
    search: str = "",
    latency_min: float = -1,
    latency_max: float = -1,
    speed_min: float = -1,
    speed_max: float = -1,
):
    """触发彻底版检测(GET+Range)。
    urls 为逗号分隔的 base64 编码 URL 列表；为空时按 tab/country 等筛选条件取子集，
    无任何筛选则取整个 session 全量。"""
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
            from iptv_check.infra.repository.results_repo import ResultsRepository
            with state.event_store.get_session() as s:
                return ResultsRepository(s).latest_session_id()
        session_id = await asyncio.to_thread(_latest_session)

    if not session_id:
        raise HTTPException(400, "没有检测结果可检测")

    def _has_data():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            return ResultsRepository(s).has_session_data(session_id)

    if not await asyncio.to_thread(_has_data):
        raise HTTPException(400, "该 session 没有物化数据，无法检测")

    def _fetch_urls():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            return ResultsRepository(s).fetch_session_urls(session_id)

    def _fetch_filtered_urls():
        if state.read_model:
            return state.read_model.fetch_filtered_urls(
                session_id, tab, media_type, "", country, region, category,
                quality, protocol, source, latency_min, latency_max, speed_min, speed_max, search,
            )
        return []

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
            urls = await asyncio.to_thread(_fetch_filtered_urls)
    else:
        urls = await asyncio.to_thread(_fetch_filtered_urls)
    total = len(urls)
    if total == 0:
        return {"total": 0, "checked": 0, "updated": 0}

    task_id = f"thorough_{int(time.time())}_{random.randint(1000, 9999)}"
    state._refresh_latency_task_id = task_id
    state._refresh_latency_progress = {"checked": 0, "total": total, "updated": 0}
    state._refresh_latency_started_at = datetime.datetime.now().isoformat()

    def _reset_latency():
        from iptv_check.infra.repository.results_repo import ResultsRepository
        with state.event_store.get_session() as s:
            ResultsRepository(s).reset_session_latency(session_id, urls or None)
    await asyncio.to_thread(_reset_latency)

    state._refresh_latency_task = asyncio.create_task(
        _run_thorough_check_background(state, session_id, urls, task_id)
    )

    return {"task_id": task_id, "total": total, "status": "running"}


async def _run_thorough_check_background(state, session_id, urls, task_id):
    """后台执行彻底版检测(GET+Range)，通过SSE推送进度"""
    import aiohttp, ssl, time as _time

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
                        from iptv_check.infra.repository.results_repo import ResultsRepository
                        with state.event_store.get_session() as s:
                            repo = ResultsRepository(s)
                            for lat, url in batch:
                                repo.update_channel_result(session_id, url, lat, True, "valid")
                                repo.update_event_payload_latency(session_id, url, lat, True, "valid")
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
                    from iptv_check.infra.repository.results_repo import ResultsRepository
                    with state.event_store.get_session() as s:
                        repo = ResultsRepository(s)
                        for lat, url in batch:
                            repo.update_channel_result(session_id, url, lat, True, "valid")
                            repo.update_event_payload_latency(session_id, url, lat, True, "valid")
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

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["channels"])


class UploadRequest(BaseModel):
    filename: str = "upload.m3u"
    content_base64: str = ""


def _get_state():
    from iptv_check.server.app import app_state
    return app_state


def _get_check_service():
    from iptv_check.server.app import app_state
    return app_state._check_service


@router.get("/results")
async def get_results(tab: str = "all", page: int = 1, per_page: int = 50, search: str = "",
                      group_path: str = "", view_mode: str = "grouped", sort: str = "best",
                      media_type: str = "all", language: str = ""):
    state = _get_state()
    service = _get_check_service()

    if service and service.session_id:
        if view_mode == "grouped":
            return state.read_model.get_grouped_channels(
                session_id=service.session_id,
                tab=tab, group_path=group_path, page=page, per_page=per_page,
                search=search, sort=sort, media_type=media_type, language=language,
            )
        return state.read_model.get_checked_channels(
            session_id=service.session_id,
            tab=tab, page=page, per_page=per_page, search=search,
            media_type=media_type, language=language,
        )

    if not state.is_checking and state.database:
        try:
            return state.database.query_results_paginated(tab=tab, page=page, per_page=per_page, search=search)
        except Exception:
            pass

    return {"total": 0, "page": page, "per_page": per_page, "items": []}


@router.get("/results/category-tree")
async def get_category_tree(media_type: str = "all"):
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        return []
    return state.read_model.get_category_tree(session_id=service.session_id, media_type=media_type)


@router.get("/results/languages")
async def get_available_languages():
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        return []
    return state.read_model.get_available_languages(service.session_id)


@router.get("/results/source-health")
async def get_source_health():
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        return []
    return state.read_model.get_source_download_stats(service.session_id)


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
            "invalid": progress["invalid"],
            "is_running": progress["is_running"],
        }
    db_stats = state.database.get_stats()
    return {
        "total": 0, "checked": 0, "valid": 0, "invalid": 0,
        "is_running": False, "db_stats": db_stats,
    }


@router.get("/results/history")
async def get_check_history(limit: int = 20):
    state = _get_state()
    return {"history": state.database.get_check_history(limit)}


@router.post("/results/save")
async def save_results_to_db():
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        raise HTTPException(400, "没有检测结果可保存")
    results_data = state.read_model.get_checked_results_raw(service.session_id)
    if not results_data:
        raise HTTPException(400, "没有检测结果可保存")
    history_id = state.database.save_check_result(results_data)
    return {"history_id": history_id, "saved": len(results_data)}


@router.get("/favorites")
async def get_favorites():
    state = _get_state()
    from iptv_check.infra.database import FavoriteModel
    with state.database.get_session() as session:
        items = session.exec(select(FavoriteModel).order_by(FavoriteModel.created_at.desc())).all()
        return {
            "favorites": [
                {"id": f.id, "channel_id": f.channel_id, "name": f.name, "url": f.url, "created_at": f.created_at.isoformat()}
                for f in items
            ]
        }


@router.post("/favorites")
async def add_favorite(req: dict):
    state = _get_state()
    from iptv_check.infra.database import FavoriteModel, ChannelModel
    with state.database.get_session() as session:
        channel = session.exec(select(ChannelModel).where(ChannelModel.url == req.get("url", ""))).first()
        if not channel:
            raise HTTPException(404, "频道不存在")
        existing = session.exec(select(FavoriteModel).where(FavoriteModel.channel_id == channel.id)).first()
        if existing:
            return {"message": "已在收藏夹中"}
        fav = FavoriteModel(channel_id=channel.id, name=channel.name, url=channel.url)
        session.add(fav)
        session.commit()
        return {"id": fav.id}


@router.delete("/favorites/{fav_id}")
async def remove_favorite(fav_id: int):
    state = _get_state()
    from iptv_check.infra.database import FavoriteModel
    with state.database.get_session() as session:
        fav = session.get(FavoriteModel, fav_id)
        if fav:
            session.delete(fav)
            session.commit()
            return {"deleted": True}
        raise HTTPException(404, "收藏不存在")


@router.get("/report")
async def get_quality_report():
    state = _get_state()
    service = _get_check_service()
    results_data = []
    if service and service.session_id:
        results_data = state.read_model.get_checked_results_raw(service.session_id)

    if not results_data:
        return {"error": "没有检测结果"}

    from iptv_check.models.check_result import CheckResult
    from iptv_check.models.channel import Channel
    results = []
    for rd in results_data:
        ch = Channel(name=rd["channel"]["name"], url=rd["channel"]["url"], group=rd["channel"].get("group", ""), sources=rd["channel"].get("sources", []))
        r = CheckResult(channel=ch, is_valid=rd["is_valid"], latency=rd["latency"], speed=rd["speed"], details=rd["details"])
        results.append(r)

    valid = [r for r in results if r.is_valid]
    invalid = [r for r in results if not r.is_valid]
    latencies = [r.latency for r in valid if r.latency > 0]

    latency_ranges = {"<50ms": 0, "50-100ms": 0, "100-200ms": 0, "200-500ms": 0, "500ms+": 0}
    for l in latencies:
        if l < 50: latency_ranges["<50ms"] += 1
        elif l < 100: latency_ranges["50-100ms"] += 1
        elif l < 200: latency_ranges["100-200ms"] += 1
        elif l < 500: latency_ranges["200-500ms"] += 1
        else: latency_ranges["500ms+"] += 1

    source_stats = {}
    for r in results:
        for src in r.channel.sources:
            if src not in source_stats:
                source_stats[src] = {"total": 0, "valid": 0, "latencies": []}
            source_stats[src]["total"] += 1
            if r.is_valid:
                source_stats[src]["valid"] += 1
                if r.latency > 0:
                    source_stats[src]["latencies"].append(r.latency)

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
        "total": len(results), "valid": len(valid), "invalid": len(invalid),
        "valid_rate": round(len(valid) / len(results) * 100, 1) if results else 0,
        "avg_latency": round(sum(latencies) / len(latencies), 0) if latencies else 0,
        "min_latency": min(latencies) if latencies else 0,
        "max_latency": max(latencies) if latencies else 0,
        "latency_distribution": latency_ranges,
        "source_ranking": source_ranking,
        "group_stats": _compute_group_stats(results),
    }


@router.get("/trends/channel/{channel_id}")
async def get_channel_trend(channel_id: int, days: int = 7):
    state = _get_state()
    trend = state.database.get_channel_trend(channel_id, days)
    stability = state.database.get_channel_stability_stats(channel_id, days)
    return {"trend": trend, "stability": stability, "days": days}


@router.get("/trends/stable-channels")
async def get_top_stable_channels(days: int = 7, limit: int = 50):
    state = _get_state()
    return {"channels": state.database.get_top_stable_channels(days, limit)}


@router.get("/trends/history-compare")
async def compare_history(h1: int, h2: int):
    state = _get_state()
    return state.database.get_history_comparison(h1, h2)


@router.get("/recommend")
async def get_recommendations(max_per_group: int = 3, prefer_low_latency: bool = True):
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        return {"error": "没有检测结果"}

    results_data = state.read_model.get_checked_results_raw(service.session_id)
    if not results_data:
        return {"error": "没有检测结果"}

    from iptv_check.models.check_result import CheckResult
    from iptv_check.models.channel import Channel
    check_results = []
    for rd in results_data:
        ch = Channel(name=rd["channel"]["name"], url=rd["channel"]["url"], group=rd["channel"].get("group", ""), sources=rd["channel"].get("sources", []))
        r = CheckResult(channel=ch, is_valid=rd["is_valid"], latency=rd["latency"], speed=rd["speed"], details=rd["details"])
        check_results.append(r)

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


@router.get("/recommend/m3u")
async def get_recommend_m3u(max_per_group: int = 3):
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        raise HTTPException(400, "没有检测结果")

    results_data = state.read_model.get_checked_results_raw(service.session_id)
    if not results_data:
        raise HTTPException(400, "没有检测结果")

    from iptv_check.models.check_result import CheckResult
    from iptv_check.models.channel import Channel
    check_results = []
    for rd in results_data:
        ch = Channel(name=rd["channel"]["name"], url=rd["channel"]["url"], group=rd["channel"].get("group", ""), sources=rd["channel"].get("sources", []))
        r = CheckResult(channel=ch, is_valid=rd["is_valid"], latency=rd["latency"], speed=rd["speed"], details=rd["details"])
        check_results.append(r)

    from iptv_check.core.recommender import SourceRecommender
    from fastapi.responses import Response
    recs = SourceRecommender.recommend(check_results, local_isp=state.local_isp, max_channels_per_group=max_per_group)
    m3u_content = SourceRecommender.generate_m3u(recs, local_isp=state.local_isp)
    return Response(content=m3u_content, media_type="audio/x-mpegurl", headers={"Content-Disposition": "attachment; filename=recommended.m3u"})


@router.get("/recommend/isp")
async def get_isp_recommendations(target_isp: str = None):
    state = _get_state()
    service = _get_check_service()
    if not service or not service.session_id:
        return {"error": "没有检测结果"}

    results_data = state.read_model.get_checked_results_raw(service.session_id)
    if not results_data:
        return {"error": "没有检测结果"}

    from iptv_check.models.check_result import CheckResult
    from iptv_check.models.channel import Channel
    check_results = []
    for rd in results_data:
        ch = Channel(name=rd["channel"]["name"], url=rd["channel"]["url"], group=rd["channel"].get("group", ""), sources=rd["channel"].get("sources", []))
        r = CheckResult(channel=ch, is_valid=rd["is_valid"], latency=rd["latency"], speed=rd["speed"], details=rd["details"])
        check_results.append(r)

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

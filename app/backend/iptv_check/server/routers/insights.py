"""质量报告 / 趋势分析 / 智能推荐 路由。"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Response

from iptv_check.server.routers._common import get_state, get_check_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/report")
async def get_quality_report():
    import traceback
    try:
        state = get_state()
        if not state:
            return {"error": "服务未初始化"}

        service = get_check_service()
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
    state = get_state()
    trend = await asyncio.to_thread(state.database.get_channel_trend, channel_id, days)
    stability = await asyncio.to_thread(state.database.get_channel_stability_stats, channel_id, days)
    return {"trend": trend, "stability": stability, "days": days}


@router.get("/trends/stable-channels")
async def get_top_stable_channels(days: int = 7, limit: int = 50):
    state = get_state()
    return {"channels": await asyncio.to_thread(state.database.get_top_stable_channels, days, limit)}


@router.get("/trends/history-compare")
async def compare_history(h1: int = 0, h2: int = 0):
    state = get_state()
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
        state = get_state()
        service = get_check_service()
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
        state = get_state()
        service = get_check_service()
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
        state = get_state()
        service = get_check_service()
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

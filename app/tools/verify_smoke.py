#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后端冒烟验收脚本（可重复运行）。

验证关键 API 端到端可用与数据结构正确性。
用法：
    python app/tools/verify_smoke.py          # 完整验收
    python app/tools/verify_smoke.py --quick  # 仅核心 API
退出码：0=全部通过，1=存在失败项
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

FAILURES = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}{' ' + detail if detail else ''}")
    if not cond:
        FAILURES.append(name)


def main():
    quick = "--quick" in sys.argv
    from fastapi.testclient import TestClient
    from iptv_check.server.app import create_app

    app = create_app()
    with TestClient(app) as c:
        # --- 核心状态 ---
        r = c.get("/api/check/state")
        check("check/state", r.status_code == 200)
        r = c.get("/api/results/stats")
        check("results/stats", r.status_code == 200)
        r = c.get("/healthz")
        check("healthz", r.status_code == 200)

        # --- 结果平铺视图（flat）---
        r = c.get("/api/results?per_page=2&view_mode=flat")
        data = r.json() if r.status_code == 200 else {}
        items = data.get("items") or []
        check("results flat: 200+items", r.status_code == 200 and len(items) > 0,
              f"(total={data.get('total')})")
        if items:
            check("results flat: has url", bool(items[0].get("url")), items[0].get("name", ""))

        # --- 结果聚合视图（grouped）---
        r = c.get("/api/results?per_page=2&view_mode=grouped")
        data = r.json() if r.status_code == 200 else {}
        items = data.get("items") or []
        check("results grouped: 200+items", r.status_code == 200 and len(items) > 0,
              f"(total={data.get('total')})")
        if items:
            first = items[0]
            check("results grouped: has sources", "sources" in first,
                  f"(sources={len(first.get('sources') or [])})")
            check("results grouped: has recommended_source_idx",
                  "recommended_source_idx" in first)

        if quick:
            return _finish()

        # --- 收藏 ---
        r = c.get("/api/favorites")
        check("favorites", r.status_code == 200)
        r = c.get("/api/favorite-folders")
        check("favorite-folders", r.status_code == 200)
        r = c.get("/api/custom-channels")
        check("custom-channels", r.status_code == 200)

        # --- 分析类 ---
        r = c.get("/api/report")
        check("report", r.status_code == 200)
        r = c.get("/api/trends/stable-channels")
        check("trends/stable-channels", r.status_code == 200)
        r = c.get("/api/trends/history-compare")
        check("trends/history-compare", r.status_code == 200)
        r = c.get("/api/recommend")
        check("recommend", r.status_code == 200)

        # --- 直播/导出 ---
        r = c.get("/api/live-channels")
        check("live-channels", r.status_code == 200)
        r = c.get("/api/favorites/m3u")
        check("favorites/m3u", r.status_code == 200)

        # --- 刷新端点不触发任务的安全分支 ---
        r = c.post("/api/results/refresh-latency", params={"session_id": "no_such_session_abc"})
        check("refresh-latency: 400 on bad session", r.status_code == 400)
        r = c.post("/api/results/thorough-check", params={"session_id": "no_such_session_abc"})
        check("thorough-check: 400 on bad session", r.status_code == 400)

        # --- 细筛检测入口的安全分支（不触发真实检测任务） ---
        r = c.post("/api/check/detail", json={"source_session_id": ""})
        check("check/detail: 400 on empty session", r.status_code == 400)
        r = c.post("/api/check/detail", json={"source_session_id": "no_such_session_abc", "check_mode": "deep"})
        check("check/detail: 400 on bad session", r.status_code == 400)

        # --- 历史记录含细筛字段（check_mode / parent_session_id） ---
        r = c.get("/api/results/history")
        hist = r.json() if r.status_code == 200 else []
        if hist:
            check("results/history: has check_mode", "check_mode" in hist[0])
            check("results/history: has parent_session_id", "parent_session_id" in hist[0])
        else:
            check("results/history: has check_mode", True, "(空历史，跳过)")

    return _finish()


def _finish():
    print("=" * 44)
    if FAILURES:
        print(f"FAIL: {len(FAILURES)} 项未通过 -> {FAILURES}")
        return 1
    print("ALL SMOKE TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())

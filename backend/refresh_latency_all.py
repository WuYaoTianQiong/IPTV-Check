"""
全量刷新检测结果中的延迟数据
直接操作 events.db，不需要重启后端服务

用法: python backend/refresh_latency_all.py
"""
import asyncio
import aiohttp
import sqlite3
import time
import ssl
import os
import sys
import logging
logging.getLogger('asyncio').setLevel(logging.CRITICAL)

DB_PATH = os.path.join(os.path.dirname(__file__), "iptv_check", "data", "events.db")


def get_urls():
    """查出最新 session 的所有 URL"""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT session_id FROM channel_results GROUP BY session_id ORDER BY MAX(created_at) DESC LIMIT 1"
    ).fetchone()
    if not row:
        print("❌ 没有找到检测数据")
        sys.exit(1)
    sid = row[0]
    rows = conn.execute(
        "SELECT DISTINCT url FROM channel_results WHERE session_id = ? AND url != ''",
        (sid,),
    ).fetchall()
    conn.close()
    print(f"📡 当前 session: {sid}")
    print(f"📊 共 {len(rows)} 个 URL")
    return sid, [r[0] for r in rows]


def write_back(session_id, updates):
    """批量写回延迟数据"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("BEGIN")
    for lat, url in updates:
        conn.execute(
            "UPDATE channel_results SET latency = ? WHERE session_id = ? AND url = ?",
            (lat, session_id, url),
        )
    conn.commit()
    conn.close()


async def main():
    session_id, urls = get_urls()
    total = len(urls)

    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    # 关键参数：IPv4 only + 用完即关 + 200 并发 + 300ms 超时择优
    connector = aiohttp.TCPConnector(
        limit=200, force_close=True, family=2, ttl_dns_cache=300
    )
    timeout = aiohttp.ClientTimeout(total=0.5, connect=0.3)

    checked = 0
    updated = 0
    ok_urls = []
    start_ts = time.time()

    sem = asyncio.Semaphore(200)

    async def probe(url):
        try:
            t0 = time.time()
            async with session.head(url, ssl=False) as r:
                ms = int((time.time() - t0) * 1000)
                return (url, ms, r.status < 400)
        except Exception:
            return (url, -1, False)

    async def bounded_probe(url):
        async with sem:
            return await probe(url)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [bounded_probe(u) for u in urls]
        for coro in asyncio.as_completed(tasks):
            try:
                url, lat, ok = await coro
            except Exception:
                continue
            checked += 1
            if ok and lat > 0:
                ok_urls.append((lat, url))
                updated += 1

            if len(ok_urls) >= 500:
                write_back(session_id, ok_urls)
                ok_urls.clear()

            if checked % 1000 == 0:
                pct = checked / total * 100
                elapsed = time.time() - start_ts
                print(
                    f"  ⏳ {checked}/{total} ({pct:.1f}%) | "
                    f"已更新 {updated} | 耗时 {elapsed:.0f}s",
                    flush=True,
                )

        if ok_urls:
            write_back(session_id, ok_urls)

    elapsed = time.time() - start_ts
    print(f"\n✅ 完成！检测 {checked} 个，更新 {updated} 个，耗时 {elapsed:.0f} 秒")


if __name__ == "__main__":
    asyncio.run(main())

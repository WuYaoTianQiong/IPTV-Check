import socket
import os
import json
import asyncio
import logging
from typing import Optional

import aiohttp

from iptv_check.infra.config.settings import ISP_KEYWORDS, ISP_APIS, IP_PREFIXES
from iptv_check.infra.network import HttpClient
from iptv_check.infra.event_bus import event_bus, Events

logger = logging.getLogger(__name__)


class ISPDetector:
    def __init__(self, http_client: HttpClient):
        self._http = http_client

    async def detect_local_isp_async(self) -> str:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
        detected_isp = None

        async def _try_api(api_config):
            api_url = api_config["url"]
            fields = api_config.get("fields", ["isp", "org", "company"])
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5), ssl=False) as resp:
                        if resp.status != 200:
                            return None
                        content_type = resp.headers.get("Content-Type", "").lower()
                        if "json" in content_type:
                            data = await resp.json(content_type=None)
                        elif "xml" in content_type or "text" in content_type:
                            text = await resp.text()
                            try:
                                data = json.loads(text.split("(", 1)[-1].rsplit(")", 1)[0])
                            except Exception:
                                try:
                                    data = json.loads(text)
                                except Exception:
                                    return None
                        else:
                            return None

                        isp_text_parts = [str(data.get(f, "")).lower() for f in fields if data.get(f)]
                        isp_text = " ".join(isp_text_parts)
                        if not isp_text:
                            isp_text = str(data).lower()[:500]

                        for isp_name, keywords in ISP_KEYWORDS.items():
                            if any(kw.lower() in isp_text for kw in keywords):
                                return isp_name
                        return None
            except Exception as e:
                logger.debug("API %s 失败: %s", api_url, e)
                return None

        sorted_apis = sorted(ISP_APIS, key=lambda x: x.get("priority", 99))
        results = await asyncio.gather(*[_try_api(api) for api in sorted_apis], return_exceptions=True)

        for r in results:
            if isinstance(r, str):
                detected_isp = r
                break

        if not detected_isp:
            detected_isp = await self._detect_by_ip_segment_async()

        result = detected_isp or "其他/未知"
        event_bus.emit(Events.ISP_DETECTED, isp=result)
        return result

    async def _detect_by_ip_segment_async(self) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://api.myip.com", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ip = data.get("ip", "")
                        if ip:
                            return self._match_ip_to_isp(ip)
        except Exception as e:
            logger.debug("IP段检测API失败: %s", e)

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip:
                return self._match_ip_to_isp(local_ip)
        except Exception as e:
            logger.debug("本地IP检测失败: %s", e)

        return None

    def detect_local_isp(self) -> str:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json"}
        detected_isp = None

        for api_config in ISP_APIS:
            api_url = api_config["url"]
            fields = api_config.get("fields", ["isp", "org", "company"])
            try:
                resp = self._http.get_unsafe(api_url, headers=headers, timeout=(5, 5))
                if resp.status_code != 200:
                    continue

                content_type = resp.headers.get("Content-Type", "").lower()
                if "json" in content_type:
                    data = resp.json()
                elif "xml" in content_type or "text" in content_type:
                    try:
                        data = json.loads(resp.text.split("(", 1)[-1].rsplit(")", 1)[0])
                    except Exception:
                        try:
                            data = json.loads(resp.text)
                        except Exception:
                            continue
                else:
                    continue

                isp_text_parts = [str(data.get(f, "")).lower() for f in fields if data.get(f)]
                isp_text = " ".join(isp_text_parts)

                if not isp_text:
                    isp_text = str(data).lower()[:500]

                logger.debug("API %s 返回: %s", api_url, isp_text[:100])

                for isp_name, keywords in ISP_KEYWORDS.items():
                    if any(kw.lower() in isp_text for kw in keywords):
                        detected_isp = isp_name
                        break

                if detected_isp:
                    break

            except Exception as e:
                logger.debug("API %s 失败: %s", api_url, e)
                continue

        if not detected_isp:
            detected_isp = self._detect_by_ip_segment()

        result = detected_isp or "其他/未知"
        event_bus.emit(Events.ISP_DETECTED, isp=result)
        return result

    def _detect_by_ip_segment(self) -> Optional[str]:
        try:
            resp = self._http.get_with_retry("https://api.myip.com", timeout=5)
            if resp.status_code == 200:
                ip = resp.json().get("ip", "")
                if ip:
                    return self._match_ip_to_isp(ip)
        except Exception as e:
            logger.debug("IP段检测API失败: %s", e)

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            if local_ip:
                return self._match_ip_to_isp(local_ip)
        except Exception as e:
            logger.debug("本地IP检测失败: %s", e)

        return None

    @staticmethod
    def _match_ip_to_isp(ip: str) -> Optional[str]:
        parts = ip.split(".")
        if len(parts) < 2:
            return None
        prefix = f"{parts[0]}.{parts[1]}"
        for isp_name, prefixes in IP_PREFIXES.items():
            if prefix in prefixes:
                logger.info("通过IP段 %s 检测到运营商: %s", prefix, isp_name)
                return isp_name
        return None

    @staticmethod
    def detect_source_isp(file_paths: list, links: list, local_isp: str) -> set:
        source_isp = set()
        for path in file_paths:
            fname = os.path.basename(path).lower()
            for isp_name, keywords in ISP_KEYWORDS.items():
                if any(kw in fname for kw in keywords):
                    source_isp.add(isp_name)
                    break
        for link in links:
            url = link.url.lower() if hasattr(link, 'url') else link.get("url", "").lower()
            for isp_name, keywords in ISP_KEYWORDS.items():
                if any(kw in url for kw in keywords):
                    source_isp.add(isp_name)
                    break
        return source_isp

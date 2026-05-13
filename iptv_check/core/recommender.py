"""
智能源推荐引擎
基于 ISP、历史检测表现、延迟等维度为用户推荐最优直播源组合
"""
import logging
from typing import List, Dict, Optional
from iptv_check.models.channel import Channel
from iptv_check.models.check_result import CheckResult

logger = logging.getLogger(__name__)


class SourceRecommender:
    """智能源推荐引擎"""

    @staticmethod
    def recommend(
        results: List[CheckResult],
        local_isp: str = "未知",
        max_channels_per_group: int = 3,
        prefer_low_latency: bool = True,
    ) -> Dict[str, List[Dict]]:
        """
        为用户推荐最优源组合

        Args:
            results: 检测结果列表
            local_isp: 本地运营商标识
            max_channels_per_group: 每个分组最多推荐几个频道（备用源数量）
            prefer_low_latency: 是否优先低延迟

        Returns:
            按分组组织的推荐频道列表
        """
        if not results:
            return {}

        # 1. 按频道名称分组
        groups: Dict[str, List[CheckResult]] = {}
        for r in results:
            if not r.is_valid:
                continue
            name = r.channel.name
            if name not in groups:
                groups[name] = []
            groups[name].append(r)

        # 2. 为每个频道选择最优源
        recommendations: Dict[str, List[Dict]] = {}
        for name, variants in groups.items():
            scored = [SourceRecommender._score_result(r, local_isp, prefer_low_latency) for r in variants]
            scored.sort(key=lambda x: x["score"], reverse=True)
            recommendations[name] = scored[:max_channels_per_group]

        return recommendations

    @staticmethod
    def _score_result(result: CheckResult, local_isp: str, prefer_low_latency: bool) -> Dict:
        """为检测结果打分"""
        score = 0.0
        reasons = []

        # 基础分：有效性
        if result.is_valid:
            score += 50
        else:
            return {"channel": result.channel, "result": result, "score": 0, "reasons": ["无效"]}

        # 延迟分（0-30分）
        if result.latency > 0:
            if result.latency < 50:
                score += 30
                reasons.append("低延迟")
            elif result.latency < 100:
                score += 25
                reasons.append("中等延迟")
            elif result.latency < 200:
                score += 15
            elif result.latency < 500:
                score += 5
            else:
                score += 0
        else:
            score += 10  # 未知延迟，给基础分

        # 速度分（0-20分）
        try:
            speed = float(result.speed) if result.speed and result.speed not in ("-", "N/A", "∞") else 0
            if speed > 1000:
                score += 20
                reasons.append("高速")
            elif speed > 500:
                score += 15
            elif speed > 200:
                score += 10
            elif speed > 100:
                score += 5
        except (ValueError, TypeError):
            score += 5  # 未知速度，给基础分

        # ISP 匹配分（0-10分）
        for source in result.channel.sources:
            source_lower = source.lower()
            if local_isp != "未知":
                isp_lower = local_isp.lower()
                if isp_lower in source_lower or (
                    ("电信" in isp_lower and "telecom" in source_lower)
                    or ("联通" in isp_lower and "unicom" in source_lower)
                    or ("移动" in isp_lower and "mobile" in source_lower)
                ):
                    score += 10
                    reasons.append(f"ISP匹配({source})")
                    break

        # 源数量加分（0-5分）
        if len(result.channel.sources) >= 3:
            score += 5
            reasons.append("多源")
        elif len(result.channel.sources) >= 2:
            score += 3

        # 标签加分
        if result.tag == "optimized":
            score += 5
            reasons.append("已优选")

        return {
            "channel": result.channel,
            "result": result,
            "score": round(score, 1),
            "reasons": reasons,
        }

    @staticmethod
    def generate_m3u(recommendations: Dict[str, List[Dict]], local_isp: str = "未知") -> str:
        """生成推荐结果的 M3U 内容"""
        lines = ["#EXTM3U"]
        for name, variants in recommendations.items():
            for v in variants:
                ch = v["channel"]
                r = v["result"]
                group = ch.group or "推荐"
                reason_str = ",".join(v["reasons"])
                lines.append(
                    f'#EXTINF:-1 group-title="{group}" tvg-name="{name}" '
                    f'tvg-logo="" comment="推荐得分:{v["score"]} ({reason_str})",'
                    f"{name}"
                )
                lines.append(r.channel.url)
        return "\n".join(lines)

    @staticmethod
    def recommend_for_isp(results: List[CheckResult], target_isp: str) -> List[CheckResult]:
        """为特定 ISP 推荐可用的最佳频道"""
        valid = [r for r in results if r.is_valid]
        isp_matched = []
        others = []

        for r in valid:
            matched = False
            for source in r.channel.sources:
                if target_isp.lower() in source.lower():
                    isp_matched.append(r)
                    matched = True
                    break
            if not matched:
                others.append(r)

        # ISP 匹配的排前面，按延迟排序
        isp_matched.sort(key=lambda r: r.latency if r.latency > 0 else 9999)
        others.sort(key=lambda r: r.latency if r.latency > 0 else 9999)

        return isp_matched + others

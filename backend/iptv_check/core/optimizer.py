import re
import logging
from typing import List, Dict

from iptv_check.models.check_result import CheckResult
from iptv_check.core.recommender import SourceRecommender

logger = logging.getLogger(__name__)


class SmartOptimizer:
    """智能优选：按频道名+分辨率分组，每组保留质量最优的N个链接"""

    @staticmethod
    def optimize(
        results: List[CheckResult],
        local_isp: str = "未知",
        max_per_group: int = 3,
    ) -> List[CheckResult]:
        valid_results = [r for r in results if r.is_valid]
        if not valid_results:
            return results

        groups: Dict[str, List[CheckResult]] = {}
        for r in valid_results:
            name = r.channel.name
            resolution = getattr(r.channel, "resolution", "") or ""
            group_key = f"{name}@{resolution}" if resolution else name
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(r)

        optimized: List[CheckResult] = []
        for group_key, group_results in groups.items():
            scored = [SourceRecommender._score_result(r, local_isp, True) for r in group_results]
            scored.sort(key=lambda x: x["score"], reverse=True)
            for s in scored[:max_per_group]:
                optimized.append(s["result"])

        invalid_results = [r for r in results if not r.is_valid]
        return optimized + invalid_results

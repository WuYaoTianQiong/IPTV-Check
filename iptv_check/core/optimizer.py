import re
import logging
from typing import List

from iptv_check.models.check_result import CheckResult

logger = logging.getLogger(__name__)


class SmartOptimizer:
    @staticmethod
    def optimize(results: List[CheckResult]) -> List[CheckResult]:
        valid_results = [r for r in results if r.is_valid]
        if not valid_results:
            return results

        channel_groups: dict = {}
        for r in valid_results:
            name_key = re.sub(r'[\s\-_|]', '', r.channel.name).lower()
            if name_key not in channel_groups:
                channel_groups[name_key] = []
            channel_groups[name_key].append(r)

        optimized: List[CheckResult] = []
        for name_key, group_results in channel_groups.items():
            if len(group_results) == 1:
                optimized.append(group_results[0])
            else:
                best = min(group_results, key=lambda r: r.latency if r.latency >= 0 else float('inf'))
                optimized.append(best)

        invalid_results = [r for r in results if not r.is_valid]
        return optimized + invalid_results

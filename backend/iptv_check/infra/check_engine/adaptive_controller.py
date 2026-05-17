"""
自适应并发控制器
基于检测超时率动态调整并发度，解决高并发导致的级联超时问题
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveConcurrencyController:
    """
    自适应并发控制器

    工作原理：
    1. 每 sample_window_size 个检测结果作为一个采样窗口
    2. 窗口满时计算超时率，决策降级或恢复
    3. 超时率 > high_timeout_threshold：并发度减半（不低于 min_threads）
    4. 连续 recovery_streak_required 个窗口超时率 < low_timeout_threshold：恢复至 max_threads 的75%
    5. 首个窗口禁止降级，复检阶段豁免降级
    """
    max_threads: int
    min_threads: int = 5
    sample_window_size: int = 50
    high_timeout_threshold: float = 0.30
    low_timeout_threshold: float = 0.15
    recovery_streak_required: int = 3

    _current_threads: int = 0
    _checked_in_window: int = 0
    _timeouts_in_window: int = 0
    _total_windows: int = 0
    _low_timeout_streak: int = 0
    _is_recheck: bool = False

    def __post_init__(self):
        self._current_threads = self.max_threads

    @property
    def current_threads(self) -> int:
        return self._current_threads

    def report_result(self, is_timeout: bool) -> Optional[int]:
        """报告单个检测结果，返回调整后的并发度或None(未调整)"""
        self._checked_in_window += 1
        if is_timeout:
            self._timeouts_in_window += 1

        if self._checked_in_window < self.sample_window_size:
            return None

        timeout_rate = self._timeouts_in_window / self._checked_in_window
        self._total_windows += 1
        adjustment = self._evaluate(timeout_rate)

        self._checked_in_window = 0
        self._timeouts_in_window = 0
        return adjustment

    def _evaluate(self, timeout_rate: float) -> Optional[int]:
        old_threads = self._current_threads

        if self._is_recheck:
            return None

        if timeout_rate > self.high_timeout_threshold and self._total_windows > 1:
            new_threads = max(self.min_threads, self._current_threads // 2)
            self._low_timeout_streak = 0
            self._current_threads = new_threads
            if new_threads != old_threads:
                logger.info(
                    "[自适应并发] 降级: %d→%d, 超时率=%.1f%%, 原因=超时率超过%.0f%%",
                    old_threads, new_threads, timeout_rate * 100, self.high_timeout_threshold * 100,
                )
                return new_threads
        elif timeout_rate < self.low_timeout_threshold:
            self._low_timeout_streak += 1
            if self._low_timeout_streak >= self.recovery_streak_required:
                new_threads = min(self.max_threads, int(self.max_threads * 0.75))
                self._current_threads = new_threads
                self._low_timeout_streak = 0
                if new_threads != old_threads:
                    logger.info(
                        "[自适应并发] 恢复: %d→%d, 连续%d窗口超时率<%.0f%%",
                        old_threads, new_threads, self.recovery_streak_required,
                        self.low_timeout_threshold * 100,
                    )
                    return new_threads
        else:
            self._low_timeout_streak = 0

        return None

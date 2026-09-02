"""AdaptiveConcurrencyController 单元测试。

此前该核心并发控制逻辑无任何测试覆盖。测试覆盖：
窗口计数、首窗口基线豁免、降级/最低并发下限、连续低故障恢复、中间态重置、复检豁免。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from iptv_check.infra.check_engine.adaptive_controller import AdaptiveConcurrencyController


class TestAdaptiveConcurrencyController:
    def make(self, **kw):
        defaults = dict(max_threads=100, min_threads=5, sample_window_size=10)
        defaults.update(kw)
        return AdaptiveConcurrencyController(**defaults)

    def test_initial_threads(self):
        c = self.make()
        assert c.current_threads == 100

    def test_window_not_full_no_adjust(self):
        c = self.make()
        for _ in range(9):
            assert c.report_result(False) is None
        assert c.current_threads == 100

    def test_first_window_is_baseline_no_degrade(self):
        """首个窗口为基线，即使 100% 故障也不降级。"""
        c = self.make()
        for _ in range(10):
            c.report_result(True)
        assert c.current_threads == 100

    def test_high_failure_degrades_after_first_window(self):
        c = self.make()
        # 首个窗口（基线）
        for _ in range(10):
            c.report_result(True)
        # 第二窗口仍高故障 → 并发度减半
        for _ in range(10):
            c.report_result(True)
        assert c.current_threads == 50

    def test_degrade_never_below_min(self):
        c = self.make(max_threads=12, min_threads=5, sample_window_size=4)
        for _ in range(4):
            c.report_result(True)  # 窗口1 基线
        for _ in range(4):
            c.report_result(True)  # 窗口2 → 12//2=6
        assert c.current_threads == 6
        for _ in range(4):
            c.report_result(True)  # 窗口3 → 6//2=3，受 min=5 保护
        assert c.current_threads == 5

    def test_recovery_after_streak(self):
        c = self.make(max_threads=100, sample_window_size=5, recovery_streak_required=3)
        for _ in range(5):
            c.report_result(True)  # 窗口1 基线
        for _ in range(5):
            c.report_result(True)  # 窗口2 → 降级 50
        assert c.current_threads == 50
        for _ in range(3):
            for _ in range(5):
                c.report_result(False)
            c.report_result(False)  # 每窗口第 5 次触发评估（窗口满）
        assert c.current_threads == 75

    def test_middle_rate_resets_streak(self):
        """故障率落在 (low, high] 之间时重置恢复 streak。"""
        c = self.make(max_threads=100, sample_window_size=5, recovery_streak_required=2)
        for _ in range(5):
            c.report_result(True)
        for _ in range(5):
            c.report_result(True)  # 降级 50
        assert c.current_threads == 50
        # 1 个低故障窗口（streak=1，不足 2）
        for _ in range(5):
            c.report_result(False)
        c.report_result(False)
        # 中间态窗口：5 个结果 1 个失败 → 0.2，位于 (0.15, 0.30]，重置 streak
        for i in range(5):
            c.report_result(i == 0)
        assert c.report_result(False) is None
        # 再一个低故障窗口（streak 重新从 1 计，仍不足 2）
        for _ in range(5):
            c.report_result(False)
        assert c.report_result(False) is None
        assert c.current_threads == 50

    def test_recheck_exempt(self):
        c = self.make(sample_window_size=5)
        c._is_recheck = True
        for _ in range(5):
            c.report_result(True)
        assert c.report_result(True) is None
        assert c.current_threads == 100  # 复检豁免，不降级

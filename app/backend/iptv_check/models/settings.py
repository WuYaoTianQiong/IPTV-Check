from dataclasses import dataclass
from enum import Enum


class CheckMode(str, Enum):
    """检测方案三档

    - QUICK（方案1·快速）：只确认 HTTP 可达性 + 延迟，不拉流验证
    - STANDARD（方案1+2·推荐）：可达性 + 首包流验证（m3u8 校验分片可达）
    - DEEP（方案1+2+测速·深度）：在 STANDARD 基础上叠加真实下载测速
    """
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class CheckConfig:
    timeout_connect: int = 8
    timeout_read: int = 15
    max_threads: int = 120
    min_threads: int = 5
    check_mode: CheckMode = CheckMode.STANDARD
    # 兼容旧开关：True 时等效于 DEEP，False 不影响 check_mode 判断
    run_speed_test: bool = False
    use_cache: bool = True
    max_latency_ms: int = 15000
    enable_recheck: bool = False

    @property
    def timeout_tuple(self) -> tuple:
        return (self.timeout_connect, self.timeout_read)

    @property
    def effective_mode(self) -> CheckMode:
        """实际生效的检测方案（兼容旧的 run_speed_test 布尔开关）"""
        if self.run_speed_test and self.check_mode != CheckMode.QUICK:
            return CheckMode.DEEP
        if self.check_mode not in (CheckMode.QUICK, CheckMode.STANDARD, CheckMode.DEEP):
            return CheckMode.STANDARD
        return self.check_mode


@dataclass
class ExportConfig:
    export_m3u: bool = True
    export_txt: bool = True
    export_csv: bool = True
    export_xlsx: bool = True
    export_mode: str = "merged"
    ipv_split: bool = False

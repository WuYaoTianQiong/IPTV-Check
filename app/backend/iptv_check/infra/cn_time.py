from datetime import datetime, timezone, timedelta, tzinfo
from zoneinfo import ZoneInfo

try:
    # Windows 无系统 tzdata，依赖 tzdata 包；缺失时回退东八区固定偏移
    _CN_TZ: tzinfo = ZoneInfo("Asia/Shanghai")
except Exception:
    # 东八区无夏令时，固定 +8 偏移与 IANA Asia/Shanghai 完全等效
    _CN_TZ: tzinfo = timezone(timedelta(hours=8))


def cn_now() -> datetime:
    return datetime.now(_CN_TZ)


def cn_tz() -> tzinfo:
    return _CN_TZ

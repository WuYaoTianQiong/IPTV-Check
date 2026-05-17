from datetime import datetime, timezone, timedelta

_CN_TZ = timezone(timedelta(hours=8))

def cn_now() -> datetime:
    return datetime.now(_CN_TZ)

def cn_tz() -> timezone:
    return _CN_TZ

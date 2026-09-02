import re
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timedelta, timezone


@dataclass
class EpgProgram:
    title: str = ""
    start: str = ""
    stop: str = ""
    desc: str = ""
    category: str = ""

    @property
    def start_datetime(self) -> Optional[datetime]:
        return self._parse_xmltv_time(self.start)

    @property
    def stop_datetime(self) -> Optional[datetime]:
        return self._parse_xmltv_time(self.stop)

    @property
    def duration_minutes(self) -> int:
        s, e = self.start_datetime, self.stop_datetime
        if s and e:
            return int((e - s).total_seconds() / 60)
        return 0

    @property
    def is_current(self) -> bool:
        now = self._utcnow()
        s, e = self.start_datetime, self.stop_datetime
        if s and e:
            return s <= now <= e
        return False

    @staticmethod
    def _utcnow() -> datetime:
        """naive UTC 当前时间（替代已废弃的 datetime.utcnow()）。"""
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_xmltv_time(time_str: str) -> Optional[datetime]:
        """解析 XMLTV 时间（YYYYMMDDHHMMSS ±HHMM）为 naive UTC datetime。

        正确处理时区偏移（此前实现直接 split('+')[0] 丢弃偏移，
        导致带 +0800 等时区的节目时间整体偏差）。
        """
        if not time_str:
            return None
        m = re.fullmatch(
            r"\s*(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\s*(?:([+-])(\d{2})(\d{2}))?\s*",
            time_str,
        )
        if not m:
            return None
        try:
            dt = datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6)),
            )
        except ValueError:
            return None
        if m.group(7):
            # XMLTV 偏移表示「本地时间 = UTC + 偏移」，转 UTC 需减去偏移
            sign = -1 if m.group(7) == "-" else 1
            offset_min = sign * (int(m.group(8)) * 60 + int(m.group(9)))
            dt = dt - timedelta(minutes=offset_min)
        return dt

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "start": self.start,
            "stop": self.stop,
            "desc": self.desc,
            "category": self.category,
            "duration_minutes": self.duration_minutes,
            "is_current": self.is_current,
        }


@dataclass
class EpgChannel:
    channel_id: str = ""
    display_name: str = ""
    programs: List[EpgProgram] = field(default_factory=list)

    def get_current_program(self) -> Optional[EpgProgram]:
        now = self._utcnow()
        for prog in self.programs:
            s, e = prog.start_datetime, prog.stop_datetime
            if s and e and s <= now <= e:
                return prog
        return None

    def get_programs_for_time_range(self, start: datetime, end: datetime) -> List[EpgProgram]:
        result = []
        for prog in self.programs:
            ps, pe = prog.start_datetime, prog.stop_datetime
            if ps and pe and ps < end and pe > start:
                result.append(prog)
        return result

    def to_dict(self) -> dict:
        return {
            "channel_id": self.channel_id,
            "display_name": self.display_name,
            "program_count": len(self.programs),
            "current": self.get_current_program().to_dict() if self.get_current_program() else None,
            "programs": [p.to_dict() for p in self.programs[:50]],
        }

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


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
        now = datetime.utcnow()
        s, e = self.start_datetime, self.stop_datetime
        if s and e:
            return s <= now <= e
        return False

    @staticmethod
    def _parse_xmltv_time(time_str: str) -> Optional[datetime]:
        if not time_str:
            return None
        try:
            clean = time_str.split("+")[0].split(" ")[0]
            if len(clean) >= 14:
                return datetime(
                    int(clean[0:4]), int(clean[4:6]), int(clean[6:8]),
                    int(clean[8:10]), int(clean[10:12]), int(clean[12:14]),
                )
        except (ValueError, IndexError):
            pass
        return None

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
        now = datetime.utcnow()
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

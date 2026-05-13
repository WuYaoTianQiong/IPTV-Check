from dataclasses import dataclass


@dataclass
class CheckConfig:
    timeout_connect: int = 3
    timeout_read: int = 8
    max_threads: int = 30
    min_threads: int = 5
    run_speed_test: bool = True
    use_cache: bool = True

    @property
    def timeout_tuple(self) -> tuple:
        return (self.timeout_connect, self.timeout_read)


@dataclass
class ExportConfig:
    export_m3u: bool = True
    export_txt: bool = True
    export_csv: bool = True
    export_xlsx: bool = True
    export_mode: str = "merged"
    ipv_split: bool = False

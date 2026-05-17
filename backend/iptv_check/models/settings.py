from dataclasses import dataclass


@dataclass
class CheckConfig:
    timeout_connect: int = 5
    timeout_read: int = 8
    max_threads: int = 120
    min_threads: int = 5
    run_speed_test: bool = False
    use_cache: bool = True
    max_latency_ms: int = 10000
    enable_recheck: bool = False

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

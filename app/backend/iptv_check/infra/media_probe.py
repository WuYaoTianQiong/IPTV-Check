import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class StreamProbeResult:
    has_video: bool = False
    has_audio: bool = False
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    resolution: Optional[str] = None
    duration: float = 0.0
    bit_rate: Optional[str] = None
    is_playable: bool = False
    error_message: Optional[str] = None

    def summary(self) -> str:
        if self.is_playable:
            parts = []
            if self.resolution:
                parts.append(self.resolution)
            if self.video_codec:
                parts.append(self.video_codec)
            if self.audio_codec:
                parts.append(self.audio_codec)
            return "可播放" + (f" ({', '.join(parts)})" if parts else "")
        return f"不可播放: {self.error_message or '未知原因'}"


class MediaProbe:
    _FFMPEG_AVAILABLE: Optional[bool] = None

    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout

    @classmethod
    def is_ffmpeg_available(cls) -> bool:
        if cls._FFMPEG_AVAILABLE is None:
            try:
                import ffmpeg
                cls._FFMPEG_AVAILABLE = True
            except ImportError:
                cls._FFMPEG_AVAILABLE = False
        return cls._FFMPEG_AVAILABLE

    async def probe(self, url: str) -> StreamProbeResult:
        if not self.is_ffmpeg_available():
            return StreamProbeResult(
                is_playable=False,
                error_message="ffprobe不可用，跳过深度检测",
            )

        try:
            probe_result = await asyncio.wait_for(
                self._run_ffprobe(url),
                timeout=self._timeout,
            )
            return probe_result
        except asyncio.TimeoutError:
            return StreamProbeResult(
                is_playable=False,
                error_message=f"探测超时({self._timeout}s)",
            )
        except Exception as e:
            logger.debug("流探测失败 %s: %s", url, e)
            return StreamProbeResult(
                is_playable=False,
                error_message=f"探测失败: {str(e)[:50]}",
            )

    async def _run_ffprobe(self, url: str) -> StreamProbeResult:
        import ffmpeg

        try:
            loop = asyncio.get_event_loop()
            probe_info = await loop.run_in_executor(
                None,
                lambda: ffmpeg.probe(
                    url,
                    v="error",
                    timeout=self._timeout,
                    analyzeduration="5000000",
                ),
            )
        except ffmpeg.Error as e:
            stderr = e.stderr.decode("utf-8", errors="ignore") if e.stderr else str(e)
            if "Invalid data" in stderr or "could not find codec" in stderr.lower():
                return StreamProbeResult(
                    is_playable=False,
                    error_message="流数据无效或无法解码",
                )
            return StreamProbeResult(
                is_playable=False,
                error_message=f"ffprobe错误: {stderr[:80]}",
            )

        return self._parse_probe_info(probe_info, url)

    @staticmethod
    def _parse_probe_info(probe_info: dict, url: str) -> StreamProbeResult:
        result = StreamProbeResult()
        streams = probe_info.get("streams", [])
        fmt = probe_info.get("format", {})

        for stream in streams:
            codec_type = stream.get("codec_type")
            codec_name = stream.get("codec_name", "unknown")

            if codec_type == "video":
                result.has_video = True
                result.video_codec = codec_name
                width = stream.get("width")
                height = stream.get("height")
                if width and height:
                    result.resolution = f"{width}x{height}"

            elif codec_type == "audio":
                result.has_audio = True
                result.audio_codec = codec_name

        duration = fmt.get("duration")
        if duration:
            try:
                result.duration = float(duration)
            except (ValueError, TypeError):
                pass

        bit_rate = fmt.get("bit_rate")
        if bit_rate:
            try:
                bit_rate_int = int(bit_rate)
                if bit_rate_int > 1000000:
                    result.bit_rate = f"{bit_rate_int / 1000000:.1f} Mbps"
                else:
                    result.bit_rate = f"{bit_rate_int / 1000:.0f} kbps"
            except (ValueError, TypeError):
                result.bit_rate = bit_rate

        result.is_playable = result.has_video or result.has_audio
        if not result.is_playable:
            parsed = urlparse(url)
            if parsed.path.endswith((".m3u8", ".m3u", ".ts")):
                result.is_playable = True

        return result

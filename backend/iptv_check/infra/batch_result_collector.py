"""
批量结果汇聚器
核心优化：将逐条SQLite写入改为批量写入，消除单消费者瓶颈
"""
import asyncio
import logging
from typing import Optional, Callable
from dataclasses import dataclass

from iptv_check.models.check_result import CheckResult

logger = logging.getLogger(__name__)


@dataclass
class CheckProgress:
    total: int = 0
    checked: int = 0
    valid: int = 0
    invalid: int = 0

    @property
    def progress_percent(self) -> float:
        return (self.checked / self.total * 100) if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "checked": self.checked,
            "valid": self.valid,
            "invalid": self.invalid,
            "progress_percent": round(self.progress_percent, 1),
        }


class BatchResultCollector:
    """
    批量结果汇聚器

    工作原理：
    1. 检测线程通过 call_soon_threadsafe 将结果提交到 asyncio 队列
    2. 后台协程定期从队列批量取出结果，批量写入 SQLite
    3. 进度通过内存计数器实时更新，避免数据库查询
    4. SSE 广播改为推送进度快照，而非每个频道的详细信息

    优势：
    - SQLite 写入从逐条改为批量（100条/次），性能提升 10 倍+
    - 消除单消费者瓶颈
    - 前端进度实时响应，无需等待数据库写入
    """

    def __init__(
        self,
        event_store,
        broadcast_fn: Callable,
        batch_size: int = 100,
        flush_interval: float = 3.0,
        session_id: str = "",
    ):
        self._event_store = event_store
        self._broadcast_fn = broadcast_fn
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._session_id = session_id

        self._result_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._progress = CheckProgress()

        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._complete_event = asyncio.Event()

    @property
    def session_id(self) -> str:
        return self._session_id

    async def start(self):
        """启动后台刷新协程"""
        self._running = True
        self._complete_event.clear()
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("[BatchCollector] 启动, session=%s, batch_size=%d, flush_interval=%.1fs",
                    self._session_id, self._batch_size, self._flush_interval)

    async def stop(self):
        """停止后台刷新协程，确保剩余结果写入"""
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_remaining()
        logger.info("[BatchCollector] 停止, 最终进度=%s", self._progress.to_dict())

    async def wait_for_complete(self):
        """等待检测完成"""
        await self._complete_event.wait()

    def set_total(self, total: int):
        """设置总频道数"""
        self._progress.total = total

    def get_progress_dict(self) -> dict:
        """获取当前进度（无需 await）"""
        return self._progress.to_dict()

    @property
    def progress(self) -> CheckProgress:
        """获取当前进度对象（公共属性）"""
        return self._progress

    async def submit_result(self, result_data: dict):
        """异步提交检测结果（内部使用）"""
        try:
            await self._result_queue.put(("result", result_data))
        except asyncio.QueueFull:
            logger.warning("[BatchCollector] 队列满，丢弃结果")

    async def submit_complete(self):
        """异步提交检测完成信号（内部使用）"""
        try:
            await self._result_queue.put(("complete", None))
        except asyncio.QueueFull:
            logger.warning("[BatchCollector] 队列满，无法提交完成信号")

    def submit_result_sync(self, result: CheckResult):
        """
        同步提交检测结果（由线程池线程调用）
        通过 call_soon_threadsafe 将结果提交到事件循环队列
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        result_data = {
            "url_key": result.channel.url_key,
            "name": result.channel.name,
            "url": result.channel.url,
            "is_valid": result.is_valid,
            "latency": result.latency_display,
            "speed": result.speed,
            "details": result.details,
            "group": result.channel.group,
            "sources": ", ".join(result.channel.sources),
            "country": result.channel.country,
            "is_radio": result.channel.is_radio,
            "language": result.channel.language,
            "content_type": self._classify_content_type(result),
        }
        try:
            loop.call_soon_threadsafe(self._result_queue.put_nowait, ("result", result_data))
        except asyncio.QueueFull:
            logger.warning("[BatchCollector] 队列满，丢弃结果: %s", result.channel.name)

    def submit_complete_sync(self):
        """同步提交检测完成信号（由线程池线程调用）"""
        logger.info("[BatchCollector] submit_complete_sync 被调用")
        try:
            loop = asyncio.get_running_loop()
            logger.info("[BatchCollector] 获取到运行中的事件循环")
        except RuntimeError as e:
            logger.error("[BatchCollector] 获取事件循环失败: %s", e)
            return
        try:
            loop.call_soon_threadsafe(self._result_queue.put_nowait, ("complete", None))
            logger.info("[BatchCollector] 完成信号已提交到队列")
        except asyncio.QueueFull:
            logger.error("[BatchCollector] 队列满，无法提交完成信号")
        except Exception as e:
            logger.error("[BatchCollector] 提交完成信号异常: %s", e)

    async def _flush_loop(self):
        """后台刷新循环：定时或达到 batch_size 时批量写入"""
        logger.info("[BatchCollector] _flush_loop 启动")
        batch: list[dict] = []

        while self._running:
            try:
                msg_type, data = await asyncio.wait_for(
                    self._result_queue.get(), timeout=self._flush_interval
                )
                logger.info("[BatchCollector] 收到消息: type=%s", msg_type)

                if msg_type == "result":
                    batch.append(data)
                    self._progress.checked += 1
                    if data.get("is_valid"):
                        self._progress.valid += 1
                    else:
                        self._progress.invalid += 1

                    if len(batch) >= self._batch_size:
                        await self._flush_batch(batch)
                        batch = []

                elif msg_type == "complete":
                    logger.info("[BatchCollector] 收到完成信号，准备刷新剩余批次")
                    if batch:
                        await self._flush_batch(batch)
                        batch = []
                    await self._on_complete()
                    self._complete_event.set()
                    logger.info("[BatchCollector] _complete_event 已设置，退出循环")
                    break

            except asyncio.TimeoutError:
                if batch:
                    await self._flush_batch(batch)
                    batch = []
                await self._broadcast_progress()
            except asyncio.CancelledError:
                logger.info("[BatchCollector] 刷新循环被取消")
                if batch:
                    await self._flush_batch(batch)
                raise
            except Exception as e:
                logger.error("[BatchCollector] 刷新循环异常: %s", e)

        logger.info("[BatchCollector] _flush_loop 退出")

    async def _flush_batch(self, batch: list[dict]):
        """批量写入一批结果到 SQLite"""
        if not batch:
            return

        events = []
        for data in batch:
            events.append(("channel_checked", data))

        try:
            await self._event_store.append_batch(events, self._session_id)
            logger.debug("[BatchCollector] 批量写入 %d 条结果", len(batch))
        except Exception as e:
            logger.error("[BatchCollector] 批量写入失败: %s", e)

    async def _flush_remaining(self):
        """写入队列中剩余的所有结果"""
        batch: list[dict] = []

        while not self._result_queue.empty():
            try:
                msg_type, data = self._result_queue.get_nowait()
                if msg_type == "result":
                    batch.append(data)
                    self._progress.checked += 1
                    if data.get("is_valid"):
                        self._progress.valid += 1
                    else:
                        self._progress.invalid += 1
                elif msg_type == "complete":
                    break
            except asyncio.QueueEmpty:
                break

        if batch:
            await self._flush_batch(batch)

        if not self._complete_event.is_set():
            await self._on_complete()
            self._complete_event.set()

    async def _broadcast_progress(self):
        """广播进度快照到前端"""
        progress = self._progress.to_dict()
        await self._broadcast_fn("progress_update", progress)

    async def _on_complete(self):
        """检测完成后的最终处理"""
        progress = self._progress.to_dict()
        await self._broadcast_fn("check_completed", {
            "total": progress["total"],
            "valid": progress["valid"],
            "invalid": progress["invalid"],
        })
        logger.info("[BatchCollector] 检测完成, %s", progress)

    @staticmethod
    def _classify_content_type(result: CheckResult) -> str:
        is_radio = result.channel.is_radio
        ch_name = result.channel.name
        group = result.channel.group
        url = result.channel.url
        country = result.channel.country

        if is_radio:
            return "广播"
        if any(kw in ch_name for kw in ["CCTV", "cctv"]) or "央视" in ch_name:
            return "央视"
        if "卫视" in ch_name or "卫视" in group:
            return "卫视"
        if any(kw in ch_name for kw in ["4K", "4k", "UHD", "uhd", "超清"]) or any(kw in group for kw in ["4K", "4k", "UHD", "uhd", "超清"]):
            return "4K"
        if any(kw in url for kw in ["ipv6", "IPv6", "/v6/"]) or "IPv6" in group:
            return "IPv6"
        if country and country.upper().split(";")[0] in {"CN", "CHN", "HK", "HKG", "MO", "MAC", "TW", "TWN"}:
            return "地方"
        if country:
            return "国际"
        return "其他"

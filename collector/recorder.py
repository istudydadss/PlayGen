"""Playwright 录制控制器"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Callable, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from collector.models import RecordingConfig, NetworkEvent, PageOperation
from collector.network_interceptor import NetworkInterceptor

logger = logging.getLogger(__name__)


class PlaywrightRecorder:
    """
    Playwright 录制控制器
    管理浏览器生命周期、录制状态和网络拦截
    """

    def __init__(self, config: RecordingConfig):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._interceptor: Optional[NetworkInterceptor] = None

        # 采集数据
        self.network_events: list[NetworkEvent] = []
        self.page_operations: list[PageOperation] = []

        # 状态
        self.is_recording = False
        self.is_paused = False

        # 外部回调
        self._on_network_event: Optional[Callable] = None
        self._on_page_action: Optional[Callable] = None

    async def _handle_network_event(self, event: NetworkEvent):
        """网络事件处理"""
        self.network_events.append(event)
        if self._on_network_event:
            try:
                result = self._on_network_event(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"外部网络事件回调失败: {e}")

    async def _handle_page_action(self, action: PageOperation):
        """页面操作处理"""
        self.page_operations.append(action)
        if self._on_page_action:
            try:
                result = self._on_page_action(action)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"外部操作回调失败: {e}")

    def set_callbacks(self, on_network_event=None, on_page_action=None):
        """设置外部回调"""
        self._on_network_event = on_network_event
        self._on_page_action = on_page_action

    async def start(self):
        """启动录制"""
        if self.is_recording:
            raise RuntimeError("录制已在进行中")

        logger.info(f"启动录制: session={self.config.session_id}, browser={self.config.browser}")

        # 启动 Playwright
        self._playwright = await async_playwright().start()

        # 启动浏览器
        browser_type = getattr(self._playwright, self.config.browser)
        self._browser = await browser_type.launch(
            headless=self.config.headless,
        )

        # 创建上下文
        context_options = {
            "viewport": self.config.viewport,
            "ignore_https_errors": True,
        }

        # 复用登录态
        if self.config.storage_state_path:
            context_options["storage_state"] = self.config.storage_state_path

        self._context = await self._browser.new_context(**context_options)

        # 创建页面
        self._page = await self._context.new_page()

        # 设置网络拦截器
        self._interceptor = NetworkInterceptor(
            session_id=self.config.session_id,
            max_body_size=self.config.max_response_body_size,
            on_event=self._handle_network_event,
            on_action=self._handle_page_action,
        )
        await self._interceptor.attach(self._page)

        # 导航到起始 URL
        if self.config.start_url:
            await self._page.goto(self.config.start_url, timeout=self.config.timeout)

        self.is_recording = True
        self.is_paused = False
        logger.info(f"录制已启动: {self.config.start_url}")

    async def pause(self):
        """暂停录制"""
        if not self.is_recording:
            raise RuntimeError("录制未启动")
        if self.is_paused:
            return

        # 暂停网络拦截（通过标记）
        self.is_paused = True
        logger.info("录制已暂停")

    async def resume(self):
        """继续录制"""
        if not self.is_recording:
            raise RuntimeError("录制未启动")
        if not self.is_paused:
            return

        self.is_paused = False
        logger.info("录制已继续")

    async def stop(self) -> dict:
        """
        停止录制并返回采集结果
        返回: {network_events, page_operations, summary}
        """
        if not self.is_recording:
            raise RuntimeError("录制未启动")

        logger.info("停止录制...")
        self.is_recording = False

        # 解绑拦截器
        if self._interceptor and self._page:
            await self._interceptor.detach(self._page)

        # 关闭浏览器
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.error(f"关闭浏览器时出错: {e}")

        # 生成摘要
        summary = {
            "session_id": self.config.session_id,
            "total_network_events": len(self.network_events),
            "total_page_operations": len(self.page_operations),
            "successful_requests": sum(
                1 for e in self.network_events
                if e.response and 200 <= e.response.status < 300
            ),
            "failed_requests": sum(
                1 for e in self.network_events
                if e.failure_reason
            ),
            "xhr_fetch_count": sum(
                1 for e in self.network_events
                if e.request.resource_type in ("xhr", "fetch")
            ),
        }

        logger.info(f"录制完成: {summary}")

        return {
            "network_events": self.network_events,
            "page_operations": self.page_operations,
            "summary": summary,
        }

    async def get_status(self) -> dict:
        """获取录制状态"""
        return {
            "session_id": self.config.session_id,
            "is_recording": self.is_recording,
            "is_paused": self.is_paused,
            "network_events_count": len(self.network_events),
            "page_operations_count": len(self.page_operations),
        }

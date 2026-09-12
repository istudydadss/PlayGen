"""Playwright 网络流量拦截器"""
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, Callable, Any
from urllib.parse import urlparse, parse_qs
from playwright.async_api import Page, Request, Response

from collector.models import (
    CapturedRequest, CapturedResponse, NetworkEvent, PageOperation
)

logger = logging.getLogger(__name__)


class NetworkInterceptor:
    """
    网络流量拦截器
    监听 Playwright 页面的 request/response 事件，采集完整网络流量数据
    """

    def __init__(
        self,
        session_id: str,
        max_body_size: int = 1_048_576,
        on_event: Optional[Callable[[NetworkEvent], Any]] = None,
        on_action: Optional[Callable[[PageOperation], Any]] = None,
    ):
        self.session_id = session_id
        self.max_body_size = max_body_size
        self.on_event = on_event
        self.on_action = on_action

        # 请求开始时间映射（用于计算耗时）
        self._request_start_times: dict[str, datetime] = {}
        # 页面 URL 追踪
        self._current_page_url: Optional[str] = None

    async def attach(self, page: Page):
        """将拦截器绑定到页面"""
        page.on("request", self._on_request)
        page.on("response", self._on_response)
        page.on("requestfailed", self._on_request_failed)
        page.on("framenavigated", self._on_frame_navigated)

    async def detach(self, page: Page):
        """从页面解绑"""
        page.remove_listener("request", self._on_request)
        page.remove_listener("response", self._on_response)
        page.remove_listener("requestfailed", self._on_request_failed)
        page.remove_listener("framenavigated", self._on_frame_navigated)

    async def _on_request(self, request: Request):
        """请求事件处理"""
        request_id = request.url + "_" + str(id(request))
        self._request_start_times[request_id] = datetime.utcnow()

        # 解析 URL
        parsed = urlparse(request.url)
        query_params = {}
        if parsed.query:
            for k, v in parse_qs(parsed.query).items():
                query_params[k] = v[0] if len(v) == 1 else v

        # 解析请求体
        body = None
        body_raw = None
        post_data = request.post_data
        if post_data:
            body_raw = post_data
            content_type = request.headers.get("content-type", "")
            if "application/json" in content_type:
                try:
                    body = json.loads(post_data)
                except (json.JSONDecodeError, ValueError):
                    body = None

        captured_request = CapturedRequest(
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
            protocol=request.headers.get(":protocol", "HTTP/1.1"),
            headers=dict(request.headers),
            query_params=query_params,
            body=body,
            body_raw=body_raw,
            post_data=post_data,
        )

        # 创建网络事件（先记录请求，等 response 时补全）
        event = NetworkEvent(
            request_id=request_id,
            session_id=self.session_id,
            page_url=self._current_page_url,
            frame_url=request.frame.url if request.frame else None,
            request=captured_request,
            started_at=self._request_start_times[request_id],
        )

        # 暂存事件，等 response 时补全
        request._playgen_event = event

    async def _on_response(self, response: Response):
        """响应事件处理"""
        request = response.request
        request_id = request.url + "_" + str(id(request))
        event: Optional[NetworkEvent] = getattr(request, "_playgen_event", None)

        if not event:
            # 如果没有找到对应的请求事件，创建一个
            await self._on_request(request)
            event = getattr(request, "_playgen_event", None)
            if not event:
                return

        started_at = self._request_start_times.get(request_id, datetime.utcnow())
        response_at = datetime.utcnow()
        duration_ms = (response_at - started_at).total_seconds() * 1000

        # 解析响应体
        body = None
        body_raw = None
        body_truncated = False
        body_hash = None
        content_type = response.headers.get("content-type", "")

        try:
            # 只对文本类内容尝试读取 body
            if any(t in content_type for t in ["json", "text", "xml", "html", "javascript"]):
                raw_body = await response.text()
                if len(raw_body.encode("utf-8")) > self.max_body_size:
                    body_raw = raw_body[:self.max_body_size]
                    body_truncated = True
                else:
                    body_raw = raw_body

                # 尝试解析 JSON
                if "json" in content_type and body_raw:
                    try:
                        body = json.loads(body_raw)
                    except (json.JSONDecodeError, ValueError):
                        body = None

                body_hash = hashlib.sha256(body_raw.encode("utf-8") if body_raw else b"").hexdigest()
        except Exception as e:
            logger.debug(f"读取响应体失败: {e}")

        captured_response = CapturedResponse(
            status=response.status,
            headers=dict(response.headers),
            body=body,
            body_raw=body_raw,
            body_truncated=body_truncated,
            body_hash=body_hash,
            content_type=content_type,
        )

        event.response = captured_response
        event.response_at = response_at
        event.duration_ms = duration_ms

        # 回调
        if self.on_event:
            try:
                await self.on_event(event) if _is_async(self.on_event) else self.on_event(event)
            except Exception as e:
                logger.error(f"网络事件回调失败: {e}")

        # 清理
        self._request_start_times.pop(request_id, None)

    async def _on_request_failed(self, request: Request, *args):
        """请求失败处理
        
        兼容不同 Playwright 版本：
        - 旧版: requestfailed 事件传递 (request, failure)
        - 新版: requestfailed 事件只传递 (request)，failure 通过 request.failure 获取
        """
        request_id = request.url + "_" + str(id(request))
        event: Optional[NetworkEvent] = getattr(request, "_playgen_event", None)

        # 兼容获取 failure 信息
        failure = args[0] if args else getattr(request, "failure", None)
        if failure is None:
            try:
                failure = request.failure
            except Exception:
                failure = "unknown"

        if event:
            event.failure_reason = str(failure) if failure else "unknown"
            event.response_at = datetime.utcnow()
            started_at = self._request_start_times.get(request_id)
            if started_at:
                event.duration_ms = (event.response_at - started_at).total_seconds() * 1000

            if self.on_event:
                try:
                    await self.on_event(event) if _is_async(self.on_event) else self.on_event(event)
                except Exception as e:
                    logger.error(f"失败事件回调失败: {e}")

        self._request_start_times.pop(request_id, None)

    async def _on_frame_navigated(self, frame):
        """页面导航处理"""
        if frame == frame.page.main_frame:
            self._current_page_url = frame.url
            # 记录导航操作
            if self.on_action:
                action = PageOperation(
                    operation_type="navigate",
                    page_url=frame.url,
                    timestamp=datetime.utcnow(),
                )
                try:
                    await self.on_action(action) if _is_async(self.on_action) else self.on_action(action)
                except Exception as e:
                    logger.error(f"操作回调失败: {e}")


def _is_async(func):
    """检查函数是否为异步函数"""
    import asyncio
    return asyncio.iscoroutinefunction(func)

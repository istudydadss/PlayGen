"""录制服务 - 桥接 collector 模块与 API 层"""
import asyncio
import json
import logging
import subprocess
import time
from datetime import datetime
from typing import Optional, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from collector.models import RecordingConfig, NetworkEvent, PageOperation
from collector.recorder import PlaywrightRecorder
from app.database import async_session_factory
from app.models.recording import RecordingSession, NetworkRecord, PageAction, RecordingStatus
from app.models.api_asset import ApiDefinition, ApiSample, RiskLevel, LifecycleStatus
from app.services.websocket_manager import ws_manager
from analyzer.filter import TrafficFilter
from analyzer.normalizer import UrlNormalizer
from analyzer.schema_inferrer import SchemaInferrer
from analyzer.dedup import InterfaceDeduplicator
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _strip_tz(dt: Optional[datetime]) -> Optional[datetime]:
    """去除 datetime 的时区信息，兼容 PostgreSQL TIMESTAMP WITHOUT TIME ZONE"""
    if dt is not None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


class RecordingService:
    """
    录制服务
    管理活跃的录制会话，桥接 Playwright 采集器与数据库持久化
    """

    def __init__(self):
        # session_id(str) -> {recorder, process, cdp_url}
        self._active_sessions: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 启动录制
    # ------------------------------------------------------------------
    async def start_recording(self, session_id: str, session_db: RecordingSession):
        """启动 Playwright 浏览器并开始录制"""
        if session_id in self._active_sessions:
            raise RuntimeError(f"录制会话 {session_id} 已在进行中")

        # 通过 subprocess 启动 Chrome，开启 CDP 远程调试端口
        cdp_port = 9222 + hash(session_id) % 100  # 基于 session_id 分配端口，避免冲突
        chrome_process = self._launch_chrome(session_db.start_url, cdp_port)

        # 等待 Chrome 启动
        await asyncio.sleep(2)

        # 通过 CDP 连接 Chrome
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        cdp_url = f"http://127.0.0.1:{cdp_port}"

        try:
            browser = await pw.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            logger.error(f"CDP 连接失败: {e}")
            chrome_process.terminate()
            await pw.stop()
            raise

        # 获取已有页面（Chrome 启动时会打开一个默认页面）
        contexts = browser.contexts
        if contexts and contexts[0].pages:
            page = contexts[0].pages[0]
        else:
            context = await browser.new_context()
            page = await context.new_page()

        # 如果 Chrome 没有导航到目标 URL，手动导航
        if session_db.start_url and page.url != session_db.start_url:
            await page.goto(session_db.start_url, timeout=settings.BROWSER_TIMEOUT)

        # 创建 PlaywrightRecorder 并注入已有的 page/browser
        config = RecordingConfig(
            session_id=session_id,
            project_id=str(session_db.project_id),
            browser="chromium",
            headless=False,
            start_url=session_db.start_url,
        )
        recorder = PlaywrightRecorder(config)
        # 手动注入，跳过 recorder.start() 中的浏览器启动流程
        recorder._playwright = pw
        recorder._browser = browser
        recorder._context = contexts[0] if contexts else page.context
        recorder._page = page

        # 设置网络拦截器
        from collector.network_interceptor import NetworkInterceptor
        interceptor = NetworkInterceptor(
            session_id=session_id,
            max_body_size=settings.RESPONSE_BODY_MAX_SIZE,
            on_event=recorder._handle_network_event,
            on_action=recorder._handle_page_action,
        )
        await interceptor.attach(page)
        recorder._interceptor = interceptor
        recorder.is_recording = True

        # 设置回调：实时保存流量到数据库
        recorder.set_callbacks(
            on_network_event=lambda event: self._on_network_event(session_id, event),
            on_page_action=lambda action: self._on_page_action(session_id, action),
        )

        # 记录活跃会话
        self._active_sessions[session_id] = {
            "recorder": recorder,
            "chrome_process": chrome_process,
            "cdp_url": cdp_url,
            "cdp_port": cdp_port,
        }

        # 更新数据库状态
        async with async_session_factory() as db:
            session_db_obj = await db.get(RecordingSession, UUID(session_id))
            if session_db_obj:
                session_db_obj.status = RecordingStatus.RECORDING
                session_db_obj.started_at = datetime.utcnow()
                await db.commit()

        logger.info(f"录制已启动: session={session_id}, CDP={cdp_url}")

    def _launch_chrome(self, url: Optional[str], port: int) -> subprocess.Popen:
        """启动 Chrome 浏览器（开启 CDP 远程调试端口）"""
        import platform

        system = platform.system()
        chrome_paths = []

        if system == "Windows":
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            ]
        elif system == "Darwin":
            chrome_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        else:  # Linux
            chrome_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/usr/bin/chromium",
            ]

        chrome_exe = None
        import os
        for path in chrome_paths:
            expanded = os.path.expandvars(path)
            if os.path.exists(expanded):
                chrome_exe = expanded
                break

        if not chrome_exe:
            chrome_exe = "google-chrome"  # 回退到 PATH 中查找

        cmd = [
            chrome_exe,
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ]
        if url:
            cmd.append(url)

        logger.info(f"启动 Chrome: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return process

    # ------------------------------------------------------------------
    # 回调：实时保存网络事件
    # ------------------------------------------------------------------
    async def _on_network_event(self, session_id: str, event: NetworkEvent):
        """网络事件回调 - 实时保存到数据库并推送 WebSocket"""
        try:
            await self._save_network_event(session_id, event)
            # WebSocket 实时推送
            await ws_manager.broadcast_to_session(session_id, {
                "type": "network_event",
                "data": {
                    "url": event.request.url,
                    "method": event.request.method,
                    "status_code": event.response.status if event.response else None,
                    "duration_ms": event.duration_ms,
                    "resource_type": event.request.resource_type,
                    "started_at": event.started_at.isoformat() if event.started_at else None,
                }
            })
        except Exception as e:
            logger.error(f"保存网络事件失败: {e}")

    async def _on_page_action(self, session_id: str, action: PageOperation):
        """页面操作回调 - 保存到数据库"""
        try:
            async with async_session_factory() as db:
                db_action = PageAction(
                    session_id=UUID(session_id),
                    action_type=action.operation_type,
                    selector=action.selector,
                    page_url=action.page_url,
                    frame_url=action.frame_url,
                    input_value=action.input_value,
                    timestamp=_strip_tz(action.timestamp),
                    metadata=action.metadata,
                )
                db.add(db_action)

                # 更新会话操作计数
                session = await db.get(RecordingSession, UUID(session_id))
                if session:
                    session.total_actions = (session.total_actions or 0) + 1

                await db.commit()

            # WebSocket 推送
            await ws_manager.broadcast_to_session(session_id, {
                "type": "page_action",
                "data": {
                    "type": action.operation_type,
                    "page_url": action.page_url,
                    "timestamp": action.timestamp.isoformat() if action.timestamp else None,
                }
            })
        except Exception as e:
            logger.error(f"保存页面操作失败: {e}")

    async def _save_network_event(self, session_id: str, event: NetworkEvent):
        """将网络事件保存到数据库"""
        async with async_session_factory() as db:
            # 先用简单评分判断是否为业务接口
            from analyzer.filter import TrafficFilter
            tf = TrafficFilter()
            result = tf._evaluate_event(event)

            record = NetworkRecord(
                session_id=UUID(session_id),
                url=event.request.url,
                method=event.request.method,
                resource_type=event.request.resource_type,
                protocol=event.request.protocol,
                request_headers=event.request.headers or None,
                query_params=event.request.query_params or None,
                request_body=event.request.body if isinstance(event.request.body, dict) else None,
                request_body_raw=event.request.body_raw,
                post_data=event.request.post_data,
                status_code=event.response.status if event.response else None,
                response_headers=event.response.headers if event.response else None,
                response_body=event.response.body if event.response and isinstance(event.response.body, dict) else None,
                response_body_raw=event.response.body_raw if event.response else None,
                response_body_truncated=event.response.body_truncated if event.response else False,
                response_body_hash=event.response.body_hash if event.response else None,
                started_at=_strip_tz(event.started_at),
                response_at=_strip_tz(event.response_at),
                duration_ms=event.duration_ms,
                page_url=event.page_url,
                frame_url=event.frame_url,
                failure_reason=event.failure_reason,
                is_business=result["is_business"],
                business_score=result["score"],
            )
            db.add(record)

            # 更新会话请求计数
            session = await db.get(RecordingSession, UUID(session_id))
            if session:
                session.total_requests = (session.total_requests or 0) + 1

            await db.commit()

    # ------------------------------------------------------------------
    # 暂停 / 继续
    # ------------------------------------------------------------------
    async def pause_recording(self, session_id: str):
        """暂停录制"""
        if session_id not in self._active_sessions:
            raise RuntimeError(f"录制会话 {session_id} 不在进行中")

        recorder = self._active_sessions[session_id]["recorder"]
        await recorder.pause()

        async with async_session_factory() as db:
            session = await db.get(RecordingSession, UUID(session_id))
            if session:
                session.status = RecordingStatus.PAUSED
                await db.commit()

        logger.info(f"录制已暂停: session={session_id}")

    async def resume_recording(self, session_id: str):
        """继续录制"""
        if session_id not in self._active_sessions:
            raise RuntimeError(f"录制会话 {session_id} 不在进行中")

        recorder = self._active_sessions[session_id]["recorder"]
        await recorder.resume()

        async with async_session_factory() as db:
            session = await db.get(RecordingSession, UUID(session_id))
            if session:
                session.status = RecordingStatus.RECORDING
                await db.commit()

        logger.info(f"录制已继续: session={session_id}")

    # ------------------------------------------------------------------
    # 停止录制
    # ------------------------------------------------------------------
    async def stop_recording(self, session_id: str):
        """停止录制，关闭浏览器"""
        if session_id not in self._active_sessions:
            raise RuntimeError(f"录制会话 {session_id} 不在进行中")

        session_info = self._active_sessions[session_id]
        recorder: PlaywrightRecorder = session_info["recorder"]
        chrome_process: subprocess.Popen = session_info["chrome_process"]

        # 停止录制（解绑拦截器、关闭浏览器）
        try:
            await recorder.stop()
        except Exception as e:
            logger.error(f"停止 recorder 失败: {e}")

        # 关闭 Chrome 进程
        try:
            chrome_process.terminate()
            chrome_process.wait(timeout=5)
        except Exception as e:
            logger.warning(f"关闭 Chrome 进程: {e}")
            chrome_process.kill()

        # 清理
        del self._active_sessions[session_id]

        # 更新数据库状态
        async with async_session_factory() as db:
            session = await db.get(RecordingSession, UUID(session_id))
            if session:
                session.status = RecordingStatus.STOPPED
                session.stopped_at = datetime.utcnow()
                await db.commit()

        logger.info(f"录制已停止: session={session_id}")

    # ------------------------------------------------------------------
    # 分析流量
    # ------------------------------------------------------------------
    async def analyze_recording(self, session_id: str):
        """
        分析已录制的流量
        流程: 读取 NetworkRecord → 转 NetworkEvent → 过滤/归一化/去重/Schema推断 → 写回结果 + 创建 ApiDefinition
        """
        async with async_session_factory() as db:
            session = await db.get(RecordingSession, UUID(session_id))
            if not session:
                raise RuntimeError(f"录制会话 {session_id} 不存在")

            session.status = RecordingStatus.ANALYZING
            await db.commit()

        try:
            # 1. 从数据库读取所有 NetworkRecord，转为 NetworkEvent
            events = await self._load_network_events(session_id)
            if not events:
                logger.warning(f"无流量数据可分析: session={session_id}")
                async with async_session_factory() as db:
                    session = await db.get(RecordingSession, UUID(session_id))
                    session.status = RecordingStatus.ANALYZED
                    await db.commit()
                return

            # 2. 过滤 + 评分
            tf = TrafficFilter()
            filter_results = tf.filter_and_score(events)

            # 3. 归一化 + 去重（仅业务接口）
            business_events = [
                r["event"] for r in filter_results if r["is_business"]
            ]
            normalizer = UrlNormalizer()
            deduplicator = InterfaceDeduplicator(normalizer)
            dedup_result = dedup_result = deduplicator.deduplicate(business_events)

            # 4. Schema 推断
            inferrer = SchemaInferrer()

            # 5. 回写分析结果到 NetworkRecord
            async with async_session_factory() as db:
                # 构建 event_index -> NetworkRecord 映射
                all_records_q = await db.execute(
                    select(NetworkRecord).where(
                        NetworkRecord.session_id == UUID(session_id)
                    ).order_by(NetworkRecord.started_at.asc())
                )
                all_records = list(all_records_q.scalars().all())

                # 更新 is_business / business_score
                for result in filter_results:
                    event = result["event"]
                    for record in all_records:
                        if record.url == event.request.url and record.method == event.request.method:
                            record.is_business = result["is_business"]
                            record.business_score = result["score"]
                            break

                # 6. 创建 ApiDefinition + ApiSample
                for fingerprint, iface in dedup_result["interfaces"].items():
                    # 查找是否已存在同指纹接口
                    existing = await db.execute(
                        select(ApiDefinition).where(
                            ApiDefinition.fingerprint == fingerprint
                        )
                    )
                    existing_api = existing.scalar_one_or_none()

                    if not existing_api:
                        # 推断响应 Schema
                        response_schemas = []
                        for evt_idx in iface["events"]:
                            evt = business_events[evt_idx] if evt_idx < len(business_events) else None
                            if evt and evt.response and evt.response.body and isinstance(evt.response.body, dict):
                                response_schemas.append(inferrer.infer(evt.response.body))

                        merged_schema = inferrer.merge_schemas(response_schemas) if response_schemas else None

                        # 从路径推断接口名
                        path_parts = [p for p in iface["normalized_path"].split("/") if p and not p.startswith("{")]
                        api_name = " ".join(path_parts[-2:]) if path_parts else iface["normalized_path"]

                        api_def = ApiDefinition(
                            project_id=session.project_id,
                            name=api_name.upper(),
                            method=iface["method"],
                            normalized_path=iface["normalized_path"],
                            fingerprint=fingerprint,
                            sample_count=iface["sample_count"],
                            first_seen_at=datetime.utcnow(),
                            last_seen_at=datetime.utcnow(),
                            response_schema=merged_schema,
                            lifecycle=LifecycleStatus.DISCOVERED,
                            risk_level=RiskLevel.CONTROLLED,
                        )
                        db.add(api_def)
                        await db.flush()

                        # 创建 ApiSample 关联到 NetworkRecord
                        for evt_idx in iface["events"]:
                            if evt_idx < len(all_records):
                                sample = ApiSample(
                                    api_id=api_def.id,
                                    network_record_id=all_records[evt_idx].id,
                                    session_id=UUID(session_id),
                                    status_code=all_records[evt_idx].status_code,
                                    duration_ms=all_records[evt_idx].duration_ms,
                                )
                                db.add(sample)
                    else:
                        # 更新已有接口的统计
                        existing_api.sample_count += iface["sample_count"]
                        existing_api.last_seen_at = datetime.utcnow()

                session.status = RecordingStatus.ANALYZED
                await db.commit()

            logger.info(
                f"分析完成: session={session_id}, "
                f"{len(events)} 请求 -> {len(dedup_result['interfaces'])} 个接口"
            )

        except Exception as e:
            logger.error(f"分析失败: session={session_id}, error={e}")
            async with async_session_factory() as db:
                session = await db.get(RecordingSession, UUID(session_id))
                if session:
                    session.status = RecordingStatus.ERROR
                    session.error_message = str(e)
                    await db.commit()
            raise

    async def _load_network_events(self, session_id: str) -> list:
        """从数据库加载网络记录，转为 NetworkEvent 列表"""
        from collector.models import CapturedRequest, CapturedResponse

        async with async_session_factory() as db:
            result = await db.execute(
                select(NetworkRecord)
                .where(NetworkRecord.session_id == UUID(session_id))
                .order_by(NetworkRecord.started_at.asc())
            )
            records = list(result.scalars().all())

        events = []
        for record in records:
            request = CapturedRequest(
                url=record.url,
                method=record.method,
                resource_type=record.resource_type or "other",
                protocol=record.protocol,
                headers=record.request_headers or {},
                query_params=record.query_params or {},
                body=record.request_body,
                body_raw=record.request_body_raw,
                post_data=record.post_data,
            )

            response = None
            if record.status_code is not None:
                response = CapturedResponse(
                    status=record.status_code,
                    headers=record.response_headers or {},
                    body=record.response_body,
                    body_raw=record.response_body_raw,
                    body_truncated=record.response_body_truncated or False,
                    body_hash=record.response_body_hash,
                    content_type=(record.response_headers or {}).get("content-type"),
                )

            event = NetworkEvent(
                request_id=f"{record.url}_{record.id}",
                session_id=str(record.session_id),
                page_url=record.page_url,
                frame_url=record.frame_url,
                request=request,
                response=response,
                started_at=record.started_at or datetime.utcnow(),
                response_at=record.response_at,
                duration_ms=record.duration_ms,
                failure_reason=record.failure_reason,
            )
            events.append(event)

        return events

    # ------------------------------------------------------------------
    # 查询方法
    # ------------------------------------------------------------------
    def get_cdp_url(self, session_id: str) -> Optional[str]:
        """获取 CDP 调试 URL"""
        info = self._active_sessions.get(session_id)
        return info["cdp_url"] if info else None

    def is_recording_active(self, session_id: str) -> bool:
        """检查录制是否仍在进行"""
        return session_id in self._active_sessions


# 全局单例
recording_service = RecordingService()

"""采集与分析相关 Celery 任务"""
import asyncio
import logging
from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.collector.analyze_recording_task", bind=True)
def analyze_recording_task(self, session_id: str):
    """
    异步分析录制流量（Celery 任务）
    在 collector worker 进程中执行，不阻塞 API 服务
    """
    logger.info(f"开始分析录制流量: session={session_id}")

    async def _run():
        # 在 worker 进程中创建独立的 RecordingService 实例
        from app.services.recording_service import RecordingService
        service = RecordingService()
        await service.analyze_recording(session_id)

    try:
        asyncio.run(_run())
        logger.info(f"分析完成: session={session_id}")
    except Exception as e:
        logger.error(f"分析失败: session={session_id}, error={e}")
        raise

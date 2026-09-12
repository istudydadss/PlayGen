"""录制管理 API"""
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from uuid import UUID

from app.database import get_db
from app.models.recording import RecordingSession, NetworkRecord, RecordingStatus
from app.models.project import Project
from app.schemas.recording import (
    RecordingCreate, RecordingResponse, RecordingListResponse,
    TrafficRecordResponse, TrafficDetailResponse, TrafficListResponse,
)
from app.services.recording_service import recording_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=RecordingResponse, status_code=201)
async def start_recording(
    data: RecordingCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """启动录制 - 通过 CDP 连接 Chrome 浏览器"""
    project = await db.get(Project, data.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    session = RecordingSession(
        project_id=data.project_id,
        environment_id=data.environment_id,
        name=data.name,
        browser=data.browser,
        start_url=data.start_url,
        capture_trace=data.capture_trace,
        status=RecordingStatus.IDLE,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    session_id_str = str(session.id)

    async def _start():
        try:
            await recording_service.start_recording(session_id_str, session)
        except Exception as e:
            error_detail = traceback.format_exc()
            logger.error(f"启动录制失败: {error_detail}")
            from app.database import async_session_factory
            async with async_session_factory() as err_db:
                err_session = await err_db.get(RecordingSession, session.id)
                if err_session:
                    err_session.status = RecordingStatus.ERROR
                    err_session.error_message = error_detail[-500:]
                    await err_db.commit()

    background_tasks.add_task(_start)

    return session


@router.post("/{recording_id}/pause", response_model=RecordingResponse)
async def pause_recording(recording_id: UUID, db: AsyncSession = Depends(get_db)):
    """暂停录制"""
    session = await db.get(RecordingSession, recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    if session.status != RecordingStatus.RECORDING:
        raise HTTPException(status_code=400, detail="当前状态不允许暂停")

    session_id_str = str(recording_id)

    # 检查录制是否在活跃列表中
    if not recording_service.is_recording_active(session_id_str):
        raise HTTPException(status_code=400, detail="录制进程不存在，可能已异常退出")

    await recording_service.pause_recording(session_id_str)

    await db.refresh(session)
    return session


@router.post("/{recording_id}/resume", response_model=RecordingResponse)
async def resume_recording(recording_id: UUID, db: AsyncSession = Depends(get_db)):
    """继续录制"""
    session = await db.get(RecordingSession, recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    if session.status != RecordingStatus.PAUSED:
        raise HTTPException(status_code=400, detail="当前状态不允许继续")

    session_id_str = str(recording_id)

    if not recording_service.is_recording_active(session_id_str):
        raise HTTPException(status_code=400, detail="录制进程不存在，可能已异常退出")

    await recording_service.resume_recording(session_id_str)

    await db.refresh(session)
    return session


@router.post("/{recording_id}/stop", response_model=RecordingResponse)
async def stop_recording(
    recording_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """停止录制并触发分析"""
    session = await db.get(RecordingSession, recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    if session.status not in (RecordingStatus.RECORDING, RecordingStatus.PAUSED):
        raise HTTPException(status_code=400, detail="当前状态不允许停止")

    session_id_str = str(recording_id)

    # 停止录制（关闭浏览器）
    if recording_service.is_recording_active(session_id_str):
        await recording_service.stop_recording(session_id_str)
    else:
        # 录制进程可能已异常退出，直接更新状态
        session.status = RecordingStatus.STOPPED
        session.stopped_at = datetime.utcnow()
        await db.flush()

    # 异步触发分析（纯数据处理，不需要 Playwright）
    async def _analyze():
        try:
            await recording_service.analyze_recording(session_id_str)
        except Exception as e:
            logger.error(f"分析失败: {e}")

    background_tasks.add_task(_analyze)

    await db.refresh(session)
    return session


@router.get("", response_model=RecordingListResponse)
async def list_recordings(
    project_id: UUID = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询录制列表"""
    query = select(RecordingSession)
    count_query = select(func.count()).select_from(RecordingSession)

    if project_id:
        query = query.where(RecordingSession.project_id == project_id)
        count_query = count_query.where(RecordingSession.project_id == project_id)
    if status:
        query = query.where(RecordingSession.status == status)
        count_query = count_query.where(RecordingSession.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(RecordingSession.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return RecordingListResponse(total=total, items=items)


@router.get("/{recording_id}/traffic", response_model=TrafficListResponse)
async def get_traffic(
    recording_id: UUID,
    is_business: bool = Query(None),
    resource_type: str = Query(None),
    method: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """查询录制流量列表"""
    query = select(NetworkRecord).where(NetworkRecord.session_id == recording_id)
    count_query = select(func.count()).select_from(NetworkRecord).where(NetworkRecord.session_id == recording_id)

    if is_business is not None:
        query = query.where(NetworkRecord.is_business == is_business)
        count_query = count_query.where(NetworkRecord.is_business == is_business)
    if resource_type:
        query = query.where(NetworkRecord.resource_type == resource_type)
        count_query = count_query.where(NetworkRecord.resource_type == resource_type)
    if method:
        query = query.where(NetworkRecord.method == method.upper())
        count_query = count_query.where(NetworkRecord.method == method.upper())

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(NetworkRecord.started_at.asc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return TrafficListResponse(total=total, items=items)


@router.get("/{recording_id}/traffic/{record_id}", response_model=TrafficDetailResponse)
async def get_traffic_detail(
    recording_id: UUID, record_id: UUID, db: AsyncSession = Depends(get_db)
):
    """查询流量详情"""
    record = await db.get(NetworkRecord, record_id)
    if not record or record.session_id != recording_id:
        raise HTTPException(status_code=404, detail="流量记录不存在")
    return record


@router.post("/{recording_id}/analyze")
async def trigger_analysis(
    recording_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """重新触发分析"""
    session = await db.get(RecordingSession, recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="录制会话不存在")
    if session.status not in (RecordingStatus.STOPPED, RecordingStatus.ANALYZED):
        raise HTTPException(status_code=400, detail="当前状态不允许分析")

    session.status = RecordingStatus.ANALYZING
    await db.flush()

    session_id_str = str(recording_id)

    async def _analyze():
        try:
            await recording_service.analyze_recording(session_id_str)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"分析失败: {e}")

    background_tasks.add_task(_analyze)

    return {"message": "分析任务已触发", "session_id": str(recording_id)}


@router.get("/{recording_id}/status")
async def get_recording_status(recording_id: UUID):
    """获取录制实时状态（含 CDP URL）"""
    session_id_str = str(recording_id)
    is_active = recording_service.is_recording_active(session_id_str)
    cdp_url = recording_service.get_cdp_url(session_id_str)

    return {
        "session_id": session_id_str,
        "is_active": is_active,
        "cdp_url": cdp_url,
    }

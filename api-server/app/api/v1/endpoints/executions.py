"""执行管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from uuid import UUID
import uuid as uuid_lib

from app.database import get_db
from app.models.scenario import ExecutionTask, StepResult, BusinessScenario, TaskStatus, TriggerType
from app.schemas.recording import (
    ExecutionCreate, ExecutionResponse, ExecutionDetailResponse, StepResultResponse
)

router = APIRouter()


@router.post("", response_model=ExecutionResponse, status_code=201)
async def create_execution(data: ExecutionCreate, db: AsyncSession = Depends(get_db)):
    """创建执行任务"""
    scenario = await db.get(BusinessScenario, data.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    if not scenario.dsl:
        raise HTTPException(status_code=400, detail="场景 DSL 为空")

    task = ExecutionTask(
        scenario_id=data.scenario_id,
        environment_id=data.environment_id,
        trigger_type=data.trigger_type,
        status=TaskStatus.PENDING,
        config=data.config or {},
        execution_id=f"exec_{uuid_lib.uuid4().hex[:12]}",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    # TODO: 通过 Celery 异步执行
    # from app.celery_app import execute_scenario_task
    # execute_scenario_task.delay(str(task.id))

    return task


@router.get("", response_model=dict)
async def list_executions(
    scenario_id: UUID = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询执行任务列表"""
    query = select(ExecutionTask)
    count_query = select(func.count()).select_from(ExecutionTask)

    if scenario_id:
        query = query.where(ExecutionTask.scenario_id == scenario_id)
        count_query = count_query.where(ExecutionTask.scenario_id == scenario_id)
    if status:
        query = query.where(ExecutionTask.status == status)
        count_query = count_query.where(ExecutionTask.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(ExecutionTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [ExecutionResponse.model_validate(t) for t in result.scalars().all()]

    return {"total": total, "items": [i.model_dump() for i in items]}


@router.get("/{task_id}", response_model=ExecutionDetailResponse)
async def get_execution_detail(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """查询执行任务详情（含步骤结果）"""
    task = await db.get(ExecutionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="执行任务不存在")

    # 获取步骤结果
    results_query = (
        select(StepResult)
        .where(StepResult.task_id == task_id)
        .order_by(StepResult.sequence)
    )
    results = await db.execute(results_query)
    step_results = [StepResultResponse.model_validate(r) for r in results.scalars().all()]

    return ExecutionDetailResponse(
        task=ExecutionResponse.model_validate(task),
        step_results=step_results,
    )


@router.post("/{task_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(task_id: UUID, db: AsyncSession = Depends(get_db)):
    """取消执行任务"""
    task = await db.get(ExecutionTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="执行任务不存在")
    if task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
        raise HTTPException(status_code=400, detail="当前状态不允许取消")

    task.status = TaskStatus.CANCELLED
    task.finished_at = datetime.utcnow()
    await db.flush()
    await db.refresh(task)
    return task

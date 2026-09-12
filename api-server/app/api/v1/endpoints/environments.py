"""环境管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.database import get_db
from app.models.project import Project, Environment
from app.schemas.project import (
    EnvironmentCreate, EnvironmentUpdate, EnvironmentResponse, EnvironmentListResponse
)

router = APIRouter()


@router.post("/{project_id}/environments", response_model=EnvironmentResponse, status_code=201)
async def create_environment(
    project_id: UUID, data: EnvironmentCreate, db: AsyncSession = Depends(get_db)
):
    """创建环境"""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    env = Environment(
        project_id=project_id,
        name=data.name,
        env_type=data.env_type,
        base_url=data.base_url,
        headers=data.headers,
        cookies=data.cookies,
        proxy=data.proxy,
        timeout=data.timeout,
        variables=data.variables,
        secrets=data.secrets,
    )
    db.add(env)
    await db.flush()
    await db.refresh(env)
    return EnvironmentResponse.from_orm_model(env)


@router.get("/{project_id}/environments", response_model=EnvironmentListResponse)
async def list_environments(
    project_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询环境列表"""
    query = select(Environment).where(Environment.project_id == project_id)
    count_query = select(func.count()).select_from(Environment).where(Environment.project_id == project_id)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Environment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [EnvironmentResponse.from_orm_model(e) for e in result.scalars().all()]

    return EnvironmentListResponse(total=total, items=items)


@router.put("/environments/{env_id}", response_model=EnvironmentResponse)
async def update_environment(
    env_id: UUID, data: EnvironmentUpdate, db: AsyncSession = Depends(get_db)
):
    """更新环境"""
    env = await db.get(Environment, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(env, field, value)

    await db.flush()
    await db.refresh(env)
    return EnvironmentResponse.from_orm_model(env)


@router.delete("/environments/{env_id}", status_code=204)
async def delete_environment(env_id: UUID, db: AsyncSession = Depends(get_db)):
    """删除环境"""
    env = await db.get(Environment, env_id)
    if not env:
        raise HTTPException(status_code=404, detail="环境不存在")
    await db.delete(env)
    await db.flush()

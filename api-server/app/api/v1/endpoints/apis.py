"""接口资产管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from uuid import UUID

from app.database import get_db
from app.models.api_asset import ApiDefinition, ApiSample
from app.schemas.recording import (
    ApiDefinitionResponse, ApiDefinitionUpdate, ApiDefinitionListResponse
)

router = APIRouter()


@router.get("/projects/{project_id}/apis", response_model=ApiDefinitionListResponse)
async def list_apis(
    project_id: UUID,
    method: str = Query(None),
    risk_level: str = Query(None),
    lifecycle: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询项目接口资产列表"""
    query = select(ApiDefinition).where(ApiDefinition.project_id == project_id)
    count_query = select(func.count()).select_from(ApiDefinition).where(ApiDefinition.project_id == project_id)

    if method:
        query = query.where(ApiDefinition.method == method.upper())
        count_query = count_query.where(ApiDefinition.method == method.upper())
    if risk_level:
        query = query.where(ApiDefinition.risk_level == risk_level)
        count_query = count_query.where(ApiDefinition.risk_level == risk_level)
    if lifecycle:
        query = query.where(ApiDefinition.lifecycle == lifecycle)
        count_query = count_query.where(ApiDefinition.lifecycle == lifecycle)
    if search:
        pattern = f"%{search}%"
        query = query.where(
            (ApiDefinition.name.ilike(pattern)) | (ApiDefinition.normalized_path.ilike(pattern))
        )
        count_query = count_query.where(
            (ApiDefinition.name.ilike(pattern)) | (ApiDefinition.normalized_path.ilike(pattern))
        )

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(ApiDefinition.last_seen_at.desc().nullslast()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return ApiDefinitionListResponse(total=total, items=items)


@router.get("/apis/{api_id}", response_model=dict)
async def get_api_detail(api_id: UUID, db: AsyncSession = Depends(get_db)):
    """查询接口详情（含样本）"""
    api_def = await db.get(ApiDefinition, api_id)
    if not api_def:
        raise HTTPException(status_code=404, detail="接口不存在")

    # 获取样本
    samples_query = select(ApiSample).where(ApiSample.api_id == api_id).order_by(ApiSample.created_at.desc()).limit(20)
    samples_result = await db.execute(samples_query)
    samples = list(samples_result.scalars().all())

    return {
        "api": ApiDefinitionResponse.model_validate(api_def).model_dump(),
        "samples": [
            {
                "id": str(s.id),
                "status_code": s.status_code,
                "duration_ms": s.duration_ms,
                "request_summary": s.request_summary,
                "response_summary": s.response_summary,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in samples
        ],
    }


@router.patch("/apis/{api_id}", response_model=ApiDefinitionResponse)
async def update_api(
    api_id: UUID, data: ApiDefinitionUpdate, db: AsyncSession = Depends(get_db)
):
    """修改接口信息或标记"""
    api_def = await db.get(ApiDefinition, api_id)
    if not api_def:
        raise HTTPException(status_code=404, detail="接口不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(api_def, field, value)

    await db.flush()
    await db.refresh(api_def)
    return api_def

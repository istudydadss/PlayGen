"""场景管理 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from uuid import UUID
import yaml

from app.database import get_db
from app.models.scenario import BusinessScenario, TestStep
from app.models.recording import NetworkRecord, RecordingSession
from app.models.project import Project
from app.schemas.recording import (
    ScenarioCreate, ScenarioFromRecording, ScenarioResponse, ScenarioListResponse,
    DslSaveRequest, DslResponse, CodeGenerateRequest, CodeGenerateResponse,
)

router = APIRouter()


@router.post("/from-recording/{recording_id}", response_model=ScenarioResponse, status_code=201)
async def create_scenario_from_recording(
    recording_id: UUID,
    data: ScenarioFromRecording,
    db: AsyncSession = Depends(get_db),
):
    """从录制创建场景"""
    session = await db.get(RecordingSession, recording_id)
    if not session:
        raise HTTPException(status_code=404, detail="录制会话不存在")

    # 创建场景
    scenario = BusinessScenario(
        project_id=data.project_id,
        name=data.name,
        description=data.description,
        risk_level=data.risk_level,
        source_recording_id=recording_id,
    )
    db.add(scenario)
    await db.flush()

    # 如果指定了接口 ID，创建步骤
    if data.network_record_ids:
        for idx, record_id in enumerate(data.network_record_ids, 1):
            record = await db.get(NetworkRecord, record_id)
            if record:
                step = TestStep(
                    scenario_id=scenario.id,
                    step_id=f"step_{idx}",
                    name=f"步骤 {idx}: {record.method} {record.url[:80]}",
                    sequence=idx,
                    request_config={
                        "method": record.method,
                        "path": record.url,
                        "headers": record.request_headers,
                        "query": record.query_params,
                        "body": record.request_body,
                    },
                )
                db.add(step)

    await db.flush()

    # 生成初始 DSL
    await _build_dsl(scenario.id, db)
    await db.refresh(scenario)

    return scenario


@router.post("", response_model=ScenarioResponse, status_code=201)
async def create_scenario(data: ScenarioCreate, db: AsyncSession = Depends(get_db)):
    """创建空场景"""
    project = await db.get(Project, data.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    scenario = BusinessScenario(
        project_id=data.project_id,
        name=data.name,
        description=data.description,
        risk_level=data.risk_level,
        tags=data.tags,
    )
    db.add(scenario)
    await db.flush()
    await db.refresh(scenario)
    return scenario


@router.get("", response_model=ScenarioListResponse)
async def list_scenarios(
    project_id: UUID = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询场景列表"""
    query = select(BusinessScenario)
    count_query = select(func.count()).select_from(BusinessScenario)

    if project_id:
        query = query.where(BusinessScenario.project_id == project_id)
        count_query = count_query.where(BusinessScenario.project_id == project_id)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(BusinessScenario.updated_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return ScenarioListResponse(total=total, items=items)


@router.get("/{scenario_id}", response_model=ScenarioResponse)
async def get_scenario(scenario_id: UUID, db: AsyncSession = Depends(get_db)):
    """查询场景详情"""
    scenario = await db.get(BusinessScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scenario


@router.put("/{scenario_id}/dsl", response_model=DslResponse)
async def save_dsl(
    scenario_id: UUID, data: DslSaveRequest, db: AsyncSession = Depends(get_db)
):
    """保存场景 DSL"""
    scenario = await db.get(BusinessScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")

    # 验证 YAML 格式
    try:
        parsed = yaml.safe_load(data.dsl)
        if not isinstance(parsed, dict):
            raise ValueError("DSL 必须是 YAML 对象")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DSL 格式错误: {str(e)}")

    scenario.dsl = data.dsl
    scenario.dsl_version += 1
    await db.flush()
    await db.refresh(scenario)

    return DslResponse(
        id=scenario.id,
        name=scenario.name,
        dsl=scenario.dsl,
        dsl_version=scenario.dsl_version,
    )


@router.get("/{scenario_id}/dsl", response_model=DslResponse)
async def get_dsl(scenario_id: UUID, db: AsyncSession = Depends(get_db)):
    """获取场景 DSL"""
    scenario = await db.get(BusinessScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    if not scenario.dsl:
        # 自动生成 DSL
        await _build_dsl(scenario.id, db)
        await db.refresh(scenario)

    return DslResponse(
        id=scenario.id,
        name=scenario.name,
        dsl=scenario.dsl or "",
        dsl_version=scenario.dsl_version,
    )


@router.post("/{scenario_id}/generate-code", response_model=CodeGenerateResponse)
async def generate_code(
    scenario_id: UUID,
    data: CodeGenerateRequest = CodeGenerateRequest(),
    db: AsyncSession = Depends(get_db),
):
    """生成测试代码"""
    scenario = await db.get(BusinessScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="场景不存在")
    if not scenario.dsl:
        raise HTTPException(status_code=400, detail="场景 DSL 为空，请先生成或保存 DSL")

    # TODO: 调用代码生成器
    # from generator.code_generator import CodeGenerator
    # generator = CodeGenerator()
    # code = generator.generate(scenario.dsl, data.language, data.template)

    # 临时返回 DSL 内容作为占位
    return CodeGenerateResponse(
        code=f"# Generated from scenario: {scenario.name}\n# Language: {data.language}\n\n{scenario.dsl}",
        language=data.language,
        filename=f"test_{scenario.name.replace(' ', '_').lower()}.py",
    )


async def _build_dsl(scenario_id: UUID, db: AsyncSession):
    """从步骤构建 DSL"""
    scenario = await db.get(BusinessScenario, scenario_id)
    steps_query = select(TestStep).where(TestStep.scenario_id == scenario_id).order_by(TestStep.sequence)
    result = await db.execute(steps_query)
    steps = list(result.scalars().all())

    dsl = {
        "name": scenario.name,
        "risk_level": scenario.risk_level,
        "variables": {},
        "steps": [],
    }

    for step in steps:
        step_dsl = {
            "id": step.step_id,
            "name": step.name or step.step_id,
            "request": step.request_config or {},
        }
        if step.extract:
            step_dsl["extract"] = step.extract
        dsl["steps"].append(step_dsl)

    scenario.dsl = yaml.dump(dsl, allow_unicode=True, default_flow_style=False, sort_keys=False)

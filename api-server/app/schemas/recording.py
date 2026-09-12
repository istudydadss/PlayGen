"""Pydantic 模型 - 录制、接口资产、场景、执行"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from uuid import UUID


# ========== 录制会话 ==========

class RecordingCreate(BaseModel):
    project_id: UUID
    environment_id: Optional[UUID] = None
    name: Optional[str] = Field(None, max_length=200)
    browser: str = "chromium"
    start_url: Optional[str] = None
    reuse_storage_state: bool = False
    capture_trace: bool = False


class RecordingResponse(BaseModel):
    id: UUID
    project_id: UUID
    environment_id: Optional[UUID]
    name: Optional[str]
    status: str
    browser: str
    start_url: Optional[str]
    total_requests: int
    total_actions: int
    started_at: Optional[datetime]
    stopped_at: Optional[datetime]
    created_at: datetime
    error_message: Optional[str]

    model_config = {"from_attributes": True}


class RecordingListResponse(BaseModel):
    total: int
    items: list[RecordingResponse]


class TrafficRecordResponse(BaseModel):
    id: UUID
    url: str
    method: str
    resource_type: str
    status_code: Optional[int]
    duration_ms: Optional[float]
    page_url: Optional[str]
    is_business: Optional[bool]
    business_score: Optional[float]
    manual_tag: Optional[str]
    started_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TrafficDetailResponse(BaseModel):
    id: UUID
    url: str
    method: str
    resource_type: str
    protocol: Optional[str]
    request_headers: Optional[dict]
    query_params: Optional[dict]
    request_body: Optional[dict]
    request_body_raw: Optional[str]
    status_code: Optional[int]
    response_headers: Optional[dict]
    response_body: Optional[dict]
    response_body_raw: Optional[str]
    duration_ms: Optional[float]
    page_url: Optional[str]
    failure_reason: Optional[str]
    is_business: Optional[bool]
    business_score: Optional[float]
    manual_tag: Optional[str]
    started_at: Optional[datetime]
    response_at: Optional[datetime]

    model_config = {"from_attributes": True}


class TrafficListResponse(BaseModel):
    total: int
    items: list[TrafficRecordResponse]


# ========== 接口资产 ==========

class ApiDefinitionResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: Optional[str]
    method: str
    normalized_path: str
    fingerprint: str
    service: Optional[str]
    tags: Optional[list]
    risk_level: str
    lifecycle: str
    sample_count: int
    first_seen_at: Optional[datetime]
    last_seen_at: Optional[datetime]
    success_rate: Optional[float]
    p95_duration_ms: Optional[float]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApiDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    service: Optional[str] = None
    tags: Optional[list] = None
    risk_level: Optional[str] = None
    lifecycle: Optional[str] = None
    owner: Optional[str] = None
    manual_tag: Optional[str] = None


class ApiDefinitionListResponse(BaseModel):
    total: int
    items: list[ApiDefinitionResponse]


# ========== 业务场景 ==========

class ScenarioCreate(BaseModel):
    project_id: UUID
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    risk_level: str = "CONTROLLED"
    tags: Optional[list] = None


class ScenarioFromRecording(BaseModel):
    """从录制创建场景"""
    project_id: UUID
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    risk_level: str = "CONTROLLED"
    network_record_ids: list[UUID] = Field(default_factory=list)


class ScenarioResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    description: Optional[str]
    risk_level: str
    dsl: Optional[str]
    dsl_version: int
    source_recording_id: Optional[UUID]
    tags: Optional[list]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScenarioListResponse(BaseModel):
    total: int
    items: list[ScenarioResponse]


class DslSaveRequest(BaseModel):
    dsl: str


class DslResponse(BaseModel):
    id: UUID
    name: str
    dsl: str
    dsl_version: int


# ========== 代码生成 ==========

class CodeGenerateRequest(BaseModel):
    language: str = "pytest"
    template: Optional[str] = None


class CodeGenerateResponse(BaseModel):
    code: str
    language: str
    filename: str


# ========== 执行 ==========

class ExecutionCreate(BaseModel):
    scenario_id: UUID
    environment_id: UUID
    trigger_type: str = "manual"
    config: Optional[dict] = None


class ExecutionResponse(BaseModel):
    id: UUID
    scenario_id: UUID
    environment_id: UUID
    trigger_type: str
    status: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    skipped_steps: int
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    total_duration_ms: Optional[float]
    error_message: Optional[str]
    failure_category: Optional[str]
    execution_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class StepResultResponse(BaseModel):
    id: UUID
    task_id: UUID
    step_id: UUID
    step_name: Optional[str]
    sequence: int
    status: str
    actual_request: Optional[dict]
    actual_response: Optional[dict]
    extracted_variables: Optional[dict]
    assertion_results: Optional[list]
    duration_ms: Optional[float]
    error_message: Optional[str]
    failure_category: Optional[str]
    retry_count: int
    trace_id: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ExecutionDetailResponse(BaseModel):
    task: ExecutionResponse
    step_results: list[StepResultResponse]

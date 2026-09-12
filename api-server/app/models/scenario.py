"""SQLAlchemy 数据模型 - 业务场景、步骤、断言与执行"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Integer, Float, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


# ========== 枚举类型 ==========

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TriggerType(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    CI = "ci"
    WEBHOOK = "webhook"


class FailureCategory(str, enum.Enum):
    NETWORK = "network"
    AUTH = "auth"
    SCRIPT = "script"
    DATA = "data"
    BUSINESS = "business"
    ASSERTION = "assertion"
    PERFORMANCE = "performance"
    UNKNOWN = "unknown"


# ========== 业务场景表 ==========

class BusinessScenario(Base):
    __tablename__ = "business_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(20), default="CONTROLLED")

    # DSL 主存储（YAML 格式字符串）
    dsl: Mapped[str | None] = mapped_column(Text)
    dsl_version: Mapped[int] = mapped_column(Integer, default=1)

    # 来源
    source_recording_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recording_sessions.id"), nullable=True
    )

    # 标签
    tags: Mapped[list | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    project: Mapped["Project"] = relationship(back_populates="business_scenarios")
    steps: Mapped[list["TestStep"]] = relationship(back_populates="scenario", cascade="all, delete-orphan", order_by="TestStep.sequence")
    execution_tasks: Mapped[list["ExecutionTask"]] = relationship(back_populates="scenario", cascade="all, delete-orphan")


# ========== 测试步骤表 ==========

class TestStep(Base):
    __tablename__ = "test_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_definitions.id"), nullable=True
    )
    step_id: Mapped[str] = mapped_column(String(100), nullable=False)  # 步骤标识符
    name: Mapped[str | None] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # 请求配置
    request_config: Mapped[dict | None] = mapped_column(JSON)
    # {method, path, headers, query, body}

    # 变量提取
    extract: Mapped[dict | None] = mapped_column(JSON)
    # {"token": "$.data.accessToken", "order_id": "$.data.orderId"}

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    scenario: Mapped["BusinessScenario"] = relationship(back_populates="steps")
    assertions: Mapped[list["Assertion"]] = relationship(back_populates="step", cascade="all, delete-orphan")
    variable_relations: Mapped[list["VariableRelation"]] = relationship(
        back_populates="target_step", cascade="all, delete-orphan",
        foreign_keys="[VariableRelation.target_step_id]"
    )


# ========== 断言表 ==========

class Assertion(Base):
    __tablename__ = "assertions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path: Mapped[str] = mapped_column(String(500), nullable=False)  # JSONPath
    operator: Mapped[str] = mapped_column(String(50), nullable=False)  # equals, not_empty, contains, gt, lt, etc.
    expected: Mapped[str | None] = mapped_column(Text)  # 期望值
    description: Mapped[str | None] = mapped_column(String(500))

    # 来源标记
    source: Mapped[str | None] = mapped_column(String(50))  # auto, manual, ai
    confidence: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    step: Mapped["TestStep"] = relationship(back_populates="assertions")


# ========== 变量依赖关系表 ==========

class VariableRelation(Base):
    __tablename__ = "variable_relations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_steps.id", ondelete="CASCADE"), nullable=False
    )
    target_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_steps.id", ondelete="CASCADE"), nullable=False
    )

    source_json_path: Mapped[str] = mapped_column(String(500), nullable=False)
    target_location: Mapped[str] = mapped_column(String(500), nullable=False)  # header.Authorization, body.productId, etc.
    transform: Mapped[str | None] = mapped_column(String(500))  # "Bearer ${value}"
    variable_name: Mapped[str | None] = mapped_column(String(100))

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    evidence: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    target_step: Mapped["TestStep"] = relationship(
        back_populates="variable_relations",
        foreign_keys=[target_step_id]
    )


# ========== 执行任务表 ==========

class ExecutionTask(Base):
    __tablename__ = "execution_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id"), nullable=False
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        SAEnum(TriggerType), default=TriggerType.MANUAL
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, index=True
    )

    # 执行配置
    config: Mapped[dict | None] = mapped_column(JSON)
    # {concurrency, timeout, retry_count, retry_on_network_error, continue_on_failure}

    # 结果统计
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    passed_steps: Mapped[int] = mapped_column(Integer, default=0)
    failed_steps: Mapped[int] = mapped_column(Integer, default=0)
    skipped_steps: Mapped[int] = mapped_column(Integer, default=0)

    # 时序
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    total_duration_ms: Mapped[float | None] = mapped_column(Float)

    # 错误
    error_message: Mapped[str | None] = mapped_column(Text)
    failure_category: Mapped[str | None] = mapped_column(String(50))

    # 追踪
    execution_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    trace_id: Mapped[str | None] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    scenario: Mapped["BusinessScenario"] = relationship(back_populates="execution_tasks")
    step_results: Mapped[list["StepResult"]] = relationship(back_populates="task", cascade="all, delete-orphan")


# ========== 步骤执行结果表 ==========

class StepResult(Base):
    __tablename__ = "step_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("test_steps.id"), nullable=False
    )
    step_name: Mapped[str | None] = mapped_column(String(200))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING
    )

    # 请求/响应快照
    actual_request: Mapped[dict | None] = mapped_column(JSON)
    actual_response: Mapped[dict | None] = mapped_column(JSON)

    # 变量提取结果
    extracted_variables: Mapped[dict | None] = mapped_column(JSON)

    # 断言结果
    assertion_results: Mapped[list | None] = mapped_column(JSON)
    # [{"path": "$.code", "operator": "equals", "expected": 0, "actual": 0, "passed": true}]

    # 耗时
    duration_ms: Mapped[float | None] = mapped_column(Float)

    # 错误
    error_message: Mapped[str | None] = mapped_column(Text)
    failure_category: Mapped[str | None] = mapped_column(String(50))
    error_type: Mapped[str | None] = mapped_column(String(50))

    # 重试
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # 追踪
    trace_id: Mapped[str | None] = mapped_column(String(100))

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)

    # 关系
    task: Mapped["ExecutionTask"] = relationship(back_populates="step_results")


# ========== 调度配置表 ==========

class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id"), nullable=False
    )
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


# ========== 审计日志表 ==========

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor: Mapped[str | None] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[str | None] = mapped_column(String(50))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(50))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

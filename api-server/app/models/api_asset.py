"""SQLAlchemy 数据模型 - 接口资产"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Integer, Float, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


class RiskLevel(str, enum.Enum):
    SAFE = "SAFE"
    CONTROLLED = "CONTROLLED"
    DANGEROUS = "DANGEROUS"


class LifecycleStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    CONFIRMED = "confirmed"
    DEPRECATED = "deprecated"
    REMOVED = "removed"


class ApiDefinition(Base):
    """接口资产定义"""
    __tablename__ = "api_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 接口基本信息
    name: Mapped[str | None] = mapped_column(String(200))
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    normalized_path: Mapped[str] = mapped_column(String(500), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # 归属
    service: Mapped[str | None] = mapped_column(String(200))
    tags: Mapped[list | None] = mapped_column(JSON)

    # Schema
    request_schema: Mapped[dict | None] = mapped_column(JSON)
    response_schema: Mapped[dict | None] = mapped_column(JSON)
    schema_hash: Mapped[str | None] = mapped_column(String(64))

    # 元数据
    risk_level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel), default=RiskLevel.CONTROLLED
    )
    lifecycle: Mapped[LifecycleStatus] = mapped_column(
        SAEnum(LifecycleStatus), default=LifecycleStatus.DISCOVERED
    )
    owner: Mapped[str | None] = mapped_column(String(100))

    # 统计
    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    success_rate: Mapped[float | None] = mapped_column(Float)
    p95_duration_ms: Mapped[float | None] = mapped_column(Float)
    error_code_distribution: Mapped[dict | None] = mapped_column(JSON)

    # 归并
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_definitions.id"), nullable=True
    )
    merge_note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    project: Mapped["Project"] = relationship(back_populates="api_definitions")
    samples: Mapped[list["ApiSample"]] = relationship(back_populates="api_definition", cascade="all, delete-orphan")
    versions: Mapped[list["ApiVersion"]] = relationship(back_populates="api_definition", cascade="all, delete-orphan")


class ApiSample(Base):
    """接口样本 - 关联到原始流量记录"""
    __tablename__ = "api_samples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    api_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    network_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("network_records.id"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recording_sessions.id"), nullable=True
    )

    # 样本摘要
    request_summary: Mapped[dict | None] = mapped_column(JSON)
    response_summary: Mapped[dict | None] = mapped_column(JSON)
    schema_hash: Mapped[str | None] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    api_definition: Mapped["ApiDefinition"] = relationship(back_populates="samples")


class ApiVersion(Base):
    """接口版本 - Schema 变更记录"""
    __tablename__ = "api_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    api_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_schema: Mapped[dict | None] = mapped_column(JSON)
    response_schema: Mapped[dict | None] = mapped_column(JSON)
    schema_hash: Mapped[str | None] = mapped_column(String(64))
    change_type: Mapped[str | None] = mapped_column(String(50))  # compatible, breaking
    change_details: Mapped[dict | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    api_definition: Mapped["ApiDefinition"] = relationship(back_populates="versions")

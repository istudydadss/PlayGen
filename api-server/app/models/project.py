"""SQLAlchemy 数据模型 - 项目与环境"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Enum as SAEnum, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


# ========== 枚举类型 ==========

class ProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EnvironmentType(str, enum.Enum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


# ========== 项目表 ==========

class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus), default=ProjectStatus.ACTIVE, index=True
    )

    # 适配配置（JSON）
    config: Mapped[dict | None] = mapped_column(JSON, default=dict)
    # config 结构示例:
    # {
    #   "domains": {"include": ["api.mall.test"], "exclude": ["tracker.example.com"]},
    #   "filters": {
    #     "exclude_paths": ["/track", "/heartbeat", "/log"],
    #     "exclude_suffixes": [".js", ".css", ".png", ".jpg", ".gif", ".svg", ".woff", ".woff2"],
    #     "exclude_content_types": ["text/html", "image/*", "font/*"]
    #   },
    #   "business_rules": {
    #     "success_code_path": "$.code",
    #     "success_code_value": 0
    #   },
    #   "sensitive_fields": ["password", "accessToken", "phone"],
    #   "dynamic_fields": ["timestamp", "nonce", "orderNo"],
    #   "scoring": {
    #     "json_response": 20,
    #     "write_method": 15,
    #     "business_keyword": 20,
    #     "temporal_proximity": 15,
    #     "success_structure": 15,
    #     "static_resource": -100,
    #     "known_tracker": -80,
    #     "heartbeat": -50
    #   },
    #   "code_language": "pytest"
    # }

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    environments: Mapped[list["Environment"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    recording_sessions: Mapped[list["RecordingSession"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    api_definitions: Mapped[list["ApiDefinition"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    business_scenarios: Mapped[list["BusinessScenario"]] = relationship(back_populates="project", cascade="all, delete-orphan")


# ========== 环境表 ==========

class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    env_type: Mapped[EnvironmentType] = mapped_column(
        SAEnum(EnvironmentType), default=EnvironmentType.TEST
    )
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # 公共配置
    headers: Mapped[dict | None] = mapped_column(JSON, default=dict)
    cookies: Mapped[dict | None] = mapped_column(JSON, default=dict)
    proxy: Mapped[str | None] = mapped_column(String(500))
    timeout: Mapped[int] = mapped_column(Integer, default=30000)

    # 变量（普通变量与密钥分开）
    variables: Mapped[dict | None] = mapped_column(JSON, default=dict)
    secrets: Mapped[dict | None] = mapped_column(JSON, default=dict)  # 加密存储

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # 关系
    project: Mapped["Project"] = relationship(back_populates="environments")

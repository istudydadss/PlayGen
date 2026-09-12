"""SQLAlchemy 数据模型 - 录制会话与网络流量"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, JSON, Integer, Float, Enum as SAEnum, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.database import Base


# ========== 枚举类型 ==========

class RecordingStatus(str, enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPED = "stopped"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ERROR = "error"


class ResourceType(str, enum.Enum):
    XHR = "xhr"
    FETCH = "fetch"
    DOCUMENT = "document"
    SCRIPT = "script"
    STYLESHEET = "stylesheet"
    IMAGE = "image"
    FONT = "font"
    MEDIA = "media"
    WEBSOCKET = "websocket"
    OTHER = "other"


# ========== 录制会话表 ==========

class RecordingSession(Base):
    __tablename__ = "recording_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("environments.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[RecordingStatus] = mapped_column(
        SAEnum(RecordingStatus), default=RecordingStatus.IDLE, index=True
    )
    browser: Mapped[str] = mapped_column(String(50), default="chromium")
    start_url: Mapped[str | None] = mapped_column(String(1000))
    storage_state_path: Mapped[str | None] = mapped_column(String(500))
    capture_trace: Mapped[bool] = mapped_column(Boolean, default=False)

    # 统计信息
    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    total_actions: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text)

    # 关系
    project: Mapped["Project"] = relationship(back_populates="recording_sessions")
    page_actions: Mapped[list["PageAction"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    network_records: Mapped[list["NetworkRecord"]] = relationship(back_populates="session", cascade="all, delete-orphan")


# ========== 页面操作表 ==========

class PageAction(Base):
    __tablename__ = "page_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # click, input, navigate, submit, etc.
    selector: Mapped[str | None] = mapped_column(String(500))  # CSS selector
    page_url: Mapped[str | None] = mapped_column(String(1000))
    frame_url: Mapped[str | None] = mapped_column(String(1000))
    input_value: Mapped[str | None] = mapped_column(Text)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)  # 额外信息

    # 关系
    session: Mapped["RecordingSession"] = relationship(back_populates="page_actions")


# ========== 网络流量记录表 ==========

class NetworkRecord(Base):
    __tablename__ = "network_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recording_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 请求信息
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), default="other")
    protocol: Mapped[str | None] = mapped_column(String(20))

    # 请求详情
    request_headers: Mapped[dict | None] = mapped_column(JSON)
    query_params: Mapped[dict | None] = mapped_column(JSON)
    request_body: Mapped[dict | None] = mapped_column(JSON)
    request_body_raw: Mapped[str | None] = mapped_column(Text)
    request_cookies: Mapped[dict | None] = mapped_column(JSON)
    post_data: Mapped[str | None] = mapped_column(Text)

    # 响应信息
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_headers: Mapped[dict | None] = mapped_column(JSON)
    response_body: Mapped[dict | None] = mapped_column(JSON)
    response_body_raw: Mapped[str | None] = mapped_column(Text)
    response_body_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    response_body_hash: Mapped[str | None] = mapped_column(String(64))

    # 时序
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    response_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_ms: Mapped[float | None] = mapped_column(Float)

    # 关联信息
    page_url: Mapped[str | None] = mapped_column(String(1000))
    frame_url: Mapped[str | None] = mapped_column(String(1000))
    initiator_type: Mapped[str | None] = mapped_column(String(50))
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("page_actions.id"), nullable=True
    )

    # 重定向与错误
    redirect_chain: Mapped[list | None] = mapped_column(JSON)
    failure_reason: Mapped[str | None] = mapped_column(Text)

    # 分析标记
    is_business: Mapped[bool | None] = mapped_column(Boolean, default=None, index=True)
    business_score: Mapped[float | None] = mapped_column(Float, default=None)
    manual_tag: Mapped[str | None] = mapped_column(String(50))  # keep, ignore, merge

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # 关系
    session: Mapped["RecordingSession"] = relationship(back_populates="network_records")

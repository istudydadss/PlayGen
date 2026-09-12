"""采集器数据模型"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from enum import Enum


class ResourceType(str, Enum):
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


class CapturedRequest(BaseModel):
    """采集的请求模型"""
    url: str
    method: str
    resource_type: str = "other"
    protocol: Optional[str] = None
    headers: dict = Field(default_factory=dict)
    query_params: dict = Field(default_factory=dict)
    body: Optional[Any] = None
    body_raw: Optional[str] = None
    cookies: dict = Field(default_factory=dict)
    post_data: Optional[str] = None


class CapturedResponse(BaseModel):
    """采集的响应模型"""
    status: int
    headers: dict = Field(default_factory=dict)
    body: Optional[Any] = None
    body_raw: Optional[str] = None
    body_truncated: bool = False
    body_hash: Optional[str] = None
    content_type: Optional[str] = None


class NetworkEvent(BaseModel):
    """完整网络事件（请求 + 响应）"""
    request_id: str
    session_id: str
    page_url: Optional[str] = None
    frame_url: Optional[str] = None
    initiator_type: Optional[str] = None

    request: CapturedRequest
    response: Optional[CapturedResponse] = None

    started_at: datetime
    response_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    failure_reason: Optional[str] = None
    redirect_chain: list = Field(default_factory=list)


class PageOperation(BaseModel):
    """页面操作记录"""
    operation_type: str  # click, input, navigate, submit, scroll, etc.
    selector: Optional[str] = None
    page_url: Optional[str] = None
    frame_url: Optional[str] = None
    input_value: Optional[str] = None
    timestamp: datetime
    metadata: dict = Field(default_factory=dict)


class RecordingConfig(BaseModel):
    """录制配置"""
    session_id: str
    project_id: str
    environment_id: Optional[str] = None
    browser: str = "chromium"
    headless: bool = False
    start_url: Optional[str] = None
    storage_state_path: Optional[str] = None
    capture_trace: bool = False
    capture_screenshots: bool = False
    capture_video: bool = False
    timeout: int = 30000
    viewport: dict = Field(default_factory=lambda: {"width": 1280, "height": 720})
    max_response_body_size: int = 1_048_576  # 1MB

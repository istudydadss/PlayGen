"""Pydantic 模型 - 项目与环境"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from uuid import UUID


# ========== 项目 ==========

class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    config: Optional[dict] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    config: Optional[dict] = None
    status: Optional[str] = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    status: str
    config: Optional[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    total: int
    items: list[ProjectResponse]


# ========== 环境 ==========

class EnvironmentCreate(BaseModel):
    name: str = Field(..., max_length=100)
    env_type: str = Field(default="test")
    base_url: str = Field(..., max_length=500)
    headers: Optional[dict] = Field(default_factory=dict)
    cookies: Optional[dict] = Field(default_factory=dict)
    proxy: Optional[str] = None
    timeout: int = 30000
    variables: Optional[dict] = Field(default_factory=dict)
    secrets: Optional[dict] = Field(default_factory=dict)


class EnvironmentUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    env_type: Optional[str] = None
    base_url: Optional[str] = Field(None, max_length=500)
    headers: Optional[dict] = None
    cookies: Optional[dict] = None
    proxy: Optional[str] = None
    timeout: Optional[int] = None
    variables: Optional[dict] = None
    secrets: Optional[dict] = None


class EnvironmentResponse(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    env_type: str
    base_url: str
    headers: Optional[dict]
    cookies: Optional[dict]
    proxy: Optional[str]
    timeout: int
    variables: Optional[dict]
    # secrets 不回显明文
    has_secrets: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_model(cls, env):
        data = {
            "id": env.id,
            "project_id": env.project_id,
            "name": env.name,
            "env_type": env.env_type,
            "base_url": env.base_url,
            "headers": env.headers,
            "cookies": env.cookies,
            "proxy": env.proxy,
            "timeout": env.timeout,
            "variables": env.variables,
            "has_secrets": bool(env.secrets),
            "created_at": env.created_at,
            "updated_at": env.updated_at,
        }
        return cls(**data)


class EnvironmentListResponse(BaseModel):
    total: int
    items: list[EnvironmentResponse]

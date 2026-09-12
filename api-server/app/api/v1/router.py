"""API v1 路由总入口"""
from fastapi import APIRouter

from app.api.v1.endpoints import projects, environments, recordings, apis, scenarios, executions

api_router = APIRouter()

api_router.include_router(projects.router, prefix="/projects", tags=["项目管理"])
api_router.include_router(environments.router, prefix="/projects", tags=["环境管理"])
api_router.include_router(recordings.router, prefix="/recordings", tags=["录制管理"])
api_router.include_router(apis.router, tags=["接口资产"])
api_router.include_router(scenarios.router, prefix="/scenarios", tags=["场景管理"])
api_router.include_router(executions.router, prefix="/executions", tags=["执行管理"])

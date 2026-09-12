"""PlayGen - FastAPI 应用入口"""
import sys
import asyncio

# Windows 上必须使用 ProactorEventLoop 以支持子进程（Playwright 需要）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import get_settings
from app.database import init_db

# 确保所有模型被导入（Alembic 需要）
from app.models import *  # noqa: F401, F403

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("PlayGen 启动中...")
    await init_db()
    logger.info("数据库初始化完成")
    yield
    logger.info("PlayGen 关闭中...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Playwright 业务接口采集与用例生成平台",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册路由
from app.api.v1.router import api_router

app.include_router(api_router, prefix=settings.API_PREFIX)


# ========== WebSocket 端点 ==========

@app.websocket("/ws/recording/{session_id}")
async def recording_websocket(websocket: WebSocket, session_id: str):
    """录制实时流量推送 WebSocket"""
    from app.services.websocket_manager import ws_manager
    await ws_manager.connect(websocket, session_id)
    try:
        while True:
            # 保持连接，接收客户端心跳或指令
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}

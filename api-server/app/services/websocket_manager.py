"""WebSocket 连接管理器"""
import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # session_id -> list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        """接受并注册 WebSocket 连接"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"WebSocket 已连接: session={session_id}")

    def disconnect(self, websocket: WebSocket, session_id: str):
        """移除 WebSocket 连接"""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"WebSocket 已断开: session={session_id}")

    async def broadcast_to_session(self, session_id: str, message: dict):
        """向指定录制会话的所有连接广播消息"""
        if session_id not in self.active_connections:
            return

        connections = self.active_connections[session_id]
        dead_connections = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"WebSocket 广播失败: {e}")
                dead_connections.append(connection)

        # 清理失效连接
        for conn in dead_connections:
            self.disconnect(conn, session_id)


# 全局单例
ws_manager = ConnectionManager()

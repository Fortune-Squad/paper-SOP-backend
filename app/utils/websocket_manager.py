"""
WebSocket 连接管理器
"""
import logging
from typing import Dict, Set
from fastapi import WebSocket
import json

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        # 所有活跃的连接
        self.active_connections: Set[WebSocket] = set()
        # 按项目ID分组的连接
        self.project_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, project_id: str = None):
        """接受新的WebSocket连接"""
        await websocket.accept()
        self.active_connections.add(websocket)

        if project_id:
            if project_id not in self.project_connections:
                self.project_connections[project_id] = set()
            self.project_connections[project_id].add(websocket)

        logger.info(f"WebSocket connected. Project: {project_id}, Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, project_id: str = None):
        """断开WebSocket连接"""
        self.active_connections.discard(websocket)

        if project_id and project_id in self.project_connections:
            self.project_connections[project_id].discard(websocket)
            if not self.project_connections[project_id]:
                del self.project_connections[project_id]

        logger.info(f"WebSocket disconnected. Project: {project_id}, Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """发送消息给特定连接"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

    async def broadcast(self, message: dict):
        """广播消息给所有连接"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")
                disconnected.add(connection)

        # 清理断开的连接
        for connection in disconnected:
            self.active_connections.discard(connection)

    async def broadcast_to_project(self, project_id: str, message: dict):
        """广播消息给特定项目的所有连接"""
        if project_id not in self.project_connections:
            logger.warning(f"No connections for project: {project_id}")
            return

        disconnected = set()
        for connection in self.project_connections[project_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to project {project_id}: {e}")
                disconnected.add(connection)

        # 清理断开的连接
        for connection in disconnected:
            self.project_connections[project_id].discard(connection)
            self.active_connections.discard(connection)

    async def send_step_progress(self, project_id: str, step_id: str, progress: float, message: str):
        """发送步骤进度更新"""
        await self.broadcast_to_project(project_id, {
            "type": "step_progress",
            "data": {
                "project_id": project_id,
                "step_id": step_id,
                "progress": progress,
                "message": message
            }
        })

    async def send_step_complete(self, project_id: str, step_id: str, success: bool, message: str = None):
        """发送步骤完成消息"""
        await self.broadcast_to_project(project_id, {
            "type": "step_complete",
            "data": {
                "project_id": project_id,
                "step_id": step_id,
                "success": success,
                "message": message
            }
        })

    async def send_ai_content(self, project_id: str, step_id: str, content: str, is_complete: bool = False):
        """发送AI生成的内容"""
        await self.broadcast_to_project(project_id, {
            "type": "ai_content",
            "data": {
                "project_id": project_id,
                "step_id": step_id,
                "content": content,
                "is_complete": is_complete
            }
        })

    async def send_gate_result(self, project_id: str, gate_name: str, verdict: str, details: dict):
        """发送Gate检查结果"""
        await self.broadcast_to_project(project_id, {
            "type": "gate_result",
            "data": {
                "project_id": project_id,
                "gate_name": gate_name,
                "verdict": verdict,
                "details": details
            }
        })


# 全局连接管理器实例
manager = ConnectionManager()

"""
WebSocket API 路由
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import logging

from app.utils.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/projects/{project_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: str
):
    """
    WebSocket端点 - 用于实时推送项目更新

    连接到特定项目的WebSocket，接收实时更新：
    - 步骤执行进度
    - AI生成内容
    - Gate检查结果
    - 步骤完成通知
    """
    await manager.connect(websocket, project_id)

    try:
        # 发送连接成功消息
        await manager.send_personal_message(
            {
                "type": "connected",
                "data": {
                    "project_id": project_id,
                    "message": f"Connected to project {project_id}"
                }
            },
            websocket
        )

        # 保持连接
        while True:
            # 接收客户端消息（心跳等）
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")

            # 可以在这里处理客户端发来的消息
            # 目前只是echo back
            await manager.send_personal_message(
                {
                    "type": "echo",
                    "data": {"message": data}
                },
                websocket
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)
        logger.info(f"Client disconnected from project {project_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, project_id)


@router.websocket("/global")
async def websocket_global(websocket: WebSocket):
    """
    全局WebSocket端点 - 接收所有项目的更新
    """
    await manager.connect(websocket)

    try:
        await manager.send_personal_message(
            {
                "type": "connected",
                "data": {"message": "Connected to global channel"}
            },
            websocket
        )

        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from global client: {data}")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Global client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

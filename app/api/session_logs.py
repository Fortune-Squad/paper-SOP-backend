"""
Session Log API Endpoints
v1.2 DevSpec §5.8 - 三时机写入 (Plan / Decisions / Wrap-up)

GET  /api/projects/{id}/sessions                          — 列出所有 sessions
GET  /api/projects/{id}/sessions/{session_id}             — 获取单个 session
POST /api/projects/{id}/sessions                          — 创建新 session (Phase 1: Plan)
POST /api/projects/{id}/sessions/{session_id}/decisions   — 添加决策记录 (Phase 2)
POST /api/projects/{id}/sessions/{session_id}/wrapup      — 写入 wrap-up (Phase 3)
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from pathlib import Path

from app.config import settings
from app.services.session_logger import SessionLogger
from app.services.project_manager import ProjectManager
from app.middleware.auth import get_current_active_user
from app.db.models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["session-logs"])

project_manager = ProjectManager()


def _get_project_path(project_id: str) -> Path:
    return Path(settings.projects_path) / project_id


async def _check_project_access(project_id: str, current_user: DBUser):
    """检查项目访问权限"""
    project = await project_manager._load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    is_admin = current_user.role == "admin"
    if not project_manager.check_project_access(project, str(current_user.id), is_admin):
        raise HTTPException(status_code=403, detail="You don't have permission to access this project")


# --- Request/Response models ---

class CreateSessionBody(BaseModel):
    goal: str = Field(..., description="Session 目标")
    approach: str = Field(..., description="采用的方案")
    rejected_alternatives: List[str] = Field(default_factory=list)
    token_estimate: Optional[int] = None

class DecisionBody(BaseModel):
    decision: str = Field(..., description="决策描述 (1-3 行)")

class WrapUpBody(BaseModel):
    completed: str = Field(..., description="完成了什么")
    remaining: str = Field(..., description="遗留问题")
    next_steps: str = Field(..., description="下一步")
    memory_updates: List[str] = Field(default_factory=list)

# --- Endpoints ---

@router.get("/projects/{project_id}/sessions")
async def list_sessions(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """列出所有 session logs"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        sl = SessionLogger(str(project_path))
        sessions = sl.list_sessions()

        return {"project_id": project_id, "sessions": sessions}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/sessions/{session_id}")
async def get_session(
    project_id: str,
    session_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取单个 session log 完整内容"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        sl = SessionLogger(str(project_path))
        content = sl.get_session_content(session_id)

        if content is None:
            raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

        return {"session_id": session_id, "content": content}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/sessions")
async def create_session(
    project_id: str,
    body: CreateSessionBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """Phase 1: Plan — 创建新 session log"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        sl = SessionLogger(str(project_path))
        session_id = sl.create_session(
            goal=body.goal,
            approach=body.approach,
            rejected_alternatives=body.rejected_alternatives,
            token_estimate=body.token_estimate,
        )

        return {"session_id": session_id, "status": "created"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/sessions/{session_id}/decisions")
async def add_decision(
    project_id: str,
    session_id: str,
    body: DecisionBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """Phase 2: Decisions — 增量写入决策记录"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        sl = SessionLogger(str(project_path))
        sl.log_decision(session_id, body.decision)

        return {"session_id": session_id, "status": "decision_logged"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to log decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/sessions/{session_id}/wrapup")
async def wrap_up_session(
    project_id: str,
    session_id: str,
    body: WrapUpBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """Phase 3: Wrap-up — 写入 session 总结"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        sl = SessionLogger(str(project_path))
        sl.wrap_up(
            session_id=session_id,
            completed=body.completed,
            remaining=body.remaining,
            next_steps=body.next_steps,
            memory_updates=body.memory_updates,
        )

        return {"session_id": session_id, "status": "wrapped_up"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to wrap up session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

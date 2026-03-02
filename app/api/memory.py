"""
Memory API Endpoints
v1.2 DevSpec §5.7 - MEMORY.md CRUD

GET    /api/projects/{id}/memory           — 获取 MEMORY.md 内容
POST   /api/projects/{id}/memory/learn     — 添加 [LEARN:tag]
DELETE /api/projects/{id}/memory/learn/{i}  — 删除条目
POST   /api/projects/{id}/memory/facts     — 添加 Key Fact
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from pathlib import Path

from app.config import settings
from app.services.memory_store import MemoryStore, LEARN_DOMAINS
from app.services.project_manager import ProjectManager
from app.middleware.auth import get_current_active_user
from app.db.models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["memory"])

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

class LearnEntryBody(BaseModel):
    domain: str = Field(..., description=f"领域标签: {', '.join(LEARN_DOMAINS)}")
    lesson: str = Field(..., max_length=100, description="教训内容 (<= 100 chars)")
    source: str = Field(default="human", description="来源: gate_failure/escalation/human/conflict")

class KeyFactBody(BaseModel):
    fact: str = Field(..., description="Key Fact 内容")

class FilterBody(BaseModel):
    tags: List[str] = Field(..., description="要过滤的领域标签列表")

# --- Endpoints ---

@router.get("/projects/{project_id}/memory")
async def get_memory(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取 MEMORY.md 完整内容"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        store = MemoryStore(str(project_path))
        data = store.load()

        return {
            "project_id": project_id,
            "key_facts": data.key_facts,
            "corrections": [e.model_dump() for e in data.corrections],
            "token_count": store.get_token_count(),
            "within_budget": store.is_within_budget(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/memory/learn")
async def add_learn_entry(
    project_id: str,
    body: LearnEntryBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """添加 [LEARN:tag] 条目"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        if body.domain not in LEARN_DOMAINS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid domain '{body.domain}'. Valid: {LEARN_DOMAINS}"
            )

        store = MemoryStore(str(project_path))
        store.add_learn_entry(domain=body.domain, lesson=body.lesson, source=body.source)

        return {
            "success": True,
            "domain": body.domain,
            "lesson": body.lesson,
            "token_count": store.get_token_count(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add learn entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}/memory/learn/{index}")
async def delete_learn_entry(
    project_id: str,
    index: int,
    current_user: DBUser = Depends(get_current_active_user)
):
    """删除指定索引的 [LEARN:tag] 条目"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        store = MemoryStore(str(project_path))
        removed = store.remove_learn_entry(index)

        if not removed:
            raise HTTPException(status_code=404, detail=f"Learn entry at index {index} not found")

        return {"success": True, "removed_index": index}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete learn entry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/memory/facts")
async def add_key_fact(
    project_id: str,
    body: KeyFactBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """添加 Key Fact"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        store = MemoryStore(str(project_path))
        store.add_key_fact(body.fact)

        return {
            "success": True,
            "fact": body.fact,
            "token_count": store.get_token_count(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add key fact: {e}")
        raise HTTPException(status_code=500, detail=str(e))

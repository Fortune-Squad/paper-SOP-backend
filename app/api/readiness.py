"""
Readiness Assessment (RA) API Endpoints
v1.2 DevSpec §5.9, §9.5

POST /api/projects/{id}/ra/{wp_id}/request  — 生成 RA 请求
POST /api/projects/{id}/ra/{wp_id}/result   — 提交 RA 结果
POST /api/projects/{id}/ra/{wp_id}/override — 人类 override BLOCK
GET  /api/projects/{id}/ra/status           — 获取所有 WP 的 RA 状态
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from pathlib import Path

from app.config import settings
from app.services.readiness_assessor import ReadinessAssessor, RAResult, RAVerdict
from app.services.memory_store import MemoryStore
from app.services.snapshot_generator import SnapshotGenerator
from app.services.project_manager import ProjectManager
from app.middleware.auth import get_current_active_user
from app.db.models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["readiness-assessment"])

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

class RARequestBody(BaseModel):
    passed_criteria: str = Field(..., description="通过的 gate 标准")
    artifacts_summary: str = Field(..., description="Artifacts 摘要")

class RAResultBody(BaseModel):
    raw_response: str = Field(..., description="ChatGPT 原始响应文本")

class RAOverrideBody(BaseModel):
    reason: str = Field(..., description="Override 原因")
    original_verdict: str = Field(default="BLOCK", description="原始判定")


# --- Endpoints ---

@router.post("/projects/{project_id}/ra/{wp_id}/request")
async def request_ra(
    project_id: str,
    wp_id: str,
    body: RARequestBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """生成 RA prompt 并返回（供前端复制到 ChatGPT）"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        ra = ReadinessAssessor(str(project_path))
        memory = MemoryStore(str(project_path))
        snapshot = SnapshotGenerator(str(project_path))

        agents_content = snapshot.get_agents_md_content() or "(AGENTS.md not initialized)"
        memory_content = memory.get_injection_content() or "(No memory entries)"

        prompt = ra.generate_ra_prompt(
            wp_id=wp_id,
            agents_md_content=agents_content,
            memory_md_content=memory_content,
            passed_criteria=body.passed_criteria,
            artifacts_summary=body.artifacts_summary,
        )

        logger.info(f"Generated RA prompt for {project_id}/{wp_id}")
        return {"wp_id": wp_id, "prompt": prompt, "status": "prompt_generated"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate RA request: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/ra/{wp_id}/result")
async def submit_ra_result(
    project_id: str,
    wp_id: str,
    body: RAResultBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """提交 ChatGPT 返回的 RA 结果"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        ra = ReadinessAssessor(str(project_path))
        result = ra.parse_result(body.raw_response)
        ra.save_result(wp_id, result)

        logger.info(f"Saved RA result for {project_id}/{wp_id}: {result.verdict.value}")
        return {
            "wp_id": wp_id,
            "verdict": result.verdict.value,
            "reasoning": result.reasoning,
            "missing_pieces": result.missing_pieces,
            "polish_suggestions": result.polish_suggestions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to submit RA result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/ra/{wp_id}/override")
async def override_ra(
    project_id: str,
    wp_id: str,
    body: RAOverrideBody,
    current_user: DBUser = Depends(get_current_active_user)
):
    """人类 override BLOCK 判定"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        ra = ReadinessAssessor(str(project_path))

        original = RAVerdict.BLOCK
        try:
            original = RAVerdict(body.original_verdict.upper())
        except ValueError:
            pass

        result = ra.create_override(wp_id, original, body.reason)

        logger.info(f"RA override for {project_id}/{wp_id}: {body.original_verdict} -> ADVANCE")
        return {
            "wp_id": wp_id,
            "verdict": result.verdict.value,
            "override_reason": body.reason,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to override RA: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/ra/status")
async def get_ra_status(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取所有 WP 的 RA 状态"""
    try:
        await _check_project_access(project_id, current_user)

        project_path = _get_project_path(project_id)
        if not project_path.exists():
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        ra = ReadinessAssessor(str(project_path))
        status = ra.get_ra_status()

        return {"project_id": project_id, "wp_statuses": status}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get RA status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

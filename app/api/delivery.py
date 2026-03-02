"""
Delivery API 路由
Step 4 交付流水线的 API 端点
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any
import logging

from app.services.state_store import StateStore, StateStoreError
from app.services.project_manager import ProjectManager
from app.middleware.auth import get_current_active_user
from app.db.models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/delivery", tags=["delivery"])

project_manager = ProjectManager()
state_store = StateStore()


async def _check_project_access(project_id: str, current_user: DBUser):
    """检查项目访问权限"""
    project = await project_manager._load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    is_admin = current_user.role == "admin"
    if not project_manager.check_project_access(project, str(current_user.id), is_admin):
        raise HTTPException(status_code=403, detail="You don't have permission to access this project")


@router.get("/manifest")
async def get_delivery_manifest(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取交付清单"""
    try:
        await _check_project_access(project_id, current_user)
        from app.utils.file_manager import FileManager
        from app.models.document import DocumentType
        fm = FileManager()
        doc = await fm.load_document(project_id, DocumentType.DELIVERY_MANIFEST)
        if not doc:
            raise HTTPException(status_code=404, detail="Delivery manifest not found")
        return {"content": doc.content, "status": doc.metadata.status.value}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_delivery_status(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取交付状态"""
    try:
        await _check_project_access(project_id, current_user)
        # 从 state.json 获取 delivery state
        if state_store.exists(project_id):
            state = state_store.load(project_id)
            return {
                "delivery_status": state.delivery_state.status.value,
                "profile": state.delivery_state.profile.value,
                "all_wps_frozen": state.all_wps_frozen(),
                "manifest_items": len(state.delivery_state.manifest),
            }
        else:
            return {
                "delivery_status": "not_started",
                "profile": "external_assembly_kit",
                "all_wps_frozen": False,
                "manifest_items": 0,
            }
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/package")
async def trigger_packaging(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """触发打包（执行 step_4_package）"""
    try:
        await _check_project_access(project_id, current_user)
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project = await project_manager.execute_step(project, "step_4_package")
        return {"success": True, "message": "Packaging completed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

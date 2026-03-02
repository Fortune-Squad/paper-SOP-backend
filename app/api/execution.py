"""
Execution API 路由
Step 3 WP 执行引擎的 API 端点
"""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Dict, Any
import logging

from app.services.wp_engine import WPExecutionEngine
from app.services.state_store import StateStore, StateStoreError
from app.services.project_manager import ProjectManager
from app.middleware.auth import get_current_active_user
from app.db.models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/execution", tags=["execution"])

state_store = StateStore()
project_manager = ProjectManager()


async def _check_project_access(project_id: str, current_user: DBUser):
    """检查项目访问权限"""
    project = await project_manager._load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    is_admin = current_user.role == "admin"
    if not project_manager.check_project_access(project, str(current_user.id), is_admin):
        raise HTTPException(status_code=403, detail="You don't have permission to access this project")


@router.get("/state")
async def get_execution_state(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取执行状态"""
    try:
        await _check_project_access(project_id, current_user)
        if not state_store.exists(project_id):
            raise HTTPException(status_code=404, detail="Execution state not found. Run step_3_init first.")
        state = state_store.load(project_id)
        return state.model_dump()
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wps")
async def list_work_packages(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """列出所有 WP"""
    try:
        await _check_project_access(project_id, current_user)
        if not state_store.exists(project_id):
            raise HTTPException(status_code=404, detail="Execution state not found.")
        state = state_store.load(project_id)
        wps = []
        for wp_id, wp_state in state.wp_states.items():
            spec = state.wp_specs.get(wp_id)
            wps.append({
                "wp_id": wp_id,
                "name": spec.name if spec else wp_id,
                "status": wp_state.status.value,
                "owner": wp_state.owner,
                "reviewer": wp_state.reviewer,
                "iteration_count": wp_state.iteration_count,
                "subtasks_completed": wp_state.subtasks_completed,
                "subtasks_remaining": wp_state.subtasks_remaining,
                "depends_on": state.wp_dag.get(wp_id, []),
            })
        return wps
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wps/{wp_id}")
async def get_work_package(
    project_id: str,
    wp_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取 WP 详情"""
    try:
        await _check_project_access(project_id, current_user)
        state = state_store.load(project_id)
        if wp_id not in state.wp_states:
            raise HTTPException(status_code=404, detail=f"WP {wp_id} not found")
        return {
            "spec": state.wp_specs[wp_id].model_dump(),
            "state": state.wp_states[wp_id].model_dump(),
        }
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wps/{wp_id}/execute")
async def execute_work_package(
    project_id: str,
    wp_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """执行 WP"""
    try:
        await _check_project_access(project_id, current_user)
        engine = WPExecutionEngine(project_id=project_id)
        wp_state = await engine.execute_wp(wp_id)
        return {"wp_id": wp_id, "status": wp_state.status.value}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/wps/{wp_id}/freeze")
async def freeze_work_package(
    project_id: str,
    wp_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """冻结 WP"""
    try:
        await _check_project_access(project_id, current_user)
        engine = WPExecutionEngine(project_id=project_id)
        await engine.freeze_wp(wp_id)
        return {"wp_id": wp_id, "status": "frozen"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wps/{wp_id}/subtasks")
async def list_subtasks(
    project_id: str,
    wp_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """列出 WP 的 subtask"""
    try:
        await _check_project_access(project_id, current_user)
        state = state_store.load(project_id)
        if wp_id not in state.wp_specs:
            raise HTTPException(status_code=404, detail=f"WP {wp_id} not found")
        spec = state.wp_specs[wp_id]
        wp_state = state.wp_states[wp_id]
        subtasks = []
        for st in spec.subtasks:
            result = wp_state.subtask_results.get(st.subtask_id)
            subtasks.append({
                "spec": st.model_dump(),
                "result": result.model_dump() if result else None,
            })
        return subtasks
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wps/{wp_id}/subtasks/{subtask_id}/result")
async def get_subtask_result(
    project_id: str,
    wp_id: str,
    subtask_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取 subtask 结果"""
    try:
        await _check_project_access(project_id, current_user)
        state = state_store.load(project_id)
        if wp_id not in state.wp_states:
            raise HTTPException(status_code=404, detail=f"WP {wp_id} not found")
        result = state.wp_states[wp_id].subtask_results.get(subtask_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Subtask {subtask_id} result not found")
        return result.model_dump()
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wps/{wp_id}/subtasks/{subtask_id}/preflight")
async def get_subtask_preflight(
    project_id: str,
    wp_id: str,
    subtask_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取 subtask 的 Pre-flight 检查结果"""
    try:
        await _check_project_access(project_id, current_user)
        state = state_store.load(project_id)
        if wp_id not in state.wp_states:
            raise HTTPException(status_code=404, detail=f"WP {wp_id} not found")
        result = state.wp_states[wp_id].subtask_results.get(subtask_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Subtask {subtask_id} result not found")
        if not result.preflight_result:
            raise HTTPException(status_code=404, detail=f"No pre-flight result for subtask {subtask_id}")
        return result.preflight_result
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dag")
async def get_wp_dag(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
):
    """获取 WP DAG"""
    try:
        await _check_project_access(project_id, current_user)
        state = state_store.load(project_id)
        return {
            "dag": state.wp_dag,
            "wp_statuses": {
                wp_id: ws.status.value for wp_id, ws in state.wp_states.items()
            },
        }
    except StateStoreError as e:
        raise HTTPException(status_code=500, detail=str(e))

"""
项目管理 API 路由
v6.1: 添加用户认证和权限控制
"""
from fastapi import APIRouter, HTTPException, status, Depends, Body
from typing import List, Dict, Any, Optional
import logging
import re

from app.models.project import ProjectConfig, StepStatus
from app.models.document import DocumentType
from app.models.bootloader import ResourceCardInput
from app.services.project_manager import ProjectManager
from app.utils.file_manager import FileManager
from app.services.clarity_analyzer import get_clarity_analyzer
from app.middleware.auth import get_current_active_user, require_admin, get_optional_user
from app.db.models import User as DBUser
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# 全局项目管理器实例
project_manager = ProjectManager()
file_manager = FileManager()

# 有效的步骤 ID 列表 (v6.0 - 包含 Bootloader + Step 3-4)
VALID_STEP_IDS = {
    "step_s_1",  # v6.0 NEW: Fuzzy Bootloader
    "step_0_1", "step_0_2",
    "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
    "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
    "step_3_init", "step_3_exec",
    "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
}

# 有效的 gate 名称列表
VALID_GATE_NAMES = {
    "gate_0", "gate_1", "gate_1_5", "gate_1_6", "gate_2",
    "gate_wp", "gate_freeze", "gate_delivery",
}


def validate_project_id(project_id: str) -> None:
    """
    验证项目 ID 格式

    Args:
        project_id: 项目 ID

    Raises:
        HTTPException: 如果格式无效
    """
    if not project_id or not isinstance(project_id, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project_id: must be a non-empty string"
        )

    # 项目 ID 应该只包含字母、数字、连字符和下划线
    if not re.match(r'^[a-zA-Z0-9_-]+$', project_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project_id format: only alphanumeric, hyphens, and underscores allowed"
        )

    # 长度限制
    if len(project_id) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project_id: too long (max 100 characters)"
        )


def validate_step_id(step_id: str) -> None:
    """
    验证步骤 ID

    Args:
        step_id: 步骤 ID

    Raises:
        HTTPException: 如果步骤 ID 无效
    """
    if step_id not in VALID_STEP_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid step_id: {step_id}. Must be one of {sorted(VALID_STEP_IDS)}"
        )


def validate_gate_name(gate_name: str) -> None:
    """
    验证 gate 名称

    Args:
        gate_name: Gate 名称

    Raises:
        HTTPException: 如果 gate 名称无效
    """
    if gate_name not in VALID_GATE_NAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid gate_name: {gate_name}. Must be one of {sorted(VALID_GATE_NAMES)}"
        )


@router.post("/analyze-clarity")
async def analyze_input_clarity(config: ProjectConfig) -> Dict[str, Any]:
    """
    分析输入清晰度（Phase 3: Smart Trigger Mechanism）

    在项目创建前分析输入的清晰度，帮助决定是否需要运行 Bootloader。

    Args:
        config: 项目配置

    Returns:
        Dict: 包含 clarity_score 和 timestamp
    """
    try:
        analyzer = get_clarity_analyzer()

        clarity_score = await analyzer.analyze_input_clarity(
            topic=config.topic,
            context=config.project_context,
            constraints=config.hard_constraints,
            keywords=config.keywords
        )

        logger.info(f"Clarity analysis completed - Score: {clarity_score.overall_score:.1f}, Recommendation: {clarity_score.recommendation}")

        return {
            "clarity_score": clarity_score.model_dump(),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to analyze input clarity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze input clarity: {str(e)}"
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_project(
    config: ProjectConfig,
    skip_bootloader: bool = Body(False),
    skip_reason: Optional[str] = Body(None),
    current_user: DBUser = Depends(get_current_active_user)  # v6.1: 需要认证
) -> Dict[str, Any]:
    """
    创建新项目（v6.0 Phase 3: 支持跳过 Bootloader）
    v6.1: 需要用户认证，记录项目所有者

    Args:
        config: 项目配置
        skip_bootloader: 是否跳过 Bootloader（用户手动选择）
        skip_reason: 跳过原因
        current_user: 当前认证用户

    Returns:
        Dict: 创建的项目信息（包含 clarity_score）
    """
    try:
        project = await project_manager.create_project(
            config=config,
            skip_bootloader=skip_bootloader,
            skip_reason=skip_reason,
            owner_id=str(current_user.id),  # v6.1: 记录所有者
            owner_username=current_user.username  # v6.1: 记录所有者用户名
        )
        # 返回完整的项目信息，与 get_project_status 保持一致
        # 包含 steps 字段以确保前端可以正确显示项目详情
        return {
            "project_id": project.project_id,
            "project_name": project.project_name,
            "status": project.status.value,
            "current_step": project.current_step,
            "progress": project.get_progress(),
            "clarity_score": project.metadata.get("clarity_score"),  # Phase 3: 返回清晰度评分
            "config": {
                "topic": project.config.topic,
                "target_venue": project.config.target_venue,
                "research_type": project.config.research_type.value,
                "data_status": project.config.data_status.value,
                "hard_constraints": project.config.hard_constraints,
                "time_budget": project.config.time_budget,
                "keywords": project.config.keywords,
                "project_context": project.config.project_context
            },
            "steps": {
                step_id: {
                    "step_id": step_info.step_id,
                    "step_name": step_info.step_name,
                    "status": step_info.status.value,
                    "ai_model": step_info.ai_model,
                    "started_at": step_info.started_at.isoformat() if step_info.started_at else None,
                    "completed_at": step_info.completed_at.isoformat() if step_info.completed_at else None,
                    "error_message": step_info.error_message
                }
                for step_id, step_info in project.steps.items()
            },
            "gate_0_passed": project.gate_0_passed,
            "gate_1_passed": project.gate_1_passed,
            "gate_1_5_passed": project.gate_1_5_passed,
            "gate_2_passed": project.gate_2_passed,
            "created_at": project.created_at.isoformat(),
            "updated_at": project.updated_at.isoformat(),
            "message": "Project created successfully"
        }
    except Exception as e:
        logger.error(f"Failed to create project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_id}/bootloader/skip")
async def skip_bootloader(
    project_id: str,
    reason: str = Body(..., embed=True),
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    跳过 Bootloader 并直接进入 Step 0（Phase 3: Smart Trigger）

    用于在项目创建后，用户决定跳过 Bootloader 的情况。

    Args:
        project_id: 项目 ID
        reason: 跳过原因
        current_user: 当前认证用户

    Returns:
        Dict: 操作结果
    """
    try:
        validate_project_id(project_id)

        # 加载项目
        project = await project_manager._load_project(project_id)

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 验证当前步骤是 step_s_1
        if project.current_step != "step_s_1":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Can only skip Bootloader before execution. Current step: {project.current_step}"
            )

        # 验证 step_s_1 状态是 PENDING
        if project.steps["step_s_1"].status != StepStatus.PENDING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Bootloader already executed or skipped. Status: {project.steps['step_s_1'].status.value}"
            )

        # 更新项目状态
        from datetime import datetime

        project.steps["step_s_1"].status = StepStatus.SKIPPED
        project.steps["step_s_1"].completed_at = datetime.now()
        project.current_step = "step_0_1"

        # 更新 metadata
        if "bootloader_decision" not in project.metadata:
            project.metadata["bootloader_decision"] = {}

        project.metadata["bootloader_decision"]["skip_reason"] = reason
        project.metadata["bootloader_decision"]["skipped_at"] = datetime.now().isoformat()

        # 保存项目
        await project_manager._save_project(project)

        logger.info(f"Bootloader skipped for project {project_id}. Reason: {reason}")

        return {
            "success": True,
            "message": "Bootloader skipped successfully",
            "next_step": "step_0_1",
            "project_id": project_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to skip bootloader: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to skip bootloader: {str(e)}"
        )


@router.post("/{project_id}/bootloader/regenerate")
async def regenerate_bootloader(
    project_id: str,
    focus_areas: Optional[List[str]] = Body(None, embed=True),
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    重新生成 Bootloader 输出（Phase 3: Confirmation Workflow）

    允许用户选择关注领域重新生成 Bootloader 输出。

    Args:
        project_id: 项目 ID
        focus_areas: 可选的关注领域列表（如 ["datasets", "tools"]）
        current_user: 当前认证用户

    Returns:
        Dict: 新的 Bootloader 输出
    """
    try:
        validate_project_id(project_id)

        # 检查访问权限
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        from app.services.bootloader_confirmation import get_bootloader_confirmation_service

        service = get_bootloader_confirmation_service()
        result = await service.regenerate_bootloader(project_id, focus_areas)

        logger.info(f"Bootloader regenerated for project {project_id}")

        return {
            "success": True,
            "outputs": {
                "domain_dictionary": result.domain_dictionary.model_dump(),
                "oot_candidates": result.oot_candidates.model_dump(),
                "resource_card": result.resource_card.model_dump()
            },
            "execution_time": result.execution_time
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to regenerate bootloader: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate bootloader: {str(e)}"
        )


@router.put("/{project_id}/bootloader/outputs")
async def update_bootloader_outputs(
    project_id: str,
    outputs: Dict[str, Any],
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    更新用户编辑的 Bootloader 输出（Phase 3: Confirmation Workflow）

    允许用户编辑 Domain Dictionary、OOT Candidates 或 Resource Card。

    Args:
        project_id: 项目 ID
        outputs: 包含编辑后输出的字典
        current_user: 当前认证用户

    Returns:
        Dict: 操作结果
    """
    try:
        validate_project_id(project_id)

        # 检查访问权限
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        from app.services.bootloader_confirmation import get_bootloader_confirmation_service
        from app.models.bootloader import DomainDictionary, OOTCandidates, ResourceCard

        service = get_bootloader_confirmation_service()

        # Parse outputs
        domain_dict = None
        oot_cands = None
        resource_card = None

        if "domain_dictionary" in outputs:
            domain_dict = DomainDictionary(**outputs["domain_dictionary"])

        if "oot_candidates" in outputs:
            oot_cands = OOTCandidates(**outputs["oot_candidates"])

        if "resource_card" in outputs:
            resource_card = ResourceCard(**outputs["resource_card"])

        success = await service.update_outputs(
            project_id,
            domain_dictionary=domain_dict,
            oot_candidates=oot_cands,
            resource_card=resource_card
        )

        if success:
            logger.info(f"Bootloader outputs updated for project {project_id}")
            return {
                "success": True,
                "message": "Bootloader outputs updated successfully"
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update bootloader outputs"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update bootloader outputs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update bootloader outputs: {str(e)}"
        )


@router.post("/{project_id}/bootloader/confirm")
async def confirm_bootloader(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    确认 Bootloader 输出并进入 Step 0（Phase 3: Confirmation Workflow）

    完成 Loop1（定义对齐确认），标记 Bootloader 为已确认，
    并将项目推进到 Step 0.1。

    Args:
        project_id: 项目 ID
        current_user: 当前认证用户

    Returns:
        Dict: 操作结果和更新后的项目信息
    """
    try:
        validate_project_id(project_id)

        # 检查访问权限
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        from app.services.bootloader_confirmation import get_bootloader_confirmation_service

        service = get_bootloader_confirmation_service()
        project = await service.confirm_and_proceed(project_id)

        logger.info(f"Bootloader confirmed for project {project_id}, proceeding to {project.current_step}")

        return {
            "success": True,
            "message": "Bootloader confirmed successfully",
            "next_step": project.current_step,
            "project": {
                "project_id": project.project_id,
                "current_step": project.current_step,
                "status": project.status.value
            }
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to confirm bootloader: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to confirm bootloader: {str(e)}"
        )


@router.get("")
@router.get("/")
async def list_projects(
    current_user: DBUser = Depends(get_current_active_user)  # v6.1: 需要认证
) -> List[Dict[str, Any]]:
    """
    列出用户可访问的项目
    v6.1: 管理员可以看到所有项目，普通用户只能看到自己的项目

    Args:
        current_user: 当前认证用户

    Returns:
        List[Dict]: 项目列表
    """
    try:
        is_admin = current_user.role == "admin"
        return await project_manager.list_projects_for_user(
            user_id=str(current_user.id),
            is_admin=is_admin
        )
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{project_id}")
async def get_project_status(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)  # v6.1: 需要认证
) -> Dict[str, Any]:
    """
    获取项目状态
    v6.1: 需要用户认证，检查访问权限

    Args:
        project_id: 项目 ID
        current_user: 当前认证用户

    Returns:
        Dict: 项目状态信息
    """
    try:
        # 加载项目
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        return await project_manager.get_project_status(project_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get project status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )




@router.post("/{project_id}/steps/{step_id}/execute")
async def execute_step(
    project_id: str,
    step_id: str,
    current_user: DBUser = Depends(get_current_active_user)  # v6.1: 需要认证
) -> Dict[str, Any]:
    """
    执行指定步骤
    v6.1: 需要用户认证，检查访问权限

    Args:
        project_id: 项目 ID
        step_id: 步骤 ID
        current_user: 当前认证用户

    Returns:
        Dict: 执行结果
    """
    # 验证输入
    validate_project_id(project_id)
    validate_step_id(step_id)

    try:
        # 加载项目
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 执行步骤
        updated_project = await project_manager.execute_step(project, step_id)

        # 获取步骤的实际状态
        step_info = updated_project.steps.get(step_id)
        step_status = step_info.status.value if step_info else "unknown"

        return {
            "project_id": updated_project.project_id,
            "step_id": step_id,
            "status": step_status,
            "current_step": updated_project.current_step,
            "error_message": step_info.error_message if step_info else None,
            "message": f"Step {step_id} executed with status: {step_status}"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to execute step: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_id}/gates/{gate_name}/check")
async def check_gate(
    project_id: str,
    gate_name: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    检查 Gate

    Args:
        project_id: 项目 ID
        gate_name: Gate 名称 (gate_0, gate_1, gate_1_25, gate_1_5, gate_1_6, gate_2)
        current_user: 当前认证用户

    Returns:
        Dict: Gate 检查结果
    """
    # 验证输入
    validate_project_id(project_id)
    validate_gate_name(gate_name)

    try:
        # 加载项目
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 检查 Gate
        result = await project_manager.check_gate(project, gate_name)

        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to check gate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_id}/gates/{gate_name}/approve")
async def approve_gate(
    project_id: str,
    gate_name: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    人工确认通过 Gate（跳过自动检查）

    Args:
        project_id: 项目 ID
        gate_name: Gate 名称

    Returns:
        Dict: 操作结果
    """
    validate_project_id(project_id)
    validate_gate_name(gate_name)

    try:
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 设置 gate 为通过
        from datetime import datetime
        gate_flag_map = {
            "gate_0": "gate_0_passed",
            "gate_1": "gate_1_passed",
            "gate_1_5": "gate_1_5_passed",
            "gate_1_6": "gate_1_6_passed",
            "gate_2": "gate_2_passed",
            "gate_delivery": "gate_delivery_passed",
        }

        flag = gate_flag_map.get(gate_name)
        if not flag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Gate {gate_name} does not support manual approval"
            )

        setattr(project, flag, True)
        project.gate_results[gate_name] = {
            "verdict": "PASS",
            "manual_approval": True,
            "approved_by": current_user.username,
            "checked_at": datetime.now().isoformat(),
            "note": f"Manually approved by {current_user.username}"
        }

        await project_manager._save_project(project)
        logger.info(f"Gate {gate_name} manually approved by {current_user.username} for project {project_id}")

        return {
            "gate_name": gate_name,
            "verdict": "PASS",
            "manual_approval": True,
            "approved_by": current_user.username,
            "message": f"Gate {gate_name} 已人工确认通过"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to approve gate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_id}/loops/{gate_name}/rollback")
async def trigger_loop_rollback(
    project_id: str,
    gate_name: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    手动触发 Loop 回退 (v7 SOP Section 3.3)

    当 Gate 失败时，手动触发回退到指定步骤重新执行。

    Args:
        project_id: 项目 ID
        gate_name: Gate 名称 (gate_1, gate_1_5, gate_1_6, gate_2, red_team)

    Returns:
        Dict: 回退结果
    """
    validate_project_id(project_id)

    from app.services.project_manager import LOOP_DEFINITIONS

    if gate_name not in LOOP_DEFINITIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No loop defined for gate: {gate_name}. Valid gates: {sorted(LOOP_DEFINITIONS.keys())}"
        )

    try:
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        result = await project_manager.handle_gate_failure(project, gate_name)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger loop rollback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{project_id}/status")
async def get_project_detailed_status(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    获取项目详细状态（包含步骤信息）

    Args:
        project_id: 项目 ID
        current_user: 当前认证用户

    Returns:
        Dict: 项目详细状态信息
    """
    try:
        # 检查访问权限
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        return await project_manager.get_project_status(project_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get project status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{project_id}/documents")
async def get_project_documents(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)  # v6.1: 需要认证
) -> List[Dict[str, Any]]:
    """
    获取项目文档列表
    v6.1: 普通用户只能看到最终文档，管理员可以看到所有文档

    Args:
        project_id: 项目 ID
        current_user: 当前认证用户

    Returns:
        List[Dict]: 文档列表
    """
    try:
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # TODO: 讨论确定 non-admin 用户应该看到哪些文档，当前仅限最终文档 + Bootloader 输出
        # 定义普通用户可见的文档类型
        user_visible_docs = {
            DocumentType.RESEARCH_PLAN_FROZEN,  # 最终文档
            DocumentType.DOMAIN_DICTIONARY,  # Bootloader 输出
            DocumentType.OOT_CANDIDATES,
            DocumentType.RESOURCE_CARD,
        }

        documents = []
        for doc_type in DocumentType:
            # 普通用户只能看到特定文档
            if not is_admin and doc_type not in user_visible_docs:
                continue

            try:
                doc = await file_manager.load_document(project_id, doc_type)
                if doc:
                    # 获取枚举值，兼容字符串和枚举类型
                    doc_type_value = getattr(doc.metadata.doc_type, 'value', doc.metadata.doc_type)
                    status_value = getattr(doc.metadata.status, 'value', doc.metadata.status)

                    documents.append({
                        "doc_type": doc_type_value,
                        "status": status_value,
                        "created_at": doc.metadata.created_at.isoformat(),
                        "updated_at": doc.metadata.updated_at.isoformat(),
                        "project_id": doc.metadata.project_id,
                        "content": doc.content  # 包含完整内容
                    })
            except Exception as e:
                logger.debug(f"Could not load document {doc_type}: {e}")
                continue  # 文档不存在，跳过

        return documents
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to get documents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{project_id}/documents/{doc_type}")
async def get_document(
    project_id: str,
    doc_type: str,
    current_user: DBUser = Depends(get_current_active_user)  # v6.1: 需要认证
) -> Dict[str, Any]:
    """
    获取指定文档
    v6.1: 普通用户只能访问最终文档，管理员可以访问所有文档

    Args:
        project_id: 项目 ID
        doc_type: 文档类型
        current_user: 当前认证用户

    Returns:
        Dict: 文档内容
    """
    try:
        # 加载项目并检查权限
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 转换文档类型
        doc_type_enum = DocumentType(doc_type)

        # TODO: 讨论确定 non-admin 用户应该看到哪些文档，当前仅限最终文档 + Bootloader 输出
        user_visible_docs = {
            DocumentType.RESEARCH_PLAN_FROZEN,
            DocumentType.DOMAIN_DICTIONARY,
            DocumentType.OOT_CANDIDATES,
            DocumentType.RESOURCE_CARD,
        }

        if not is_admin and doc_type_enum not in user_visible_docs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this document"
            )

        doc = await file_manager.load_document(project_id, doc_type_enum)
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {doc_type}"
            )

        # 获取枚举值，兼容字符串和枚举类型
        doc_type_value = getattr(doc.metadata.doc_type, 'value', doc.metadata.doc_type)
        status_value = getattr(doc.metadata.status, 'value', doc.metadata.status)

        return {
            "doc_type": doc_type_value,
            "content": doc.content,
            "status": status_value,
            "created_at": doc.metadata.created_at.isoformat(),
            "updated_at": doc.metadata.updated_at.isoformat(),
            "project_id": doc.metadata.project_id
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid document type: {doc_type}"
        )
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{project_id}/steps/{step_id}/reset")
async def reset_step(
    project_id: str,
    step_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    重置步骤状态（用于重试失败的步骤）

    Args:
        project_id: 项目 ID
        step_id: 步骤 ID
        current_user: 当前认证用户

    Returns:
        Dict: 重置结果
    """
    try:
        # 加载项目
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 检查步骤是否存在
        if step_id not in project.steps:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Step not found: {step_id}"
            )

        # 重置步骤状态
        from app.models.project import StepStatus
        project.update_step_status(step_id, StepStatus.PENDING)
        project.steps[step_id].error_message = None
        project.steps[step_id].started_at = None
        project.steps[step_id].completed_at = None

        # 保存项目
        await project_manager._save_project(project)

        return {
            "project_id": project_id,
            "step_id": step_id,
            "status": "pending",
            "message": f"Step {step_id} has been reset and ready for retry"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset step: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{project_id}/config")
async def update_project_config(
    project_id: str,
    config: ProjectConfig,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    更新项目配置（仅在未开始执行时允许）

    Args:
        project_id: 项目 ID
        config: 新的项目配置
        current_user: 当前认证用户

    Returns:
        Dict: 更新后的项目信息
    """
    try:
        # 检查访问权限
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project not found: {project_id}"
            )
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        updated_project = await project_manager.update_project_config(project_id, config)

        # 返回完整的项目信息
        return {
            "project_id": updated_project.project_id,
            "project_name": updated_project.project_name,
            "status": updated_project.status.value,
            "current_step": updated_project.current_step,
            "progress": updated_project.get_progress(),
            "config": {
                "topic": updated_project.config.topic,
                "target_venue": updated_project.config.target_venue,
                "research_type": updated_project.config.research_type.value,
                "data_status": updated_project.config.data_status.value,
                "hard_constraints": updated_project.config.hard_constraints,
                "time_budget": updated_project.config.time_budget,
                "keywords": updated_project.config.keywords,
                "project_context": updated_project.config.project_context
            },
            "steps": {
                step_id: {
                    "step_id": step_info.step_id,
                    "step_name": step_info.step_name,
                    "status": step_info.status.value,
                    "started_at": step_info.started_at.isoformat() if step_info.started_at else None,
                    "completed_at": step_info.completed_at.isoformat() if step_info.completed_at else None,
                    "error_message": step_info.error_message
                }
                for step_id, step_info in updated_project.steps.items()
            },
            "gate_0_passed": updated_project.gate_0_passed,
            "gate_1_passed": updated_project.gate_1_passed,
            "gate_1_5_passed": updated_project.gate_1_5_passed,
            "gate_2_passed": updated_project.gate_2_passed,
            "created_at": updated_project.created_at.isoformat(),
            "updated_at": updated_project.updated_at.isoformat(),
            "message": "Project config updated successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update project config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{project_id}/resource-card-input")
async def save_resource_card_input(
    project_id: str,
    resource_input: ResourceCardInput,
    current_user: DBUser = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    保存用户填写的 Resource Card 表单数据

    Args:
        project_id: 项目 ID
        resource_input: Resource Card 表单数据
        current_user: 当前认证用户

    Returns:
        Dict: 保存结果
    """
    validate_project_id(project_id)
    try:
        project = await project_manager._load_project(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project {project_id} not found"
            )

        # 检查访问权限
        is_admin = current_user.role == "admin"
        if not project_manager.check_project_access(project, str(current_user.id), is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this project"
            )

        # 保存到 project.config.resource_card_input
        project.config.resource_card_input = resource_input.model_dump()
        project.updated_at = datetime.now()
        await project_manager._save_project(project)

        logger.info(f"Saved resource card input for project {project_id}, is_skipped={resource_input.is_skipped}")
        return {
            "success": True,
            "project_id": project_id,
            "is_skipped": resource_input.is_skipped,
            "message": "Resource card input saved successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save resource card input: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: DBUser = Depends(require_admin)  # v6.1: 仅管理员可删除
) -> Dict[str, Any]:
    """
    删除项目（仅管理员）
    v6.1: 仅管理员可以删除项目

    Args:
        project_id: 项目 ID
        current_user: 当前管理员用户

    Returns:
        Dict: 删除结果
    """
    try:
        success = await project_manager.delete_project(project_id)
        logger.info(f"Admin {current_user.username} deleted project {project_id}")
        return {
            "project_id": project_id,
            "success": success,
            "message": "Project deleted successfully"
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to delete project: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


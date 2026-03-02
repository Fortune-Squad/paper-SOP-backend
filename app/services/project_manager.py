"""
项目管理服务
负责管理项目的创建、执行和状态跟踪
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from app.models.project import Project, ProjectConfig, ProjectStatus, StepInfo, StepStatus
from app.models.document import DocumentType
from app.models.gate import GateVerdict
from app.services.gate_checker import GateChecker
from app.steps.step_s1 import Step_S1_Bootloader
from app.steps.step0 import Step0_1_IntakeCard, Step0_2_VenueTaste
from app.steps.step1 import (
    Step1_1_DeepResearch,
    Step1_1b_ReferenceQA,
    Step1_2_TopicDecision,
    Step1_2b_TopicAlignmentCheck,
    Step1_3_KillerPriorCheck,
    Step1_4_ClaimsFreeze,
    Step1_5_FigureFirstStory
)
from app.steps.step2 import (
    Step2_0_FigureTableList,
    Step2_1_FullProposal,
    Step2_2_DataSimSpec,
    Step2_3_EngineeringDecomposition,
    Step2_4_RedTeamReview,
    Step2_4b_PatchPropagation,
    Step2_5_PlanFreeze
)
from app.utils.file_manager import FileManager
from app.utils.git_manager import GitManager
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ProjectManager:
    """项目管理器"""

    def __init__(
        self,
        file_manager: Optional[FileManager] = None,
        git_manager: Optional[GitManager] = None,
        vector_store: Optional[VectorStore] = None,
        gate_checker: Optional[GateChecker] = None
    ):
        """
        初始化项目管理器

        Args:
            file_manager: 文件管理器
            git_manager: Git 管理器
            vector_store: 向量数据库
            gate_checker: Gate 检查器
        """
        self.file_manager = file_manager or FileManager()
        self.git_manager = git_manager or GitManager()
        self.vector_store = vector_store or VectorStore()
        self.gate_checker = gate_checker or GateChecker(file_manager=self.file_manager)

    async def create_project(
        self,
        config: ProjectConfig,
        skip_bootloader: bool = False,
        skip_reason: Optional[str] = None,
        owner_id: Optional[str] = None,
        owner_username: Optional[str] = None
    ) -> Project:
        """
        创建新项目（v6.0 Phase 3: 支持智能触发和跳过 Bootloader）
        v6.1: 添加用户所有权支持

        Args:
            config: 项目配置
            skip_bootloader: 是否跳过 Bootloader（用户手动选择）
            skip_reason: 跳过原因
            owner_id: 项目所有者 ID
            owner_username: 项目所有者用户名

        Returns:
            Project: 创建的项目对象
        """
        try:
            # 生成项目名称和 ID
            project_name = config.topic

            # 生成短的唯一 project_id（避免路径过长问题）
            # 使用时间戳 + topic 哈希的组合，确保唯一性且长度可控
            import hashlib
            from datetime import datetime

            # 获取 topic 的前 30 个字符作为可读前缀
            topic_prefix = config.topic.lower().replace(" ", "-")[:30].rstrip("-")

            # 使用 topic + 时间戳的哈希值确保唯一性
            unique_string = f"{config.topic}_{datetime.now().isoformat()}"
            topic_hash = hashlib.md5(unique_string.encode()).hexdigest()[:8]

            # 组合：可读前缀 + 哈希值
            project_id = f"{topic_prefix}-{topic_hash}"

            logger.info(f"Creating new project: {project_name}")

            # Phase 3: 分析输入清晰度
            from app.services.clarity_analyzer import get_clarity_analyzer

            clarity_analyzer = get_clarity_analyzer()
            clarity_score = await clarity_analyzer.analyze_input_clarity(
                topic=config.topic,
                context=config.project_context,
                constraints=config.hard_constraints,
                keywords=config.keywords
            )

            logger.info(f"Clarity analysis - Score: {clarity_score.overall_score:.1f}, Recommendation: {clarity_score.recommendation}")

            # 决定初始步骤：基于清晰度和用户选择
            should_skip = skip_bootloader or (
                clarity_score.recommendation == "skip_bootloader"
            )

            initial_step = "step_0_1" if should_skip else "step_s_1"

            logger.info(f"Initial step: {initial_step} (skip_bootloader={skip_bootloader}, clarity_recommendation={clarity_score.recommendation})")

            # 创建项目对象
            project = Project(
                project_id=project_id,
                project_name=project_name,
                config=config,
                status=ProjectStatus.CREATED,
                current_step=initial_step,  # Phase 3: 基于清晰度决定
                owner_id=owner_id,  # v6.1: 记录所有者
                owner_username=owner_username,  # v6.1: 记录所有者用户名
                metadata={
                    "clarity_score": clarity_score.model_dump(),
                    "bootloader_decision": {
                        "should_run": not should_skip,
                        "user_override": skip_bootloader,
                        "skip_reason": skip_reason
                    }
                }
            )

            # 如果跳过 Bootloader，标记 step_s_1 为 SKIPPED
            if should_skip:
                project.steps["step_s_1"].status = StepStatus.SKIPPED
                project.steps["step_s_1"].completed_at = datetime.now()
                logger.info(f"Bootloader skipped - Reason: {skip_reason or 'High clarity score'}")

            # 初始化项目目录
            self.file_manager.ensure_project_structure(project_id)

            # 初始化 Git 仓库
            self.git_manager.init_repo(project_id)

            # 保存项目配置
            await self._save_project(project)

            logger.info(f"Project created successfully: {project_id}")
            return project

        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            raise

    async def execute_step(self, project: Project, step_id: str) -> Project:
        """
        执行指定步骤

        Args:
            project: 项目对象
            step_id: 步骤 ID

        Returns:
            Project: 更新后的项目对象
        """
        try:
            logger.info(f"Executing step {step_id} for project {project.project_id}")

            # 验证步骤前置条件
            is_valid, error_msg = self._validate_step_prerequisites(project, step_id)
            if not is_valid:
                logger.error(f"Step prerequisites not met: {error_msg}")
                raise ValueError(f"无法执行步骤 {step_id}: {error_msg}")

            # 检查步骤是否已完成（没有错误信息）
            if step_id in project.steps:
                step_info = project.steps[step_id]
                if step_info.status == StepStatus.COMPLETED and not step_info.error_message:
                    logger.warning(f"Step {step_id} already completed successfully")
                    return project
                elif step_info.status == StepStatus.COMPLETED and step_info.error_message:
                    # 如果步骤状态是 COMPLETED 但有错误信息，重置为 PENDING 以便重试
                    logger.info(f"Step {step_id} has error, resetting to PENDING for retry")
                    project.update_step_status(step_id, StepStatus.PENDING)
                    project.steps[step_id].error_message = None
                    # 清除相关的 gate 状态
                    self._clear_related_gates(project, step_id)
                    await self._save_project(project)

            # 更新步骤状态为进行中
            project.update_step_status(step_id, StepStatus.IN_PROGRESS)
            await self._save_project(project)

            # 执行步骤
            document = None
            step = None
            if step_id == "step_s_1":
                step = Step_S1_Bootloader(project)
                document = await step.execute()
            elif step_id == "step_0_1":
                step = Step0_1_IntakeCard(project)
                document = await step.execute()
            elif step_id == "step_0_2":
                step = Step0_2_VenueTaste(project)
                document = await step.execute()
            elif step_id == "step_1_1":
                step = Step1_1_DeepResearch(project)
                document = await step.execute()
            elif step_id == "step_1_1b":
                step = Step1_1b_ReferenceQA(project)
                document = await step.execute()
            elif step_id == "step_1_2":
                step = Step1_2_TopicDecision(project)
                document = await step.execute()
            elif step_id == "step_1_2b":
                step = Step1_2b_TopicAlignmentCheck(project)
                document = await step.execute()
            elif step_id == "step_1_3":
                step = Step1_3_KillerPriorCheck(project)
                document = await step.execute()
            elif step_id == "step_1_4":
                step = Step1_4_ClaimsFreeze(project)
                document = await step.execute()
            elif step_id == "step_1_5":
                step = Step1_5_FigureFirstStory(project)
                document = await step.execute()
            elif step_id == "step_2_0":
                step = Step2_0_FigureTableList(project)
                document = await step.execute()
            elif step_id == "step_2_1":
                step = Step2_1_FullProposal(project)
                document = await step.execute()
            elif step_id == "step_2_2":
                step = Step2_2_DataSimSpec(project)
                document = await step.execute()
            elif step_id == "step_2_3":
                step = Step2_3_EngineeringDecomposition(project)
                document = await step.execute()
            elif step_id == "step_2_4":
                step = Step2_4_RedTeamReview(project)
                document = await step.execute()
            elif step_id == "step_2_4b":
                step = Step2_4b_PatchPropagation(project)
                document = await step.execute()
            elif step_id == "step_2_5":
                step = Step2_5_PlanFreeze(project)
                document = await step.execute()
            else:
                raise ValueError(f"Unknown step: {step_id}")

            # 更新步骤状态为完成，并设置 AI 模型
            project.update_step_status(step_id, StepStatus.COMPLETED)
            # 设置 AI 模型信息
            if step_id in project.steps and step:
                project.steps[step_id].ai_model = step.ai_model
            # 清除错误信息（如果有的话）
            if step_id in project.steps:
                project.steps[step_id].error_message = None

            # 只有当执行的是当前步骤时，才更新到下一步
            # 这样可以防止跳步骤执行时错误更新 current_step
            next_step = None
            if step_id == project.current_step:
                next_step = self._get_next_step(step_id)
                if next_step:
                    project.current_step = next_step
                    logger.info(f"Moving current_step from {step_id} to {next_step}")

            # 保存项目
            await self._save_project(project)

            logger.info(f"Step {step_id} completed successfully")

            # 自动检查相关的 Gate（v4.0 NEW）
            # Gate 1.6: 在 Step 1.1b (Reference QA) 完成后自动检查
            if step_id == "step_1_1b":
                logger.info("Auto-checking Gate 1.6 after Step 1.1b completion")
                try:
                    gate_result = await self.gate_checker.check_gate_1_6(project)
                    # 保存检查结果（无论通过与否）
                    project.gate_results["gate_1_6"] = gate_result.model_dump()
                    if gate_result.verdict == GateVerdict.PASS:
                        project.gate_1_6_passed = True
                        logger.info("Gate 1.6 auto-check: PASS")
                    else:
                        project.gate_1_6_passed = False
                        logger.warning("Gate 1.6 auto-check: FAIL - manual review required")
                    await self._save_project(project)
                except Exception as e:
                    logger.error(f"Gate 1.6 auto-check failed: {e}")

            # Gate 1.25: 在 Step 1.2b (Topic Alignment Check) 完成后自动检查
            if step_id == "step_1_2b":
                logger.info("Auto-checking Gate 1.25 after Step 1.2b completion")
                try:
                    gate_result = await self.gate_checker.check_gate_1_25(project)
                    # 保存检查结果（无论通过与否）
                    project.gate_results["gate_1_25"] = gate_result.model_dump()
                    if gate_result.verdict == GateVerdict.PASS:
                        project.gate_1_25_passed = True
                        logger.info("Gate 1.25 auto-check: PASS")
                    else:
                        project.gate_1_25_passed = False
                        logger.warning("Gate 1.25 auto-check: FAIL - manual review required")
                    await self._save_project(project)
                except Exception as e:
                    logger.error(f"Gate 1.25 auto-check failed: {e}")

            # 步骤间延迟，避免API速率限制
            if next_step:
                from app.config import settings
                delay = settings.step_interval_delay
                logger.info(f"Waiting {delay} seconds before next step...")
                await asyncio.sleep(delay)

            return project

        except Exception as e:
            logger.error(f"Failed to execute step {step_id}: {e}")
            # 更新步骤状态为失败
            project.update_step_status(step_id, StepStatus.FAILED, error_message=str(e))

            # 如果失败的是当前步骤，current_step 保持不变
            # 如果失败的是之前的步骤（重新执行），current_step 也保持不变
            logger.info(f"Step {step_id} failed, current_step remains at {project.current_step}")

            await self._save_project(project)
            raise

    async def check_gate(self, project: Project, gate_name: str) -> Dict[str, Any]:
        """
        检查 Gate

        Args:
            project: 项目对象
            gate_name: Gate 名称 (gate_0, gate_1, gate_1_25, gate_1_5, gate_1_6, gate_2)

        Returns:
            Dict: Gate 检查结果
        """
        try:
            logger.info(f"Checking {gate_name} for project {project.project_id}")

            # 执行 Gate 检查
            if gate_name == "gate_0":
                result = await self.gate_checker.check_gate_0(project)
                project.gate_results["gate_0"] = result.model_dump()
                project.gate_0_passed = (result.verdict == GateVerdict.PASS)
            elif gate_name == "gate_1":
                result = await self.gate_checker.check_gate_1(project)
                project.gate_results["gate_1"] = result.model_dump()
                project.gate_1_passed = (result.verdict == GateVerdict.PASS)
            elif gate_name == "gate_1_25":
                result = await self.gate_checker.check_gate_1_25(project)
                project.gate_results["gate_1_25"] = result.model_dump()
                project.gate_1_25_passed = (result.verdict == GateVerdict.PASS)
            elif gate_name == "gate_1_5":
                result = await self.gate_checker.check_gate_1_5(project)
                project.gate_results["gate_1_5"] = result.model_dump()
                project.gate_1_5_passed = (result.verdict == GateVerdict.PASS)
            elif gate_name == "gate_1_6":
                result = await self.gate_checker.check_gate_1_6(project)
                project.gate_results["gate_1_6"] = result.model_dump()
                project.gate_1_6_passed = (result.verdict == GateVerdict.PASS)
            elif gate_name == "gate_2":
                result = await self.gate_checker.check_gate_2(project)
                project.gate_results["gate_2"] = result.model_dump()
                project.gate_2_passed = (result.verdict == GateVerdict.PASS)
            else:
                raise ValueError(f"Unknown gate: {gate_name}")

            # 保存项目
            await self._save_project(project)

            logger.info(f"{gate_name} check result: {result.verdict.value}")
            return result.model_dump()

        except Exception as e:
            logger.error(f"Failed to check {gate_name}: {e}")
            raise

    async def get_project_status(self, project_id: str) -> Dict[str, Any]:
        """
        获取项目状态

        Args:
            project_id: 项目 ID

        Returns:
            Dict: 项目状态信息
        """
        try:
            project = await self._load_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            return {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "status": project.status.value,
                "current_step": project.current_step,
                "progress": project.get_progress(),
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
                "gate_0_passed": project.gate_0_passed,
                "gate_1_passed": project.gate_1_passed,
                "gate_1_25_passed": project.gate_1_25_passed,
                "gate_1_5_passed": project.gate_1_5_passed,
                "gate_1_6_passed": project.gate_1_6_passed,
                "gate_2_passed": project.gate_2_passed,
                "gate_results": project.gate_results,  # v4.0 NEW - 返回完整的 Gate 检查结果
                "loop_history": project.loop_history,  # v7.0 NEW - 返回 Loop 历史记录
                "steps": {
                    step_id: {
                        "step_id": step_id,
                        "step_name": info.step_name,
                        "status": info.status.value,
                        "ai_model": info.ai_model,
                        "started_at": info.started_at.isoformat() if info.started_at else None,
                        "completed_at": info.completed_at.isoformat() if info.completed_at else None,
                        "error_message": info.error_message,
                        "retry_count": info.retry_count,  # v7.0 NEW - 返回重试次数
                        "max_retries": info.max_retries  # v7.0 NEW - 返回最大重试次数
                    }
                    for step_id, info in project.steps.items()
                },
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to get project status: {e}")
            raise

    async def list_projects(self) -> List[Dict[str, Any]]:
        """
        列出所有项目

        Returns:
            List[Dict]: 项目列表
        """
        try:
            projects = []
            projects_path = self.file_manager.base_path

            # 扫描项目目录
            if projects_path.exists():
                for project_dir in projects_path.iterdir():
                    if project_dir.is_dir():
                        project_file = project_dir / "project.json"
                        if project_file.exists():
                            try:
                                project = await self._load_project(project_dir.name)
                                if project:
                                    projects.append({
                                        "project_id": project.project_id,
                                        "project_name": project.project_name,
                                        "status": project.status.value,
                                        "current_step": project.current_step,
                                        "progress": project.get_progress(),
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
                                        "owner_id": project.owner_id,  # v6.1: 添加所有者信息
                                        "owner_username": project.owner_username,  # v6.1: 添加所有者用户名
                                        "gate_0_passed": project.gate_0_passed,
                                        "gate_1_passed": project.gate_1_passed,
                                        "gate_1_25_passed": project.gate_1_25_passed,
                                        "gate_1_5_passed": project.gate_1_5_passed,
                                        "gate_1_6_passed": project.gate_1_6_passed,
                                        "gate_2_passed": project.gate_2_passed,
                                        "gate_results": project.gate_results,  # v4.0 NEW
                                        "created_at": project.created_at.isoformat(),
                                        "updated_at": project.updated_at.isoformat()
                                    })
                            except Exception as e:
                                logger.warning(f"Failed to load project {project_dir.name}: {e}")
                                continue

            return projects

        except Exception as e:
            logger.error(f"Failed to list projects: {e}")
            raise

    async def list_projects_for_user(self, user_id: str, is_admin: bool = False) -> List[Dict[str, Any]]:
        """
        列出用户可访问的项目（v6.1 NEW）

        Args:
            user_id: 用户 ID
            is_admin: 是否为管理员

        Returns:
            List[Dict]: 项目列表（管理员看到所有项目，普通用户只看到自己的项目）
        """
        try:
            all_projects = await self.list_projects()

            # 管理员可以看到所有项目
            if is_admin:
                return all_projects

            # 普通用户只能看到自己创建的项目
            user_projects = [
                project for project in all_projects
                if project.get("owner_id") == user_id
            ]

            return user_projects

        except Exception as e:
            logger.error(f"Failed to list projects for user {user_id}: {e}")
            raise

    def check_project_access(self, project: Project, user_id: str, is_admin: bool = False) -> bool:
        """
        检查用户是否有权限访问项目（v6.1 NEW）

        Args:
            project: 项目对象
            user_id: 用户 ID
            is_admin: 是否为管理员

        Returns:
            bool: 是否有权限访问
        """
        # 管理员可以访问所有项目
        if is_admin:
            return True

        # 普通用户只能访问自己创建的项目
        return project.owner_id == user_id

    async def update_project_config(self, project_id: str, config: ProjectConfig) -> Project:
        """
        更新项目配置（仅在未开始执行时允许）

        Args:
            project_id: 项目 ID
            config: 新的项目配置

        Returns:
            Project: 更新后的项目对象

        Raises:
            ValueError: 如果项目不存在或已开始执行
        """
        try:
            # 加载项目
            project = await self._load_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # 检查是否允许编辑（所有步骤必须是 PENDING 状态）
            for step_id, step_info in project.steps.items():
                if step_info.status != StepStatus.PENDING:
                    raise ValueError(
                        f"项目已开始执行步骤，无法修改配置。"
                        f"步骤 {step_info.step_id} ({step_info.step_name}) 状态为 {step_info.status.value}"
                    )

            logger.info(f"Updating config for project {project_id}")

            # 更新配置
            project.config = config

            # 更新项目名称（如果 topic 改变）
            project.project_name = config.topic

            # 更新时间戳
            project.updated_at = datetime.now()

            # 保存项目
            await self._save_project(project)

            logger.info(f"Project config updated successfully: {project_id}")
            return project

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to update project config: {e}")
            raise

    async def delete_project(self, project_id: str) -> bool:
        """
        删除项目

        Args:
            project_id: 项目 ID

        Returns:
            bool: 是否删除成功
        """
        try:
            import shutil
            import time
            import gc
            import sys

            # 检查项目是否存在
            project = await self._load_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # 删除向量数据库中的项目集合
            try:
                await self.vector_store.delete_collection(project_id)
                logger.info(f"Deleted vector store collection for project {project_id}")
            except Exception as e:
                logger.warning(f"Failed to delete vector store collection: {e}")

            # 强制垃圾回收，释放可能的文件句柄
            gc.collect()

            # 删除项目目录（带重试机制）
            project_path = self.file_manager.get_project_path(project_id)
            if project_path.exists():
                max_retries = 3
                retry_delay = 0.5  # 秒

                for attempt in range(max_retries):
                    try:
                        # Windows 特殊处理：使用 onerror 回调处理只读文件
                        def handle_remove_readonly(func, path, exc):
                            """处理只读文件删除"""
                            import os
                            import stat
                            if not os.access(path, os.W_OK):
                                # 修改文件权限为可写
                                os.chmod(path, stat.S_IWUSR | stat.S_IREAD)
                                func(path)
                            else:
                                raise

                        if sys.platform == 'win32':
                            shutil.rmtree(project_path, onerror=handle_remove_readonly)
                        else:
                            shutil.rmtree(project_path)

                        logger.info(f"Deleted project directory: {project_path}")
                        break

                    except PermissionError as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Attempt {attempt + 1} failed to delete {project_path}: {e}. Retrying...")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                            gc.collect()  # 再次尝试释放文件句柄
                        else:
                            logger.error(f"Failed to delete project directory after {max_retries} attempts: {e}")
                            raise Exception(
                                f"无法删除项目文件夹，可能有文件被占用。"
                                f"请关闭所有打开该项目文件的程序（如文本编辑器、文件管理器等），然后重试。"
                                f"\n项目路径: {project_path}"
                            )
                    except Exception as e:
                        logger.error(f"Unexpected error deleting project directory: {e}")
                        raise

            return True

        except Exception as e:
            logger.error(f"Failed to delete project {project_id}: {e}")
            raise

    def _get_next_step(self, current_step: str) -> Optional[str]:
        """
        获取下一个步骤

        Args:
            current_step: 当前步骤 ID

        Returns:
            Optional[str]: 下一个步骤 ID，如果没有则返回 None
        """
        step_sequence = [
            "step_0_1",
            "step_0_2",
            "step_1_1",
            "step_1_1b",
            "step_1_2",
            "step_1_2b",
            "step_1_3",
            "step_1_4",
            "step_1_5",
            "step_2_0",
            "step_2_1",
            "step_2_2",
            "step_2_3",
            "step_2_4",
            "step_2_4b",
            "step_2_5",
        ]

        try:
            current_index = step_sequence.index(current_step)
            if current_index < len(step_sequence) - 1:
                return step_sequence[current_index + 1]
            return None
        except ValueError:
            logger.warning(f"Unknown step: {current_step}")
            return None

    def _validate_step_prerequisites(self, project: Project, step_id: str) -> tuple[bool, str]:
        """
        验证步骤的前置条件是否满足

        Args:
            project: 项目对象
            step_id: 要执行的步骤 ID

        Returns:
            tuple[bool, str]: (是否满足前置条件, 错误消息)
        """
        step_sequence = [
            "step_s_1",  # v6.0: Bootloader
            "step_0_1", "step_0_2",
            "step_1_1", "step_1_1b", "step_1_2", "step_1_2b", "step_1_3", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
        ]

        try:
            step_index = step_sequence.index(step_id)
        except ValueError:
            return False, f"未知步骤: {step_id}"

        # 检查所有前置步骤是否已完成
        for i in range(step_index):
            prev_step_id = step_sequence[i]
            if prev_step_id in project.steps:
                prev_step = project.steps[prev_step_id]
                if prev_step.status != StepStatus.COMPLETED:
                    return False, f"前置步骤 {prev_step_id} ({prev_step.step_name}) 尚未完成（状态: {prev_step.status.value}）"

        # 特殊检查：Step 2 需要 Gate 1.5 通过
        if step_id.startswith("step_2_") and not project.gate_1_5_passed:
            return False, "Gate 1.5 (Killer Prior Check) 必须通过才能进入 Step 2"

        return True, ""

    def _clear_related_gates(self, project: Project, step_id: str) -> None:
        """
        清除与步骤相关的 gate 状态

        重新执行步骤时，需要清除依赖该步骤的 gate 状态，
        以确保 gate 检查反映最新的步骤结果

        Args:
            project: 项目对象
            step_id: 步骤 ID
        """
        # 映射步骤到其影响的 gate
        step_gate_mapping = {
            "step_0_2": ["gate_0"],  # Step 0.2 影响 Gate 0
            "step_1_1b": ["gate_1_6"],  # Step 1.1b 影响 Gate 1.6
            "step_1_2": ["gate_1"],  # Step 1.2 影响 Gate 1
            "step_1_2b": ["gate_1_25"],  # Step 1.2b 影响 Gate 1.25
            "step_1_3": ["gate_1_5"],  # Step 1.3 影响 Gate 1.5 (Killer Prior)
            "step_2_5": ["gate_2"],  # Step 2.5 影响 Gate 2
        }

        # 如果步骤影响某些 gate，清除这些 gate 的状态
        if step_id in step_gate_mapping:
            for gate_name in step_gate_mapping[step_id]:
                if gate_name == "gate_0":
                    project.gate_0_passed = False
                    if "gate_0" in project.gate_results:
                        del project.gate_results["gate_0"]
                    logger.info(f"Cleared gate_0 status due to {step_id} re-execution")
                elif gate_name == "gate_1":
                    project.gate_1_passed = False
                    if "gate_1" in project.gate_results:
                        del project.gate_results["gate_1"]
                    logger.info(f"Cleared gate_1 status due to {step_id} re-execution")
                elif gate_name == "gate_1_25":
                    project.gate_1_25_passed = False
                    if "gate_1_25" in project.gate_results:
                        del project.gate_results["gate_1_25"]
                    logger.info(f"Cleared gate_1_25 status due to {step_id} re-execution")
                elif gate_name == "gate_1_5":
                    project.gate_1_5_passed = False
                    if "gate_1_5" in project.gate_results:
                        del project.gate_results["gate_1_5"]
                    logger.info(f"Cleared gate_1_5 status due to {step_id} re-execution")
                elif gate_name == "gate_1_6":
                    project.gate_1_6_passed = False
                    if "gate_1_6" in project.gate_results:
                        del project.gate_results["gate_1_6"]
                    logger.info(f"Cleared gate_1_6 status due to {step_id} re-execution")
                elif gate_name == "gate_2":
                    project.gate_2_passed = False
                    if "gate_2" in project.gate_results:
                        del project.gate_results["gate_2"]
                    logger.info(f"Cleared gate_2 status due to {step_id} re-execution")

    async def _save_project(self, project: Project) -> None:
        """
        保存项目配置

        Args:
            project: 项目对象
        """
        import json
        import aiofiles

        project_file = self.file_manager.get_project_path(project.project_id) / "project.json"

        async with aiofiles.open(project_file, 'w', encoding='utf-8') as f:
            await f.write(project.model_dump_json(indent=2))

    async def _load_project(self, project_id: str) -> Optional[Project]:
        """
        加载项目配置

        Args:
            project_id: 项目 ID

        Returns:
            Optional[Project]: 项目对象，如果不存在则返回 None
        """
        import json
        import aiofiles

        project_file = self.file_manager.get_project_path(project_id) / "project.json"

        if not project_file.exists():
            return None

        async with aiofiles.open(project_file, 'r', encoding='utf-8') as f:
            content = await f.read()
            return Project.model_validate_json(content)

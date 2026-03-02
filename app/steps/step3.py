"""
Step 3 实现
Research Execution 阶段的步骤实现

Step 3 使用两个 meta-step：
- step_3_init: 解析 PlanFrozen → WP DAG → state.json
- step_3_exec: 运行 WP 执行引擎（多 WP 编排）
"""
import logging
from typing import Dict, Any

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.services.wp_engine import WPExecutionEngine
from app.services.state_store import StateStore
from app.models.work_package import WPStatus

logger = logging.getLogger(__name__)


class Step3_Init(BaseStep):
    """Step 3 Init: 解析 PlanFrozen → WP DAG → state.json"""

    @property
    def step_id(self) -> str:
        return "step_3_init"

    @property
    def step_name(self) -> str:
        return "WP DAG Initialization"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.WP_REGISTRY

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        """
        E0: 解析 PlanFrozen → WP DAG

        Returns:
            Document: WP Registry 文档
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 检查 Gate 2 是否通过
            if not self.project.gate_2_passed:
                raise StepExecutionError("Gate 2 (Plan Freeze) must PASS before entering Step 3")

            # 加载 PlanFrozen
            plan_frozen_content = await self.load_context_with_fallback(
                step_id="step_2_5",
                doc_type=DocumentType.RESEARCH_PLAN_FROZEN
            )
            if not plan_frozen_content:
                raise StepExecutionError("Research Plan Frozen not found. Please run Step 2.5 first.")

            # 加载 Execution Order（可选）
            execution_order_content = await self.load_context_with_fallback(
                step_id="step_2_5",
                doc_type=DocumentType.EXECUTION_ORDER
            ) or ""

            # 初始化 WP 执行引擎
            engine = WPExecutionEngine(
                project_id=self.project.project_id,
                chatgpt_client=self.chatgpt_client,
                gemini_client=self.gemini_client,
                claude_client=self.claude_client,
            )

            # E0: 解析 → WP DAG
            state = await engine.initialize(plan_frozen_content, execution_order_content)

            # 生成 WP Registry 文档
            import yaml
            registry_content = "# WP Registry\n\n"
            registry_content += f"Total WPs: {len(state.wp_specs)}\n\n"
            registry_content += "## WP DAG\n\n"
            for wp_id, deps in state.wp_dag.items():
                spec = state.wp_specs[wp_id]
                dep_str = ", ".join(deps) if deps else "none"
                registry_content += f"- **{wp_id}** ({spec.name}): depends on [{dep_str}]\n"

            registry_content += "\n## WP Details\n\n"
            for wp_id, spec in state.wp_specs.items():
                registry_content += f"### {wp_id}: {spec.name}\n"
                registry_content += f"- Owner: {spec.owner}\n"
                registry_content += f"- Reviewer: {spec.reviewer}\n"
                registry_content += f"- Gate Criteria: {', '.join(spec.gate_criteria)}\n"
                registry_content += f"- Subtasks: {len(spec.subtasks)}\n\n"

            # 更新项目标志
            self.project.step3_started = True
            self.project.execution_state_ref = f"projects/{self.project.project_id}/state.json"

            # 创建并保存文档
            document = self.create_document(
                doc_type=DocumentType.WP_REGISTRY,
                content=registry_content,
                status=DocumentStatus.COMPLETED,
                inputs=["04_Research_Plan_FROZEN"],
                outputs=["05_WP_Registry", "state.json"],
            )

            await self.save_and_commit(document, f"step_3_init: WP DAG initialized with {len(state.wp_specs)} WPs")

            # 保存到 Artifact Store
            from app.models.artifact import ArtifactStatus
            await self.save_to_artifact_store(registry_content, DocumentType.WP_REGISTRY, ArtifactStatus.DRAFT)

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 3 Init failed: {e}")
            raise StepExecutionError(f"Step 3 Init failed: {e}")


class Step3_Execute(BaseStep):
    """Step 3 Execute: 运行 WP 执行引擎"""

    @property
    def step_id(self) -> str:
        return "step_3_exec"

    @property
    def step_name(self) -> str:
        return "WP Execution Engine"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.EXECUTION_STATE

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        """
        运行 WP 执行引擎：顺序执行所有 ready WPs

        Returns:
            Document: Execution State 文档
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            engine = WPExecutionEngine(
                project_id=self.project.project_id,
                chatgpt_client=self.chatgpt_client,
                gemini_client=self.gemini_client,
                claude_client=self.claude_client,
            )

            state_store = StateStore()
            if not state_store.exists(self.project.project_id):
                raise StepExecutionError("state.json not found. Please run step_3_init first.")

            # 主执行循环：顺序执行所有 WP
            max_rounds = 20  # 安全限制
            round_count = 0

            while round_count < max_rounds:
                round_count += 1
                ready_wps = await engine.get_ready_wps()

                if not ready_wps:
                    # 检查是否全部冻结
                    state = state_store.load(self.project.project_id)
                    if state.all_wps_frozen():
                        logger.info("All WPs frozen - execution complete")
                        break
                    else:
                        # 可能有 WP 在 REVIEW/ITERATING/ESCALATED 状态
                        logger.warning("No ready WPs but not all frozen - checking stuck WPs")
                        break

                # 顺序执行 ready WPs（MVP: 不并行）
                for wp_id in ready_wps:
                    logger.info(f"Round {round_count}: Executing WP {wp_id}")

                    # E1→E2: 执行
                    await engine.execute_wp(wp_id)

                    # E3: Review
                    review_result = await engine.review_wp(wp_id)

                    # 内循环: Owner fix 最多 max_iterations 轮 (§2.2.4)
                    state = state_store.load(self.project.project_id)
                    wp_spec = state.wp_specs[wp_id]

                    for _ in range(wp_spec.max_iterations):
                        state = state_store.load(self.project.project_id)
                        wp_state = state.wp_states[wp_id]
                        if wp_state.status == WPStatus.ITERATING:
                            issues = str(review_result.get("review_result", {}).get("issues", []))
                            await engine.iterate_wp(wp_id, issues)
                            review_result = await engine.review_wp(wp_id)
                        else:
                            break  # PASS/ESCALATED/RA_PENDING → 退出内循环

                    # §2.2.4: 检查是否需要 Secondary Reviewer
                    state = state_store.load(self.project.project_id)
                    wp_state = state.wp_states[wp_id]

                    if wp_state.status == WPStatus.ESCALATED:
                        # 尝试 Secondary Reviewer (2轮)
                        secondary_result = await engine.secondary_review_wp(wp_id)
                        state = state_store.load(self.project.project_id)
                        wp_state = state.wp_states[wp_id]

                    if wp_state.status == WPStatus.ESCALATED:
                        # Gemini 诊断 + HIL
                        await engine.escalate_wp(wp_id)
                        logger.warning(f"WP {wp_id} escalated - needs human intervention")

            # 生成执行状态文档
            summary = await engine.get_execution_summary()
            import json

            exec_content = "# Execution State Summary\n\n"
            exec_content += f"Total WPs: {summary['total_wps']}\n"
            exec_content += f"Frozen WPs: {summary['frozen_wps']}\n"
            exec_content += f"All Frozen: {summary['all_frozen']}\n\n"

            exec_content += "## WP Status\n\n"
            for wp_id, wp_info in summary["wps"].items():
                exec_content += f"### {wp_id}: {wp_info['name']}\n"
                exec_content += f"- Status: {wp_info['status']}\n"
                exec_content += f"- Iterations: {wp_info['iteration_count']}\n"
                exec_content += f"- Subtasks: {wp_info['subtasks_completed']} completed, {wp_info['subtasks_remaining']} remaining\n\n"

            # 更新项目标志
            if summary["all_frozen"]:
                self.project.step3_completed = True

            document = self.create_document(
                doc_type=DocumentType.EXECUTION_STATE,
                content=exec_content,
                status=DocumentStatus.COMPLETED if summary["all_frozen"] else DocumentStatus.IN_PROGRESS,
                inputs=["05_WP_Registry", "state.json"],
                outputs=["05_Execution_State"],
            )

            await self.save_and_commit(
                document,
                f"step_3_exec: {summary['frozen_wps']}/{summary['total_wps']} WPs frozen"
            )

            from app.models.artifact import ArtifactStatus
            await self.save_to_artifact_store(
                exec_content, DocumentType.EXECUTION_STATE,
                ArtifactStatus.FROZEN if summary["all_frozen"] else ArtifactStatus.DRAFT
            )

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 3 Execute failed: {e}")
            raise StepExecutionError(f"Step 3 Execute failed: {e}")

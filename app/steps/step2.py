"""
Step 2 实现
蓝图与工程分解阶段的步骤实现
"""
import logging
from pathlib import Path
from typing import Dict, Any

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.models.artifact import ArtifactStatus
from app.models.hil import QuestionType, TicketPriority
from app.prompts.step2_prompts import (
    render_step_2_0_prompt,
    render_step_2_1_prompt,
    render_step_2_2_prompt,
    render_step_2_3_prompt,
    render_step_2_4_prompt,
    render_step_2_4b_prompt,
    render_step_2_5_prompt
)

logger = logging.getLogger(__name__)


class Step2_1_FullProposal(BaseStep):
    """Step 2.1: Full Proposal / "The Constitution" (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_2_1"

    @property
    def step_name(self) -> str:
        return "Full Proposal"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.FULL_PROPOSAL

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 2.1: Full Proposal

        Returns:
            Document: Full Proposal 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 检查 Gate 1.5 是否通过
            if not self.project.gate_1_5_passed:
                raise StepExecutionError("Gate 1.5 (Killer Prior Check) must PASS before entering Step 2")

            # 获取 Selected Topic (with fallback)
            selected_topic_content = await self.load_context_with_fallback(
                step_id="step_1_2",
                doc_type=DocumentType.SELECTED_TOPIC
            )

            if not selected_topic_content:
                raise StepExecutionError("Selected Topic not found. Please run Step 1.2 first.")

            # 获取 Frozen Claims (with fallback)
            frozen_claims_content = await self.load_context_with_fallback(
                step_id="step_1_4",
                doc_type=DocumentType.CLAIMS_AND_NONCLAIMS
            )

            if not frozen_claims_content:
                raise StepExecutionError("Claims and NonClaims not found. Please run Step 1.4 first.")

            # 获取 Minimal Verification Set（可选，v7: S5a 输入）
            mvs_content = await self.load_context_with_fallback(
                step_id="step_1_4",
                doc_type=DocumentType.MINIMAL_VERIFICATION_SET
            )

            # 渲染 Prompt
            prompt = render_step_2_1_prompt(
                selected_topic_content=selected_topic_content,
                frozen_claims_content=frozen_claims_content,
                target_venue=self.project.config.target_venue,
                mvs_content=mvs_content if mvs_content else ""
            )

            # 调用 ChatGPT（PI/架构师角色）
            logger.info("Calling ChatGPT to generate Full Proposal")
            system_prompt = "You are a PI (Principal Investigator). Your role is to formalize the research proposal with rigorous definitions, methods, and evaluation plans."
            content = await self.chatgpt_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt
            )

            # 记录 AI 对话
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context=[],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "selected_topic_included": True,
                    "frozen_claims_included": True,
                    "mvs_included": bool(mvs_content),
                    "gate_1_5_checked": True
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.FULL_PROPOSAL,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.SELECTED_TOPIC.value, DocumentType.CLAIMS_AND_NONCLAIMS.value, DocumentType.MINIMAL_VERIFICATION_SET.value],
                outputs=[DocumentType.DATA_SIM_SPEC.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.FULL_PROPOSAL,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Full Proposal"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.1 failed: {e}")


class Step2_2_DataSimSpec(BaseStep):
    """Step 2.2: Data/Simulation Spec (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_2_2"

    @property
    def step_name(self) -> str:
        return "Data/Simulation Spec"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.DATA_SIM_SPEC

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 2.2: Data/Simulation Spec

        Returns:
            Document: Data/Sim Spec 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Full Proposal (with fallback)
            full_proposal_content = await self.load_context_with_fallback(
                step_id="step_2_1",
                doc_type=DocumentType.FULL_PROPOSAL
            )

            if not full_proposal_content:
                raise StepExecutionError("Full Proposal not found. Please run Step 2.1 first.")

            # 渲染 Prompt
            prompt = render_step_2_2_prompt(
                full_proposal_content=full_proposal_content
            )

            # 调用 ChatGPT（PI/架构师角色）
            logger.info("Calling ChatGPT to generate Data/Simulation Spec")
            system_prompt = "You are a PI (Principal Investigator). Your role is to translate research proposals into engineering-grade specifications."
            content = await self.chatgpt_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt
            )

            # 记录 AI 对话
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context=[],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "full_proposal_included": True
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.DATA_SIM_SPEC,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.FULL_PROPOSAL.value],
                outputs=[DocumentType.ENGINEERING_SPEC.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.DATA_SIM_SPEC,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Data/Simulation Spec"
            )

            # HIL Integration: Check for multiple dataset options
            logger.info("Checking for multiple dataset options (HIL integration)")
            dataset_options = self._extract_dataset_options(content)

            if len(dataset_options) > 1:
                logger.info(f"Found {len(dataset_options)} dataset options - requesting human selection")

                # Create HIL ticket for dataset selection
                ticket = await self.request_human_input(
                    question=f"发现 {len(dataset_options)} 个可用数据集，请选择最适合的数据集",
                    question_type=QuestionType.DECISION,
                    context={
                        "step": "Data/Simulation Spec",
                        "topic": self.project.config.topic,
                        "datasets": dataset_options
                    },
                    options=dataset_options,
                    priority=TicketPriority.HIGH,
                    blocking=False,  # Non-blocking - can proceed with default
                    timeout_hours=48.0
                )

                logger.info(f"Created HIL ticket {ticket.ticket_id} for dataset selection")
                logger.info("Step will continue without waiting for answer (non-blocking)")

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.2 failed: {e}")

    def _extract_dataset_options(self, content: str) -> list[str]:
        """
        从 Data/Sim Spec 中提取数据集选项

        查找数据集名称和描述
        """
        try:
            import re
            options = []

            # 查找 "Dataset" 或 "Data Source" 部分
            patterns = [
                r'##\s*(?:Dataset|Data\s+Source)s?\s*\n(.*?)(?=\n##|\Z)',
                r'##\s*Available\s+Datasets?\s*\n(.*?)(?=\n##|\Z)',
                r'##\s*Data\s+Options?\s*\n(.*?)(?=\n##|\Z)',
            ]

            for pattern in patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    section_content = match.group(1).strip()

                    # 提取列表项或表格行
                    list_items = re.findall(r'[-*]\s*\*?\*?([^:\n]+)', section_content)

                    for item in list_items:
                        # 清理数据集名称
                        dataset = item.strip()
                        # 移除markdown格式
                        dataset = re.sub(r'[\*_`]', '', dataset)

                        if dataset and len(dataset) > 3 and len(dataset) < 100:
                            options.append(dataset)

                    if options:
                        break

            # 如果没有找到明确的数据集列表，尝试查找常见数据集名称
            if not options:
                common_datasets = [
                    'ImageNet', 'COCO', 'CIFAR', 'MNIST', 'Pascal VOC',
                    'MS COCO', 'ADE20K', 'Cityscapes', 'KITTI', 'NuScenes',
                    'SQuAD', 'GLUE', 'SuperGLUE', 'WikiText', 'Common Crawl'
                ]

                for dataset in common_datasets:
                    if dataset.lower() in content.lower():
                        options.append(dataset)

            # 去重并限制数量
            unique_options = list(dict.fromkeys(options))[:5]  # 最多5个选项

            logger.info(f"Extracted {len(unique_options)} dataset options")
            return unique_options

        except Exception as e:
            logger.error(f"Error extracting dataset options: {e}")
            return []


class Step2_3_EngineeringDecomposition(BaseStep):
    """Step 2.3: Engineering Decomposition (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_2_3"

    @property
    def step_name(self) -> str:
        return "Engineering Decomposition"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.ENGINEERING_SPEC

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 2.3: Engineering Decomposition

        Returns:
            Document: Engineering Spec 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Full Proposal (with fallback)
            full_proposal_content = await self.load_context_with_fallback(
                step_id="step_2_1",
                doc_type=DocumentType.FULL_PROPOSAL
            )

            if not full_proposal_content:
                raise StepExecutionError("Full Proposal not found. Please run Step 2.1 first.")

            # 获取 Data/Sim Spec（可选，with fallback）
            data_spec_content = await self.load_context_with_fallback(
                step_id="step_2_2",
                doc_type=DocumentType.DATA_SIM_SPEC
            )

            # 渲染 Prompt
            prompt = render_step_2_3_prompt(
                full_proposal_content=full_proposal_content,
                data_spec_content=data_spec_content if data_spec_content else ""
            )

            # 调用 ChatGPT（PI/架构师角色）
            logger.info("Calling ChatGPT to generate Engineering Spec and Test Plan")
            system_prompt = "You are a PI (Principal Investigator). Your role is to decompose research proposals into independent, testable engineering modules."
            content = await self.chatgpt_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt
            )

            # 记录 AI 对话
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context=[],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "full_proposal_included": True,
                    "data_spec_included": bool(data_spec_content),
                    "generates_multiple_docs": True,
                    "doc_count": 2
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 解析多个文档
            documents_data = self.parse_multiple_documents(content, [
                ("DOCUMENT_1", DocumentType.ENGINEERING_SPEC),
                ("DOCUMENT_2", DocumentType.TEST_PLAN)
            ])

            # 创建并保存所有文档
            main_document = None
            for doc_type, doc_content in documents_data:
                document = self.create_document(
                    doc_type=doc_type,
                    content=doc_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.FULL_PROPOSAL.value, DocumentType.DATA_SIM_SPEC.value],
                    outputs=[DocumentType.REDTEAM_REVIEW.value]
                )

                # v6.0: Save to Artifact Store (dual-write mode)
                await self.save_to_artifact_store(
                    content=doc_content,
                    doc_type=doc_type,
                    status=ArtifactStatus.FROZEN
                )
                logger.info(f"Saved to Artifact Store: {self.step_id} - {doc_type.value}")

                # 保存并提交 (backward compatibility)
                await self.save_and_commit(
                    document=document,
                    commit_message=f"{self.step_id}: Generate {doc_type.value}"
                )

                # 第一个文档作为主文档返回
                if doc_type == DocumentType.ENGINEERING_SPEC:
                    main_document = document

            logger.info(f"Completed {self.step_name} - Generated 2 documents")
            return main_document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.3 failed: {e}")



class Step2_4_RedTeamReview(BaseStep):
    """Step 2.4: Reviewer #2 Red-Team (Gemini) - v6.0 with Controlled Red Team"""

    @property
    def step_id(self) -> str:
        return "step_2_4"

    @property
    def step_name(self) -> str:
        return "Reviewer #2 Red-Team"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.REDTEAM_REVIEW

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 2.4: Reviewer #2 Red-Team (v6.0 Controlled Red Team)

        使用 ControlledRedTeamService 进行三阶段审查：
        1. Review Packet 生成（Gemini）
        2. Executable Patch 生成（Gemini）
        3. Planner 复核（ChatGPT）

        Returns:
            Document: Red Team Review 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Full Proposal (with fallback)
            full_proposal_content = await self.load_context_with_fallback(
                step_id="step_2_1",
                doc_type=DocumentType.FULL_PROPOSAL
            )

            if not full_proposal_content:
                raise StepExecutionError("Full Proposal not found. Please run Step 2.1 first.")

            # 获取 Engineering Spec (with fallback)
            engineering_spec_content = await self.load_context_with_fallback(
                step_id="step_2_3",
                doc_type=DocumentType.ENGINEERING_SPEC
            )

            if not engineering_spec_content:
                raise StepExecutionError("Engineering Spec not found. Please run Step 2.3 first.")

            # v7: 加载额外的 4 个输入文档（S6 Review Packet）
            frozen_claims_content = await self.load_context_with_fallback(
                step_id="step_1_4",
                doc_type=DocumentType.CLAIMS_AND_NONCLAIMS
            )

            mvs_content = await self.load_context_with_fallback(
                step_id="step_1_4",
                doc_type=DocumentType.MINIMAL_VERIFICATION_SET
            )

            test_plan_content = await self.load_context_with_fallback(
                step_id="step_2_3",
                doc_type=DocumentType.TEST_PLAN
            )

            killer_prior_content = await self.load_context_with_fallback(
                step_id="step_1_3",
                doc_type=DocumentType.KILLER_PRIOR_CHECK
            )

            # 合并文档内容（v7: 6 个输入文档）
            combined_content = f"""# Frozen Claims and NonClaims

{frozen_claims_content if frozen_claims_content else "[Not available]"}

---

# Minimal Verification Set

{mvs_content if mvs_content else "[Not available]"}

---

# Full Proposal

{full_proposal_content}

---

# Engineering Specification

{engineering_spec_content}

---

# Test Plan

{test_plan_content if test_plan_content else "[Not available]"}

---

# Killer Prior Check (Top 5 Prior)

{killer_prior_content if killer_prior_content else "[Not available]"}
"""

            # v6.0: 使用 Controlled Red Team Service
            logger.info("Running Controlled Red Team (3-phase review)")
            from app.services.red_team_service import get_red_team_service

            red_team_service = get_red_team_service()

            # 运行完整的 Red Team 流程
            red_team_result = await red_team_service.run_red_team(
                document_id=self.project.project_id,
                document_type="Research Proposal + Engineering Spec",
                document_content=combined_content,
                review_criteria=[
                    "Logic and coherence",
                    "Evidence sufficiency",
                    "Feasibility and practicality",
                    "Novelty and impact",
                    f"Alignment with {self.project.config.target_venue} standards"
                ]
            )

            logger.info(f"Red Team completed: {len(red_team_result.review_packet.issues)} issues, "
                       f"{len(red_team_result.patches)} patches, "
                       f"{sum(1 for r in red_team_result.patch_reviews if r.approved)} approved")

            # 格式化 Red Team 结果为 Markdown
            content = self._format_red_team_result(red_team_result)

            # 保存 Review Packet 和 Patches 到文件
            await self._save_review_packet(red_team_result.review_packet)
            await self._save_patches(red_team_result.patches, red_team_result.patch_reviews)

            # 记录 AI 对话（记录完整流程）
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt="Controlled Red Team (3-phase review)",
                user_prompt=f"Review criteria: {red_team_result.review_packet.reviewer_role}",
                context=[full_proposal_content[:500], engineering_spec_content[:500]],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "controlled_red_team": True,
                    "issues_count": len(red_team_result.review_packet.issues),
                    "patches_count": len(red_team_result.patches),
                    "approved_patches": sum(1 for r in red_team_result.patch_reviews if r.approved),
                    "execution_time": red_team_result.execution_time
                }
            )

            if not content:
                raise StepExecutionError("Red Team returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.REDTEAM_REVIEW,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[
                    DocumentType.CLAIMS_AND_NONCLAIMS.value,
                    DocumentType.MINIMAL_VERIFICATION_SET.value,
                    DocumentType.FULL_PROPOSAL.value,
                    DocumentType.ENGINEERING_SPEC.value,
                    DocumentType.TEST_PLAN.value,
                    DocumentType.KILLER_PRIOR_CHECK.value
                ],
                outputs=[DocumentType.RESEARCH_PLAN_FROZEN.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.REDTEAM_REVIEW,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Perform Controlled Red Team Review (v6.0)"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.4 failed: {e}")

    def _format_red_team_result(self, result) -> str:
        """
        格式化 Red Team 结果为 Markdown

        Args:
            result: RedTeamResult 对象

        Returns:
            str: Markdown 格式的报告
        """
        from app.services.red_team_service import ReviewSeverity

        # 按严重性分组问题
        critical_issues = [i for i in result.review_packet.issues if i.severity == ReviewSeverity.CRITICAL]
        major_issues = [i for i in result.review_packet.issues if i.severity == ReviewSeverity.MAJOR]
        minor_issues = [i for i in result.review_packet.issues if i.severity == ReviewSeverity.MINOR]
        suggestions = [i for i in result.review_packet.issues if i.severity == ReviewSeverity.SUGGESTION]

        # 统计批准的 patches
        approved_patches = [r for r in result.patch_reviews if r.approved]
        rejected_patches = [r for r in result.patch_reviews if not r.approved]

        # 生成 Markdown
        content = f"""# Controlled Red Team Review

**Document ID**: {result.review_packet.document_id}
**Document Type**: {result.review_packet.document_type}
**Reviewer Role**: {result.review_packet.reviewer_role}
**Review Date**: {result.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Execution Time**: {result.execution_time:.2f} seconds

---

## Executive Summary

{result.review_packet.overall_assessment}

**Issues Found**: {len(result.review_packet.issues)} total
- 🔴 Critical: {len(critical_issues)}
- 🟠 Major: {len(major_issues)}
- 🟡 Minor: {len(minor_issues)}
- 💡 Suggestions: {len(suggestions)}

**Patches Generated**: {len(result.patches)}
- ✅ Approved: {len(approved_patches)}
- ❌ Rejected: {len(rejected_patches)}

---

## Top Recommendations

"""

        for i, rec in enumerate(result.review_packet.recommendations, 1):
            content += f"{i}. {rec}\n"

        content += "\n---\n\n"

        # Critical Issues
        if critical_issues:
            content += "## 🔴 Critical Issues (Must Fix)\n\n"
            for issue in critical_issues:
                content += f"### {issue.issue_id}: {issue.category.upper()}\n\n"
                content += f"**Location**: {issue.location}\n\n"
                content += f"**Description**: {issue.description}\n\n"
                content += f"**Rationale**: {issue.rationale}\n\n"
                content += f"**Suggested Fix**: {issue.suggested_fix}\n\n"

                # 查找对应的 patch
                patch = next((p for p in result.patches if p.issue_id == issue.issue_id), None)
                if patch:
                    review = next((r for r in result.patch_reviews if r.patch_id == patch.patch_id), None)
                    status = "✅ Approved" if review and review.approved else "❌ Rejected"
                    content += f"**Patch Status**: {status} (Patch ID: {patch.patch_id})\n\n"

                content += "---\n\n"

        # Major Issues
        if major_issues:
            content += "## 🟠 Major Issues (Should Fix)\n\n"
            for issue in major_issues:
                content += f"### {issue.issue_id}: {issue.category.upper()}\n\n"
                content += f"**Location**: {issue.location}\n\n"
                content += f"**Description**: {issue.description}\n\n"
                content += f"**Rationale**: {issue.rationale}\n\n"
                content += f"**Suggested Fix**: {issue.suggested_fix}\n\n"

                # 查找对应的 patch
                patch = next((p for p in result.patches if p.issue_id == issue.issue_id), None)
                if patch:
                    review = next((r for r in result.patch_reviews if r.patch_id == patch.patch_id), None)
                    status = "✅ Approved" if review and review.approved else "❌ Rejected"
                    content += f"**Patch Status**: {status} (Patch ID: {patch.patch_id})\n\n"

                content += "---\n\n"

        # Minor Issues
        if minor_issues:
            content += "## 🟡 Minor Issues (Optional Fix)\n\n"
            for issue in minor_issues:
                content += f"### {issue.issue_id}: {issue.category.upper()}\n\n"
                content += f"**Location**: {issue.location}\n\n"
                content += f"**Description**: {issue.description}\n\n"
                content += f"**Suggested Fix**: {issue.suggested_fix}\n\n"
                content += "---\n\n"

        # Suggestions
        if suggestions:
            content += "## 💡 Suggestions\n\n"
            for issue in suggestions:
                content += f"### {issue.issue_id}: {issue.category.upper()}\n\n"
                content += f"**Description**: {issue.description}\n\n"
                content += f"**Suggestion**: {issue.suggested_fix}\n\n"
                content += "---\n\n"

        # Patch Details
        if result.patches:
            content += "## 📋 Executable Patches\n\n"
            for patch in result.patches:
                review = next((r for r in result.patch_reviews if r.patch_id == patch.patch_id), None)
                status = "✅ Approved" if review and review.approved else "❌ Rejected"

                content += f"### Patch {patch.patch_id} ({status})\n\n"
                content += f"**Issue ID**: {patch.issue_id}\n"
                content += f"**Operations**: {len(patch.operations)}\n\n"

                for i, op in enumerate(patch.operations, 1):
                    content += f"#### Operation {i}: {op.operation_type.upper()}\n\n"
                    content += f"**Target**: {op.target_location}\n\n"
                    if op.old_content:
                        content += f"**Old Content**:\n```\n{op.old_content[:200]}...\n```\n\n"
                    content += f"**New Content**:\n```\n{op.new_content[:200]}...\n```\n\n"
                    content += f"**Rationale**: {op.rationale}\n\n"

                if review:
                    content += f"**Planner Review**: {review.reviewer_comments}\n\n"
                    if review.modifications:
                        content += "**Modifications Suggested**:\n"
                        for mod in review.modifications:
                            content += f"- {mod}\n"
                        content += "\n"

                content += "---\n\n"

        # Footer
        content += f"""
---

## Review Metadata

- **Total Issues**: {len(result.review_packet.issues)}
- **Patches Generated**: {len(result.patches)}
- **Patches Approved**: {len(approved_patches)}
- **Execution Time**: {result.execution_time:.2f} seconds
- **Review Packet Saved**: `red_team/review_packets/{result.review_packet.document_id}.json`
- **Patches Saved**: `red_team/patches/{result.review_packet.document_id}/`

**Note**: This is a Controlled Red Team review. Only issues with approved executable patches are considered blocking.
"""

        return content

    async def _save_review_packet(self, review_packet) -> None:
        """
        保存 Review Packet 到文件

        Args:
            review_packet: ReviewPacket 对象
        """
        import json
        from pathlib import Path
        from app.utils.file_manager import FileManager

        # 获取项目目录
        file_manager = FileManager()
        project_path = file_manager.get_project_path(self.project.project_id)

        # 创建目录
        red_team_dir = project_path / "red_team" / "review_packets"
        red_team_dir.mkdir(parents=True, exist_ok=True)

        # 保存 JSON
        json_path = red_team_dir / f"{self.project.project_id}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(review_packet.model_dump(), f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"Saved Review Packet to: {json_path}")

        # 保存 Markdown（人类可读）
        md_path = red_team_dir / f"{self.project.project_id}.md"
        md_content = f"""# Review Packet: {review_packet.document_id}

**Document Type**: {review_packet.document_type}
**Reviewer**: {review_packet.reviewer_role}
**Created**: {review_packet.created_at.strftime('%Y-%m-%d %H:%M:%S')}

## Overall Assessment

{review_packet.overall_assessment}

## Issues ({len(review_packet.issues)})

"""
        for issue in review_packet.issues:
            md_content += f"""
### {issue.issue_id} - {issue.severity.value.upper()}

**Category**: {issue.category}
**Location**: {issue.location}

**Description**: {issue.description}

**Rationale**: {issue.rationale}

**Suggested Fix**: {issue.suggested_fix}

---
"""

        md_content += "\n## Recommendations\n\n"
        for i, rec in enumerate(review_packet.recommendations, 1):
            md_content += f"{i}. {rec}\n"

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        logger.info(f"Saved Review Packet (Markdown) to: {md_path}")

    async def _save_patches(self, patches, patch_reviews) -> None:
        """
        保存 Patches 到文件

        Args:
            patches: ExecutablePatch 列表
            patch_reviews: PatchReview 列表
        """
        import json
        from pathlib import Path
        from app.utils.file_manager import FileManager

        # 获取项目目录
        file_manager = FileManager()
        project_path = file_manager.get_project_path(self.project.project_id)

        # 创建目录
        patches_dir = project_path / "red_team" / "patches" / self.project.project_id
        patches_dir.mkdir(parents=True, exist_ok=True)

        # 保存每个 patch
        for patch in patches:
            # 查找对应的 review
            review = next((r for r in patch_reviews if r.patch_id == patch.patch_id), None)

            # 保存 JSON
            json_path = patches_dir / f"{patch.patch_id}.json"
            patch_data = patch.model_dump()
            if review:
                patch_data['review'] = review.model_dump()

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(patch_data, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Saved Patch to: {json_path}")

            # 保存 Markdown（人类可读）
            md_path = patches_dir / f"{patch.patch_id}.md"
            status = "✅ Approved" if review and review.approved else "❌ Rejected"
            md_content = f"""# Patch: {patch.patch_id} ({status})

**Issue ID**: {patch.issue_id}
**Document ID**: {patch.document_id}
**Created**: {patch.created_at.strftime('%Y-%m-%d %H:%M:%S')}

## Operations ({len(patch.operations)})

"""
            for i, op in enumerate(patch.operations, 1):
                md_content += f"""
### Operation {i}: {op.operation_type.upper()}

**Target Location**: {op.target_location}

**Old Content**:
```
{op.old_content if op.old_content else 'N/A'}
```

**New Content**:
```
{op.new_content}
```

**Rationale**: {op.rationale}

---
"""

            md_content += "\n## Validation Rules\n\n"
            for rule in patch.validation_rules:
                md_content += f"- {rule}\n"

            if review:
                md_content += f"\n## Planner Review\n\n"
                md_content += f"**Status**: {status}\n\n"
                md_content += f"**Comments**: {review.reviewer_comments}\n\n"
                if review.modifications:
                    md_content += "**Modifications**:\n"
                    for mod in review.modifications:
                        md_content += f"- {mod}\n"

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(md_content)

            logger.info(f"Saved Patch (Markdown) to: {md_path}")

        # 保存汇总文件
        summary_path = patches_dir / "summary.md"
        summary_content = f"""# Patches Summary

**Project ID**: {self.project.project_id}
**Total Patches**: {len(patches)}
**Approved**: {sum(1 for r in patch_reviews if r.approved)}
**Rejected**: {sum(1 for r in patch_reviews if not r.approved)}

## Patch List

"""
        for patch in patches:
            review = next((r for r in patch_reviews if r.patch_id == patch.patch_id), None)
            status = "✅" if review and review.approved else "❌"
            summary_content += f"- {status} **{patch.patch_id}** (Issue: {patch.issue_id}, Operations: {len(patch.operations)})\n"

        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_content)

        logger.info(f"Saved Patches Summary to: {summary_path}")


class Step2_5_PlanFreeze(BaseStep):
    """Step 2.5: Plan Freeze Package (ChatGPT) - Gate 2"""

    @property
    def step_id(self) -> str:
        return "step_2_5"

    @property
    def step_name(self) -> str:
        return "Plan Freeze Package"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.RESEARCH_PLAN_FROZEN

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 2.5: Plan Freeze Package

        Returns:
            Document: Research Plan FROZEN 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取所有必需的文档 (with fallback)
            frozen_claims_content = await self.load_context_with_fallback(
                step_id="step_1_4",
                doc_type=DocumentType.CLAIMS_AND_NONCLAIMS
            )

            full_proposal_content = await self.load_context_with_fallback(
                step_id="step_2_1",
                doc_type=DocumentType.FULL_PROPOSAL
            )

            engineering_spec_content = await self.load_context_with_fallback(
                step_id="step_2_3",
                doc_type=DocumentType.ENGINEERING_SPEC
            )

            redteam_review_content = await self.load_context_with_fallback(
                step_id="step_2_4",
                doc_type=DocumentType.REDTEAM_REVIEW
            )

            # 检查所有文档是否存在
            if not all([frozen_claims_content, full_proposal_content, engineering_spec_content, redteam_review_content]):
                raise StepExecutionError("Missing required documents. Please complete all previous steps.")

            # 渲染 Prompt
            prompt = render_step_2_5_prompt(
                full_proposal_content=full_proposal_content,
                engineering_spec_content=engineering_spec_content,
                redteam_content=redteam_review_content,
                frozen_claims_content=frozen_claims_content
            )

            # 调用 ChatGPT（PI/架构师角色）
            logger.info("Calling ChatGPT to generate Plan Freeze Package")
            system_prompt = "You are a PI (Principal Investigator). Your role is to create the final frozen research plan that locks all specifications."
            content = await self.chatgpt_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt
            )

            # 记录 AI 对话
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context=[],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "frozen_claims_included": True,
                    "full_proposal_included": True,
                    "engineering_spec_included": True,
                    "redteam_review_included": True,
                    "gate_check": "Gate 2"
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.RESEARCH_PLAN_FROZEN,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[
                    DocumentType.CLAIMS_AND_NONCLAIMS.value,
                    DocumentType.FULL_PROPOSAL.value,
                    DocumentType.ENGINEERING_SPEC.value,
                    DocumentType.REDTEAM_REVIEW.value
                ],
                outputs=[]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.RESEARCH_PLAN_FROZEN,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Research Plan FROZEN (Gate 2)"
            )

            # ── Phase C: Generate WorkPlan YAML (non-blocking) ──
            try:
                from app.services.workplan import WorkPlanLoader
                from app.config import settings as _settings

                # Load Data/Sim Spec if available
                data_sim_content = await self.load_context_with_fallback(
                    step_id="step_2_2",
                    doc_type=DocumentType.DATA_SIM_SPEC,
                ) or ""

                workplan = WorkPlanLoader.from_plan_freeze(
                    program_spec=full_proposal_content,
                    data_sim_spec=data_sim_content,
                    eng_decomp=engineering_spec_content,
                    project_id=self.project.project_id,
                )

                wp_path = str(
                    Path(_settings.projects_path)
                    / self.project.project_id
                    / "workplan.yaml"
                )
                WorkPlanLoader.dump(workplan, wp_path)

                errors = WorkPlanLoader.validate(workplan)
                if errors:
                    logger.warning(
                        "WorkPlan validation warnings: %s", "; ".join(errors)
                    )
                else:
                    logger.info("WorkPlan generated and validated: %s", wp_path)
            except Exception as wp_err:
                logger.warning(
                    "WorkPlan generation failed (non-blocking): %s", wp_err
                )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.5 failed: {e}")


class Step2_0_FigureTableList(BaseStep):
    """Step 2.0: Figure/Table List (ChatGPT) - v4.0 NEW"""

    @property
    def step_id(self) -> str:
        return "step_2_0"

    @property
    def step_name(self) -> str:
        return "Figure/Table List"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.FIGURE_TABLE_LIST

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 2.0: Figure/Table List
        在编写完整提案前，先规划所有图表

        Returns:
            Document: Figure/Table List 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Frozen Claims (with fallback)
            frozen_claims_content = await self.load_context_with_fallback(
                step_id="step_1_4",
                doc_type=DocumentType.CLAIMS_AND_NONCLAIMS
            )

            if not frozen_claims_content:
                raise StepExecutionError("Claims and NonClaims not found. Please run Step 1.4 first.")

            # 渲染 Prompt
            prompt = render_step_2_0_prompt(
                frozen_claims_content=frozen_claims_content,
                target_venue=self.project.config.target_venue
            )

            # 调用 ChatGPT（PI 角色）
            logger.info("Calling ChatGPT to generate Figure/Table List")
            system_prompt = f"You are the PI planning the publication. Your role is to design the figure/table strategy that will most effectively communicate the claims to {self.project.config.target_venue} reviewers."
            content = await self.chatgpt_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt
            )

            # 记录 AI 对话
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt=system_prompt,
                user_prompt=prompt,
                context=[],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "frozen_claims_included": True,
                    "v4_new_step": True
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.FIGURE_TABLE_LIST,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.CLAIMS_AND_NONCLAIMS.value],
                outputs=[DocumentType.FULL_PROPOSAL.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.FIGURE_TABLE_LIST,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Figure/Table List"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.0 failed: {e}")


class Step2_4b_PatchPropagation(BaseStep):
    """Step 2.4b: Patch Propagation - v6.0 with Automatic Patch Application"""

    @property
    def step_id(self) -> str:
        return "step_2_4b"

    @property
    def step_name(self) -> str:
        return "Patch Propagation"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.PATCH_DIFF

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 2.4b: Patch Propagation (v6.0 Automatic Application)

        加载 Review Packet 和 Patches，应用批准的 patches 到目标文档

        Returns:
            Document: Patch Diff 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 1. 加载 Review Packet 和 Patches
            logger.info("Loading Review Packet and Patches from files")
            review_packet, patches, patch_reviews = await self._load_red_team_results()

            if not patches:
                logger.warning("No patches found, skipping patch application")
                # 生成空的 Patch Diff 文档
                content = self._generate_empty_patch_diff()
                document = self.create_document(
                    doc_type=DocumentType.PATCH_DIFF,
                    content=content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.REDTEAM_REVIEW.value],
                    outputs=[]
                )
                await self.save_and_commit(
                    document=document,
                    commit_message=f"{self.step_id}: No patches to apply"
                )
                return document

            # 2. 筛选批准的 patches
            approved_patches = [
                patch for patch in patches
                if any(r.patch_id == patch.patch_id and r.approved for r in patch_reviews)
            ]

            logger.info(f"Found {len(approved_patches)} approved patches out of {len(patches)} total")

            if not approved_patches:
                logger.warning("No approved patches, skipping patch application")
                content = self._generate_no_approved_patches_diff(patches, patch_reviews)
                document = self.create_document(
                    doc_type=DocumentType.PATCH_DIFF,
                    content=content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.REDTEAM_REVIEW.value],
                    outputs=[]
                )
                await self.save_and_commit(
                    document=document,
                    commit_message=f"{self.step_id}: No approved patches to apply"
                )
                return document

            # 3. 加载目标文档
            logger.info("Loading target documents")
            full_proposal_content = await self.load_context_with_fallback(
                step_id="step_2_1",
                doc_type=DocumentType.FULL_PROPOSAL
            )

            engineering_spec_content = await self.load_context_with_fallback(
                step_id="step_2_3",
                doc_type=DocumentType.ENGINEERING_SPEC
            )

            if not full_proposal_content or not engineering_spec_content:
                raise StepExecutionError("Target documents not found")

            # 合并文档内容
            combined_content = f"""# Full Proposal

{full_proposal_content}

---

# Engineering Specification

{engineering_spec_content}
"""

            # 4. 应用 patches
            logger.info(f"Applying {len(approved_patches)} approved patches")
            from app.services.red_team_service import get_red_team_service
            red_team_service = get_red_team_service()

            updated_content = combined_content
            all_apply_logs = []

            for patch in approved_patches:
                try:
                    updated_content, apply_log = await red_team_service.apply_patch(
                        patch, updated_content
                    )
                    all_apply_logs.append({
                        "patch_id": patch.patch_id,
                        "issue_id": patch.issue_id,
                        "log": apply_log
                    })
                    logger.info(f"Applied patch {patch.patch_id}: {len(apply_log)} operations")
                except Exception as e:
                    logger.error(f"Failed to apply patch {patch.patch_id}: {e}")
                    all_apply_logs.append({
                        "patch_id": patch.patch_id,
                        "issue_id": patch.issue_id,
                        "log": [f"❌ Failed to apply patch: {str(e)}"]
                    })

            # 5. 生成 Patch Diff 文档
            content = self._generate_patch_diff(
                original_content=combined_content,
                updated_content=updated_content,
                approved_patches=approved_patches,
                apply_logs=all_apply_logs,
                review_packet=review_packet
            )

            # 6. 保存更新后的文档（可选）
            # 注意：这里不直接覆盖原文档，而是生成 diff 报告
            # 用户可以根据 diff 报告手动应用更改

            # 记录 AI 对话（记录 patch 应用过程）
            self.log_ai_conversation(
                model="system",
                system_prompt="Automatic Patch Application",
                user_prompt=f"Apply {len(approved_patches)} approved patches",
                context=[],
                response=content,
                metadata={
                    "step_name": self.step_name,
                    "patches_applied": len(approved_patches),
                    "total_patches": len(patches),
                    "apply_logs": all_apply_logs
                }
            )

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.PATCH_DIFF,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.REDTEAM_REVIEW.value, DocumentType.FULL_PROPOSAL.value, DocumentType.ENGINEERING_SPEC.value],
                outputs=[]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.PATCH_DIFF,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Apply {len(approved_patches)} approved patches (v6.0)"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 2.4b failed: {e}")

    async def _load_red_team_results(self):
        """
        加载 Review Packet 和 Patches 从文件

        Returns:
            tuple: (review_packet, patches, patch_reviews)
        """
        import json
        from pathlib import Path
        from app.utils.file_manager import FileManager
        from app.services.red_team_service import ReviewPacket, ExecutablePatch, PatchReview

        # 获取项目目录
        file_manager = FileManager()
        project_path = file_manager.get_project_path(self.project.project_id)

        # 加载 Review Packet
        review_packet_path = project_path / "red_team" / "review_packets" / f"{self.project.project_id}.json"
        if not review_packet_path.exists():
            raise StepExecutionError(f"Review Packet not found: {review_packet_path}")

        with open(review_packet_path, 'r', encoding='utf-8') as f:
            review_packet_data = json.load(f)
            review_packet = ReviewPacket(**review_packet_data)

        logger.info(f"Loaded Review Packet: {len(review_packet.issues)} issues")

        # 加载 Patches
        patches_dir = project_path / "red_team" / "patches" / self.project.project_id
        if not patches_dir.exists():
            logger.warning(f"Patches directory not found: {patches_dir}")
            return review_packet, [], []

        patches = []
        patch_reviews = []

        for patch_file in patches_dir.glob("patch_*.json"):
            with open(patch_file, 'r', encoding='utf-8') as f:
                patch_data = json.load(f)

                # 提取 review（如果存在）
                review_data = patch_data.pop('review', None)

                # 创建 Patch 对象
                patch = ExecutablePatch(**patch_data)
                patches.append(patch)

                # 创建 Review 对象
                if review_data:
                    review = PatchReview(**review_data)
                    patch_reviews.append(review)

        logger.info(f"Loaded {len(patches)} patches with {len(patch_reviews)} reviews")

        return review_packet, patches, patch_reviews

    def _generate_empty_patch_diff(self) -> str:
        """生成空的 Patch Diff 文档"""
        return """# Patch Diff Report

**Project ID**: {self.project.project_id}
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

No patches were generated by the Red Team review.

**Status**: No changes applied
"""

    def _generate_no_approved_patches_diff(self, patches, patch_reviews) -> str:
        """生成无批准 patches 的 Diff 文档"""
        from datetime import datetime

        content = f"""# Patch Diff Report

**Project ID**: {self.project.project_id}
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

**Total Patches**: {len(patches)}
**Approved Patches**: 0
**Rejected Patches**: {len(patches)}

No patches were approved by the Planner. No changes applied.

## Rejected Patches

"""
        for patch in patches:
            review = next((r for r in patch_reviews if r.patch_id == patch.patch_id), None)
            content += f"- **{patch.patch_id}** (Issue: {patch.issue_id})\n"
            if review:
                content += f"  - Reason: {review.reviewer_comments}\n"

        return content

    def _generate_patch_diff(
        self,
        original_content: str,
        updated_content: str,
        approved_patches,
        apply_logs,
        review_packet
    ) -> str:
        """
        生成 Patch Diff 文档

        Args:
            original_content: 原始文档内容
            updated_content: 更新后的文档内容
            approved_patches: 批准的 patches 列表
            apply_logs: 应用日志列表
            review_packet: Review Packet 对象

        Returns:
            str: Patch Diff Markdown 文档
        """
        from datetime import datetime
        import difflib

        # 生成 diff
        original_lines = original_content.splitlines()
        updated_lines = updated_content.splitlines()

        diff = list(difflib.unified_diff(
            original_lines,
            updated_lines,
            fromfile='Original',
            tofile='Updated',
            lineterm=''
        ))

        # 统计修改
        additions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

        # 生成文档
        content = f"""# Patch Diff Report

**Project ID**: {self.project.project_id}
**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Review Packet**: {review_packet.document_id}

---

## Executive Summary

**Total Issues**: {len(review_packet.issues)}
**Patches Generated**: {len(approved_patches) + len([log for log in apply_logs if 'Failed' in str(log)])}
**Patches Applied**: {len(approved_patches)}
**Lines Added**: {additions}
**Lines Deleted**: {deletions}
**Net Change**: {additions - deletions} lines

---

## Applied Patches

"""

        for i, patch in enumerate(approved_patches, 1):
            # 查找对应的 issue
            issue = next((iss for iss in review_packet.issues if iss.issue_id == patch.issue_id), None)

            # 查找应用日志
            log_entry = next((log for log in apply_logs if log['patch_id'] == patch.patch_id), None)

            content += f"""### Patch {i}: {patch.patch_id}

**Issue ID**: {patch.issue_id}
**Severity**: {issue.severity.value if issue else 'Unknown'}
**Category**: {issue.category if issue else 'Unknown'}

**Operations**: {len(patch.operations)}

"""

            if log_entry:
                content += "**Application Log**:\n"
                for log_line in log_entry['log']:
                    content += f"- {log_line}\n"
                content += "\n"

            content += "**Operations Detail**:\n\n"
            for j, op in enumerate(patch.operations, 1):
                content += f"#### Operation {j}: {op.operation_type.upper()}\n\n"
                content += f"**Target**: {op.target_location}\n\n"
                if op.old_content:
                    content += f"**Old Content** ({len(op.old_content)} chars):\n```\n{op.old_content[:200]}{'...' if len(op.old_content) > 200 else ''}\n```\n\n"
                content += f"**New Content** ({len(op.new_content)} chars):\n```\n{op.new_content[:200]}{'...' if len(op.new_content) > 200 else ''}\n```\n\n"
                content += f"**Rationale**: {op.rationale}\n\n"

            content += "---\n\n"

        # 添加 Unified Diff
        content += "## Unified Diff\n\n"
        content += "```diff\n"
        content += "\n".join(diff[:100])  # 限制 diff 长度
        if len(diff) > 100:
            content += f"\n\n... ({len(diff) - 100} more lines)\n"
        content += "\n```\n\n"

        # 添加元数据
        content += f"""---

## Metadata

- **Original Content**: {len(original_content)} characters
- **Updated Content**: {len(updated_content)} characters
- **Change**: {len(updated_content) - len(original_content):+d} characters
- **Patches Applied**: {len(approved_patches)}
- **Successful Operations**: {sum(len([l for l in log['log'] if l.startswith('✅')]) for log in apply_logs)}
- **Failed Operations**: {sum(len([l for l in log['log'] if l.startswith('❌')]) for log in apply_logs)}

**Note**: This diff shows the changes made by applying approved Red Team patches. Review carefully before committing.
"""

        return content


"""
Step 0 实现
项目启动阶段的步骤实现
"""
import logging
from typing import Dict, Any

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.prompts.step0_prompts import render_step_0_1_prompt, render_step_0_2_prompt

logger = logging.getLogger(__name__)


class Step0_1_IntakeCard(BaseStep):
    """Step 0.1: 生成 Project Intake Card"""

    @property
    def step_id(self) -> str:
        return "step_0_1"

    @property
    def step_name(self) -> str:
        return "Project Intake Card"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.PROJECT_INTAKE_CARD

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 0.1: 生成 Project Intake Card

        Returns:
            Document: Project Intake Card 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 渲染 Prompt
            prompt = render_step_0_1_prompt(
                topic=self.project.config.topic,
                target_venue=self.project.config.target_venue,
                research_type=self.project.config.research_type.value,
                data_status=self.project.config.data_status.value,
                hard_constraints=self.project.config.hard_constraints,
                time_budget=self.project.config.time_budget,
                keywords=self.project.config.keywords,
                rigor_profile=self.project.config.rigor_profile or "top_journal"  # v6.0 NEW
            )

            # 暂时使用 Gemini 替代 ChatGPT（因为 TokHub 的 ChatGPT 模型权限问题）
            # IMPORTANT: Use DISABLED mode for Step 0.1 because it requires YAML front-matter (format conflict with Agentic Wrapper)
            logger.info("Calling Gemini to generate Project Intake Card (Agentic Wrapper meta_tail for YAML format)")

            system_prompt = "You are an experienced research PI and paper architect. Your task is to create a comprehensive Project Intake Card for a new research project."

            try:
                content = await self.gemini_client.chat(
                    prompt=prompt,
                    context=[],
                    system_prompt=system_prompt,
                    max_tokens=8192,  # 增加输出空间以支持长篇输出
                    wrapper_mode="meta_tail"  # meta_tail: YAML format + quality control without conflict
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
                        "agentic_wrapper_mode": "meta_tail",
                        "max_tokens": 8192,
                        "reason": "meta_tail preserves YAML format + quality control"
                    }
                )
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                raise

            # 检查内容
            if not content:
                raise StepExecutionError("Gemini returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.PROJECT_INTAKE_CARD,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[],
                outputs=[DocumentType.VENUE_TASTE_NOTES.value]
            )

            # 双写模式：同时保存到 Artifact Store 和文件系统
            # 1. 保存到 Artifact Store (v6.0 NEW)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.PROJECT_INTAKE_CARD
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 2. 保存到文件系统（保持兼容性）
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Project Intake Card"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 0.1 failed: {e}")


class Step0_2_VenueTaste(BaseStep):
    """Step 0.2: 生成 Venue Taste Notes"""

    @property
    def step_id(self) -> str:
        return "step_0_2"

    @property
    def step_name(self) -> str:
        return "Venue Taste Primer"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.VENUE_TASTE_NOTES

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 0.2: 生成 Venue Taste Notes

        Returns:
            Document: Venue Taste Notes 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Project Intake Card 作为上下文
            # 使用 load_context_with_fallback 优先从 Artifact Store 读取 (v6.0 NEW)
            intake_card_content = await self.load_context_with_fallback(
                step_id="step_0_1",
                doc_type=DocumentType.PROJECT_INTAKE_CARD
            )

            if not intake_card_content:
                raise StepExecutionError("Project Intake Card not found. Please run Step 0.1 first.")

            # 从向量数据库检索上下文
            context = await self.retrieve_context(
                query=f"venue analysis {self.project.config.target_venue}",
                top_k=2
            )

            # 渲染 Prompt
            prompt = render_step_0_2_prompt(
                topic=self.project.config.topic,
                target_venue=self.project.config.target_venue
            )

            # 添加 Intake Card 内容到 Prompt
            full_prompt = f"{prompt}\n\n## Project Intake Card:\n{intake_card_content}"

            # 调用 Gemini
            # IMPORTANT: Use DISABLED mode for Step 0.2 because output is long (>5000 chars)
            logger.info("Calling Gemini to generate Venue Taste Notes (Agentic Wrapper meta_tail for long output)")

            try:
                response = await self.gemini_client.chat(
                    prompt=full_prompt,
                    context=context,
                    max_tokens=8192,  # 增加输出空间以支持长篇输出
                    wrapper_mode="meta_tail"  # meta_tail: long output + quality control
                )

                # 记录 AI 对话
                self.log_ai_conversation(
                    model=self.ai_model,
                    system_prompt=None,  # Gemini 使用默认 system prompt
                    user_prompt=full_prompt,
                    context=context,
                    response=response,
                    metadata={
                        "step_name": self.step_name,
                        "intake_card_included": True,
                        "agentic_wrapper_mode": "meta_tail",
                        "max_tokens": 8192,
                        "reason": "meta_tail for long output + quality control"
                    }
                )
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                raise

            if not response:
                raise StepExecutionError("Gemini returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.VENUE_TASTE_NOTES,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.PROJECT_INTAKE_CARD.value],
                outputs=[]
            )

            # 双写模式：同时保存到 Artifact Store 和文件系统
            # 1. 保存到 Artifact Store (v6.0 NEW)
            await self.save_to_artifact_store(
                content=response,
                doc_type=DocumentType.VENUE_TASTE_NOTES
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 2. 保存到文件系统（保持兼容性）
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Venue Taste Notes"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 0.2 failed: {e}")

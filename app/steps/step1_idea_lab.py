"""
Step 1 Idea-Lab Plugin
v7.1 S1-2: 高温发散生成候选 idea

仅在 enable_idea_lab=True 时执行。
输入: 01_C_Literature_Matrix.md
输出: 01_D_Idea_Lab_Candidates.md
"""
import logging
from typing import Optional

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.prompts.step1_prompts import IDEA_LAB_GEMINI_PROMPT

logger = logging.getLogger(__name__)


class Step1_IdeaLab(BaseStep):
    """Step 1.3b Idea-Lab: Gemini 高温发散生成候选 idea"""

    @property
    def step_id(self) -> str:
        return "step_1_3b_idea_lab"

    @property
    def step_name(self) -> str:
        return "Idea-Lab Divergent Generation"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.IDEA_LAB_CANDIDATES

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # Check if Idea-Lab is enabled
            if not getattr(self.project.config, 'enable_idea_lab', False):
                logger.info("Idea-Lab disabled, skipping")
                raise StepExecutionError("Idea-Lab is disabled (enable_idea_lab=False)")

            # Load Literature Matrix
            lit_matrix = await self.load_context_with_fallback(
                step_id="step_1_1", doc_type=DocumentType.LITERATURE_MATRIX_V7
            ) or ""

            if not lit_matrix:
                # Fallback to v4 literature matrix
                lit_matrix = await self.load_context_with_fallback(
                    step_id="step_1_1", doc_type=DocumentType.LITERATURE_MATRIX
                ) or ""

            prompt = IDEA_LAB_GEMINI_PROMPT.format(
                literature_matrix=lit_matrix,
                topic=self.project.config.topic,
                venue=self.project.config.target_venue,
            )

            response = await self.gemini_client.chat(
                system_prompt="You are a creative research ideation agent. Think divergently.",
                prompt=prompt,
                wrapper_mode="minimal",  # Creative divergent task, minimal quality control
            )

            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt="Idea-Lab divergent generation",
                user_prompt=prompt[:500],
                response=response[:1000],
            )

            document = self.create_document(
                doc_type=DocumentType.IDEA_LAB_CANDIDATES,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["01_C_Literature_Matrix"],
                outputs=["01_D_Idea_Lab_Candidates"],
            )

            await self.save_and_commit(document, "step_1_3b_idea_lab: Idea-Lab candidates generated")
            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 1.3b Idea-Lab failed: {e}")
            raise StepExecutionError(f"Step 1.3b Idea-Lab failed: {e}")

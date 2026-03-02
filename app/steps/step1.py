"""
Step 1 实现
深度研究与主题冻结阶段的步骤实现
"""
import logging
import re
from typing import Dict, Any, Optional

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.models.artifact import ArtifactStatus
from app.models.hil import QuestionType, TicketPriority
from app.prompts.step1_prompts import (
    render_step_1_1a_prompt,
    render_step_1_1b_hunt_prompt,
    render_step_1_1c_prompt,
    render_step_1_2_prompt,
    render_step_1_3_prompt,
    render_step_1_4_prompt,
    render_step_1_5_prompt,
    render_step_1_3b_prompt,
    render_step_1_2b_prompt
)

logger = logging.getLogger(__name__)


def extract_clean_url(text: str) -> str:
    """
    从markdown文本中提取干净的URL

    支持格式:
    - [text](url)
    - 裸URL
    - [url](url)
    - 错误格式: url](url

    Args:
        text: 包含URL的文本

    Returns:
        str: 清理后的URL
    """
    if not text:
        return text

    text = text.strip()

    # 情况1: markdown链接格式 [text](url)
    match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', text)
    if match:
        return match.group(2).strip()

    # 情况2: 错误格式 url](url - 取第一个http开头的部分
    if '](http' in text:
        match = re.search(r'(https?://[^\s\]]+?)(?=\]|$)', text)
        if match:
            return match.group(1).strip()

    # 情况3: 裸URL - 移除可能的markdown符号
    if text.startswith('http'):
        # 移除尾部的markdown残留
        text = re.sub(r'[\[\]\(\)]+$', '', text)
        return text.strip()

    return text


def validate_url_format(url: str) -> tuple[bool, str]:
    """
    验证URL格式是否正确

    Args:
        url: 待验证的URL

    Returns:
        tuple: (is_valid, error_message)
    """
    if not url:
        return False, "Empty URL"

    # 检查是否包含markdown残留
    if '](' in url or '[' in url or ']' in url:
        return False, "URL contains markdown syntax remnants"

    # 检查是否为有效URL
    url_pattern = r'^https?://[^\s]+$'
    if not re.match(url_pattern, url):
        return False, "Invalid URL format"

    # 检查是否为支持的域名
    supported_domains = ['arxiv.org', 'doi.org', 'dx.doi.org', 'openreview.net', 'aclweb.org']
    if not any(domain in url for domain in supported_domains):
        logger.warning(f"URL from unsupported domain: {url}")
        # 不阻止，只是警告

    return True, "Valid"


class Step1_1a_SearchPlan(BaseStep):
    """Step 1.1a: Search Plan (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_1_1a"

    @property
    def step_name(self) -> str:
        return "Search Plan"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.SEARCH_PLAN

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 1.1a: Search Plan (ChatGPT)

        Returns:
            Document: Search Plan 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Project Intake Card 作为上下文 (with fallback)
            intake_card_content = await self.load_context_with_fallback(
                step_id="step_0_1",
                doc_type=DocumentType.PROJECT_INTAKE_CARD
            )

            if not intake_card_content:
                raise StepExecutionError("Project Intake Card not found. Please run Step 0.1 first.")

            # 获取 Venue Taste Notes（可选，with fallback）
            venue_taste_content = await self.load_context_with_fallback(
                step_id="step_0_2",
                doc_type=DocumentType.VENUE_TASTE_NOTES
            )

            # 渲染 Prompt
            prompt = render_step_1_1a_prompt(
                topic=self.project.config.topic,
                target_venue=self.project.config.target_venue,
                research_type=self.project.config.research_type.value,
                intake_card_content=intake_card_content,
                venue_taste_content=venue_taste_content if venue_taste_content else ""
            )

            # 调用 ChatGPT（Research Strategist 角色）
            logger.info("Calling ChatGPT to generate Search Plan")
            system_prompt = "You are a Research Strategist. Your role is to decompose research topics into structured search plans for systematic literature review."
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
                    "intake_card_included": True,
                    "venue_taste_included": bool(venue_taste_content),
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.SEARCH_PLAN,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.PROJECT_INTAKE_CARD.value, DocumentType.VENUE_TASTE_NOTES.value],
                outputs=[DocumentType.RAW_INTEL_LOG.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.SEARCH_PLAN,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Search Plan"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.1a failed: {e}")


class Step1_1b_Hunt(BaseStep):
    """Step 1.1b: The Hunt (Gemini)"""

    @property
    def step_id(self) -> str:
        return "step_1_1b"

    @property
    def step_name(self) -> str:
        return "The Hunt"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.RAW_INTEL_LOG

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 1.1b: The Hunt (Gemini)

        Returns:
            Document: Raw Intel Log 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Search Plan (with fallback)
            search_plan_content = await self.load_context_with_fallback(
                step_id="step_1_1a",
                doc_type=DocumentType.SEARCH_PLAN
            )

            if not search_plan_content:
                raise StepExecutionError("Search Plan not found. Please run Step 1.1a first.")

            # 渲染 Prompt
            rigor_profile = getattr(self.project.config, 'rigor_profile', None) or getattr(self.project, 'rigor_profile', 'top_journal') or 'top_journal'
            prompt = render_step_1_1b_hunt_prompt(
                search_plan_content=search_plan_content,
                topic=self.project.config.topic,
                target_venue=self.project.config.target_venue,
                rigor_profile=rigor_profile
            )

            # 调用 Gemini（情报官角色）
            logger.info("Calling Gemini to execute The Hunt (Agentic Wrapper: disabled)")
            system_prompt = "You are an Intelligence Officer (The Hunter). Your role is systematic evidence gathering — find, catalog, and verify research papers."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                max_tokens=32768,
                wrapper_mode="disabled"  # disabled: output is >5000 tokens structured table, wrapper causes truncation
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
                    "search_plan_included": True,
                    "agentic_wrapper_mode": "disabled",
                    "max_tokens": 16384
                }
            )

            if not content:
                raise StepExecutionError("Gemini returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.RAW_INTEL_LOG,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.SEARCH_PLAN.value],
                outputs=[DocumentType.LITERATURE_MATRIX_V7.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.RAW_INTEL_LOG,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Execute The Hunt"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.1b failed: {e}")


class Step1_1c_Synthesis(BaseStep):
    """Step 1.1c: Literature Synthesis (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_1_1c"

    @property
    def step_name(self) -> str:
        return "Literature Synthesis"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.LITERATURE_MATRIX_V7

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 1.1c: Literature Synthesis (ChatGPT)

        Returns:
            Document: Literature Matrix v7 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Raw Intel Log (with fallback)
            raw_intel_content = await self.load_context_with_fallback(
                step_id="step_1_1b",
                doc_type=DocumentType.RAW_INTEL_LOG
            )

            if not raw_intel_content:
                raise StepExecutionError("Raw Intel Log not found. Please run Step 1.1b first.")

            # 渲染 Prompt
            rigor_profile = getattr(self.project.config, 'rigor_profile', None) or getattr(self.project, 'rigor_profile', 'top_journal') or 'top_journal'
            prompt = render_step_1_1c_prompt(
                raw_intel_content=raw_intel_content,
                topic=self.project.config.topic,
                target_venue=self.project.config.target_venue,
                rigor_profile=rigor_profile
            )

            # 调用 ChatGPT（PI 角色）
            logger.info("Calling ChatGPT to generate Literature Synthesis")
            system_prompt = "You are the PI (Principal Investigator). Your role is to synthesize raw intelligence into structured analysis, identify research gaps, and propose directions."
            content = await self.chatgpt_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                max_tokens=16384  # Large output: Literature Matrix table (25+ rows × 10 cols) + Schools + Gaps + Directions
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
                    "raw_intel_included": True,
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.LITERATURE_MATRIX_V7,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.RAW_INTEL_LOG.value],
                outputs=[DocumentType.SELECTED_TOPIC.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.LITERATURE_MATRIX_V7,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Literature Matrix (v7)"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.1c failed: {e}")


class Step1_2_TopicDecision(BaseStep):
    """Step 1.2: Topic Decision & Draft Claim Set (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_1_2"

    @property
    def step_name(self) -> str:
        return "Topic Decision & Draft Claim Set"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.SELECTED_TOPIC

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 1.2: Topic Decision & Draft Claim Set

        Returns:
            Document: Selected Topic 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Literature Matrix v7 (with fallback)
            literature_matrix_content = await self.load_context_with_fallback(
                step_id="step_1_1c",
                doc_type=DocumentType.LITERATURE_MATRIX_V7
            )

            if not literature_matrix_content:
                raise StepExecutionError("Literature Matrix not found. Please run Step 1.1 first.")

            # 获取 Venue Taste Notes (v7: S2 输入)
            venue_taste_content = await self.load_context_with_fallback(
                step_id="step_0_2",
                doc_type=DocumentType.VENUE_TASTE_NOTES
            )

            # 获取 Project Intake Card 以提取核心关键词 (with fallback)
            intake_card_content = await self.load_context_with_fallback(
                step_id="step_0_1",
                doc_type=DocumentType.PROJECT_INTAKE_CARD
            )

            # 提取核心关键词
            core_keywords = ""
            if intake_card_content:
                # 从 Intake Card 中提取 "Deep Research Keywords" 部分
                import re
                keywords_pattern = r'##\s*6\.\s*Deep Research Keywords.*?\n\*\*English Keywords:\*\*\s*([^\n]+)'
                match = re.search(keywords_pattern, intake_card_content, re.DOTALL | re.IGNORECASE)
                if match:
                    core_keywords = match.group(1).strip()
                    logger.info(f"Extracted core keywords: {core_keywords}")

            # 渲染 Prompt
            prompt = render_step_1_2_prompt(
                literature_matrix_content=literature_matrix_content,
                target_venue=self.project.config.target_venue,
                core_keywords=core_keywords,
                venue_taste_content=venue_taste_content if venue_taste_content else ""
            )

            # v7.1: Inject AGENTS.md + MEMORY.md context
            project_context = self.get_project_context_injection()
            if project_context:
                prompt += project_context

            # v7.1: Append core terms addendum
            from app.prompts.step1_prompts import TOPIC_DECISION_CORE_TERMS_ADDENDUM
            prompt += TOPIC_DECISION_CORE_TERMS_ADDENDUM

            # v7.1: Load Idea-Lab candidates (optional)
            try:
                idea_lab_content = await self.load_context_with_fallback(
                    step_id="step_1_3b_idea_lab",
                    doc_type=DocumentType.IDEA_LAB_CANDIDATES
                )
                if idea_lab_content:
                    from app.prompts.step1_prompts import TOPIC_DECISION_IDEALAB_ADDENDUM
                    prompt += TOPIC_DECISION_IDEALAB_ADDENDUM.format(idea_lab_content=idea_lab_content)
                    logger.info("Idea-Lab candidates injected into Topic Decision prompt")
            except Exception as idea_err:
                logger.debug(f"Idea-Lab candidates not available (optional): {idea_err}")

            # 调用 ChatGPT（PI/架构师角色）
            logger.info("Calling ChatGPT to generate Topic Decision")
            system_prompt = "You are a PI (Principal Investigator) and research architect. Your role is formalization, decision-making, and risk assessment."
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
                    "literature_matrix_included": True,
                    "venue_taste_included": bool(venue_taste_content),
                    "core_keywords_included": bool(core_keywords)
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.SELECTED_TOPIC,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.LITERATURE_MATRIX_V7.value, DocumentType.VENUE_TASTE_NOTES.value],
                outputs=[DocumentType.KILLER_PRIOR_CHECK.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.SELECTED_TOPIC,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Selected Topic and Draft Claims"
            )

            # 提取并保存 Draft Claims 子文档（v7 必须产物）
            logger.info("Extracting Draft Claims from Selected Topic")
            draft_claims_content = self._extract_draft_claims(content)
            if draft_claims_content:
                draft_claims_doc = self.create_document(
                    doc_type=DocumentType.DRAFT_CLAIMS,
                    content=draft_claims_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.SELECTED_TOPIC.value],
                    outputs=[DocumentType.KILLER_PRIOR_CHECK.value]
                )

                # v6.0: Save to Artifact Store (dual-write mode)
                await self.save_to_artifact_store(
                    content=draft_claims_content,
                    doc_type=DocumentType.DRAFT_CLAIMS,
                    status=ArtifactStatus.FROZEN
                )
                logger.info(f"Saved to Artifact Store: {self.step_id} - Draft Claims")

                await self.save_and_commit(
                    document=draft_claims_doc,
                    commit_message=f"{self.step_id}: Extract Draft Claims"
                )
                logger.info("Draft Claims document created successfully")
            else:
                logger.warning("Could not extract Draft Claims from response - full content will be used as fallback")

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.2 failed: {e}")

    def _extract_draft_claims(self, content: str) -> Optional[str]:
        """
        从 Selected Topic 响应中提取 Draft Claims 部分

        查找包含 claims 和 non-claims 的段落，支持多种标题格式
        """
        import re

        # 尝试匹配常见的 Draft Claims 段落标题
        patterns = [
            r'(##\s*(?:4\)|Draft Claim|Claim Set|Claims and Non[-\s]?Claims).*?)(?=\n##\s*(?:5\)|Minimal|Figure|Table)|$)',
            r'(##\s*Draft Claims.*?)(?=\n##\s*|$)',
            r'(###?\s*(?:Claims|Draft Claims).*?###?\s*(?:Non[-\s]?Claims|What We Do NOT Claim).*?)(?=\n##\s*|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()
                if len(extracted) > 100:  # 确保提取到有意义的内容
                    logger.info(f"Extracted Draft Claims ({len(extracted)} chars)")
                    return extracted

        # 回退：查找包含 "claim" 关键词的连续段落
        lines = content.split('\n')
        claim_start = None
        claim_end = None
        for i, line in enumerate(lines):
            lower = line.lower()
            if claim_start is None and ('draft claim' in lower or 'claim set' in lower or ('claims' in lower and 'non' not in lower and line.startswith('#'))):
                claim_start = i
            elif claim_start is not None and line.startswith('## ') and 'claim' not in lower and 'non-claim' not in lower and 'nonclaim' not in lower:
                claim_end = i
                break

        if claim_start is not None:
            claim_end = claim_end or len(lines)
            extracted = '\n'.join(lines[claim_start:claim_end]).strip()
            if len(extracted) > 100:
                logger.info(f"Extracted Draft Claims via fallback ({len(extracted)} chars)")
                return extracted

        logger.warning("Could not extract Draft Claims section from content")
        return None


class Step1_3_KillerPriorCheck(BaseStep):
    """Step 1.3: Killer Prior Check (Gemini) - MANDATORY"""

    @property
    def step_id(self) -> str:
        return "step_1_3"

    @property
    def step_name(self) -> str:
        return "Killer Prior Check (MANDATORY)"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.KILLER_PRIOR_CHECK

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 1.3: Killer Prior Check (MANDATORY)

        Returns:
            Document: Killer Prior Check 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Selected Topic (with fallback)
            selected_topic_content = await self.load_context_with_fallback(
                step_id="step_1_2",
                doc_type=DocumentType.SELECTED_TOPIC
            )

            if not selected_topic_content:
                raise StepExecutionError("Selected Topic not found. Please run Step 1.2 first.")

            # 获取 Draft Claims（v7: S3 必须输入）
            draft_claims_content = await self.load_context_with_fallback(
                step_id="step_1_2",
                doc_type=DocumentType.DRAFT_CLAIMS
            )

            if not draft_claims_content:
                raise StepExecutionError("Draft Claims not found. Please run Step 1.2 first (it should produce Draft Claims).")

            # 渲染 Prompt
            rigor_profile = getattr(self.project.config, 'rigor_profile', None) or getattr(self.project, 'rigor_profile', 'top_journal') or 'top_journal'
            prompt = render_step_1_3_prompt(
                selected_topic_content=selected_topic_content,
                draft_claims_content=draft_claims_content,
                rigor_profile=rigor_profile
            )

            # 调用 Gemini（情报官/审稿人角色）
            logger.info("Calling Gemini to perform Killer Prior Check")
            system_prompt = "You are a ruthless reviewer and research librarian. Your role is to find prior work that might invalidate the proposed research."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                wrapper_mode="disabled",  # disabled: output is >5000 tokens (15+ papers + collision map table + verdict), wrapper causes truncation
                max_tokens=32768  # Large output: Direct Collision + Partial Overlap + Collision Map + Changes + Verdict
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
                    "draft_claims_included": True,
                    "mandatory_check": True
                }
            )

            if not content:
                raise StepExecutionError("Gemini returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.KILLER_PRIOR_CHECK,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.SELECTED_TOPIC.value],
                outputs=[DocumentType.CLAIMS_AND_NONCLAIMS.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.KILLER_PRIOR_CHECK,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Perform Killer Prior Check (MANDATORY)"
            )

            # HIL Integration: Check if similar work found
            logger.info("Checking for similar work (HIL integration)")
            has_similar_work = self._check_for_similar_work(content)

            if has_similar_work:
                logger.warning("Similar work detected - requesting human decision")

                # Create HIL ticket for continuation decision
                ticket = await self.request_human_input(
                    question="发现相似工作，是否继续当前研究方向？",
                    question_type=QuestionType.DECISION,
                    context={
                        "step": "Killer Prior Check",
                        "topic": self.project.config.topic,
                        "venue": self.project.config.target_venue,
                        "similar_work_found": True
                    },
                    options=["继续当前方向", "调整研究角度", "暂停项目"],
                    default_answer="继续当前方向",  # Default to continue
                    priority=TicketPriority.CRITICAL,
                    blocking=True,  # Blocking - should wait for answer
                    timeout_hours=72.0
                )

                logger.info(f"Created BLOCKING HIL ticket {ticket.ticket_id} for similar work decision")
                logger.warning("This is a BLOCKING ticket - project should wait for human decision")

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.3 failed: {e}")

    def _check_for_similar_work(self, content: str) -> bool:
        """
        检查 Killer Prior Check 结果中是否发现相似工作

        查找关键词如 "similar", "prior work", "already published" 等
        """
        try:
            content_lower = content.lower()

            # 关键词列表
            similar_work_keywords = [
                "similar work",
                "prior work",
                "already published",
                "existing work",
                "closely related",
                "nearly identical",
                "substantial overlap",
                "已发表",
                "相似工作",
                "现有工作"
            ]

            # 检查是否包含关键词
            for keyword in similar_work_keywords:
                if keyword in content_lower:
                    logger.info(f"Found similar work indicator: {keyword}")
                    return True

            # 检查是否有 "FAIL" 或 "WARNING" 标记
            if "verdict: fail" in content_lower or "verdict: warning" in content_lower:
                logger.info("Found FAIL or WARNING verdict in Killer Prior Check")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking for similar work: {e}")
            return False


class Step1_4_ClaimsFreeze(BaseStep):
    """Step 1.4: Claims Freeze (ChatGPT)"""

    @property
    def step_id(self) -> str:
        return "step_1_4"

    @property
    def step_name(self) -> str:
        return "Claims Freeze"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.CLAIMS_AND_NONCLAIMS

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 1.4: Claims Freeze
        生成3个独立文档：Claims and NonClaims, Minimal Verification Set, Pivot Rules

        Returns:
            Document: Claims and NonClaims 文档（主文档）

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Killer Prior Check (with fallback)
            killer_prior_content = await self.load_context_with_fallback(
                step_id="step_1_3",
                doc_type=DocumentType.KILLER_PRIOR_CHECK
            )

            if not killer_prior_content:
                raise StepExecutionError("Killer Prior Check not found. Please run Step 1.3 first.")

            # 渲染 Prompt
            prompt = render_step_1_4_prompt(
                killer_prior_content=killer_prior_content,
                target_venue=self.project.config.target_venue
            )

            # 调用 ChatGPT（PI/架构师角色）
            logger.info("Calling ChatGPT to freeze claims and generate 3 documents")
            system_prompt = "You are a PI (Principal Investigator). Your role is to formalize and freeze the research claims based on prior work analysis."
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
                    "killer_prior_included": True,
                    "generates_multiple_docs": True,
                    "doc_count": 3
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 解析多个文档
            documents_data = self.parse_multiple_documents(content, [
                ("DOCUMENT_1", DocumentType.CLAIMS_AND_NONCLAIMS),
                ("DOCUMENT_2", DocumentType.MINIMAL_VERIFICATION_SET),
                ("DOCUMENT_3", DocumentType.PIVOT_RULES)
            ])

            # 创建并保存所有文档
            main_document = None
            for doc_type, doc_content in documents_data:
                document = self.create_document(
                    doc_type=doc_type,
                    content=doc_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.KILLER_PRIOR_CHECK.value],
                    outputs=[DocumentType.FIGURE_FIRST_STORY.value]
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
                if doc_type == DocumentType.CLAIMS_AND_NONCLAIMS:
                    main_document = document

            logger.info(f"Completed {self.step_name} - Generated 3 documents")
            return main_document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.4 failed: {e}")



class Step1_5_FigureFirstStory(BaseStep):
    """Step 1.5: Paper Identity & Figure-First Story (Gemini)"""

    @property
    def step_id(self) -> str:
        return "step_1_5"

    @property
    def step_name(self) -> str:
        return "Paper Identity & Figure-First Story"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.FIGURE_FIRST_STORY

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 1.5: Paper Identity & Figure-First Story
        生成2个独立文档：Figure First Story, Title Abstract Candidates

        Returns:
            Document: Figure First Story 文档（主文档）

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
            prompt = render_step_1_5_prompt(
                frozen_claims_content=frozen_claims_content,
                target_venue=self.project.config.target_venue
            )

            # 调用 Gemini（编辑角色）
            logger.info("Calling Gemini to generate Figure-First Story and Title/Abstract Candidates")
            system_prompt = f"You are a senior editor of {self.project.config.target_venue}. Your role is to optimize narrative and presentation for maximum impact."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                max_tokens=32768,  # Large output: two complete documents (Figure-First Story + Title/Abstract)
                wrapper_mode="disabled"  # disabled: output is >5000 tokens (2 docs with YAML + sections), wrapper causes truncation
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
                    "generates_multiple_docs": True,
                    "doc_count": 2,
                    "agentic_wrapper_mode": "lite",
                    "max_tokens": 8192
                }
            )

            if not content:
                raise StepExecutionError("Gemini returned empty response")

            # 解析多个文档
            documents_data = self.parse_multiple_documents(content, [
                ("DOCUMENT_1", DocumentType.FIGURE_FIRST_STORY),
                ("DOCUMENT_2", DocumentType.TITLE_ABSTRACT_CANDIDATES)
            ])

            # 创建并保存所有文档
            main_document = None
            for doc_type, doc_content in documents_data:
                document = self.create_document(
                    doc_type=doc_type,
                    content=doc_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.CLAIMS_AND_NONCLAIMS.value],
                    outputs=[DocumentType.FULL_PROPOSAL.value]
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
                if doc_type == DocumentType.FIGURE_FIRST_STORY:
                    main_document = document

            logger.info(f"Completed {self.step_name} - Generated 2 documents")
            return main_document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.5 failed: {e}")


class Step1_3b_ReferenceQA(BaseStep):
    """Step 1.3b: Reference QA (Gemini) - renamed from Step1_1b"""

    @property
    def step_id(self) -> str:
        return "step_1_3b"

    @property
    def step_name(self) -> str:
        return "Reference QA"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.REFERENCE_QA_REPORT

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 1.1b: Reference QA
        验证文献引用质量，生成 Reference QA Report

        Returns:
            Document: Reference QA Report 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Literature Matrix v7 (with fallback)
            literature_matrix_content = await self.load_context_with_fallback(
                step_id="step_1_1c",
                doc_type=DocumentType.LITERATURE_MATRIX_V7
            )

            if not literature_matrix_content:
                raise StepExecutionError("Literature Matrix not found. Please run Step 1.1 first.")

            # 获取 Killer Prior Check (v7: S3b 输入)
            killer_prior_content = await self.load_context_with_fallback(
                step_id="step_1_3",
                doc_type=DocumentType.KILLER_PRIOR_CHECK
            )

            # 渲染 Prompt
            prompt = render_step_1_3b_prompt(
                literature_matrix_content=literature_matrix_content,
                killer_prior_content=killer_prior_content if killer_prior_content else ""
            )

            # 调用 Gemini（研究图书管理员角色）
            logger.info("Calling Gemini to perform Reference QA")
            system_prompt = "You are a meticulous research librarian and citation validator. Your role is to ensure all references are complete, valid, and properly formatted."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                wrapper_mode="disabled",  # disabled: output is >5000 tokens (enhanced matrix + QA report), wrapper causes truncation
                max_tokens=32768  # Large output: enhanced Literature Matrix + Reference Quality Report
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
                    "literature_matrix_included": True,
                    "killer_prior_included": bool(killer_prior_content),
                    "v4_new_step": True
                }
            )

            if not content:
                raise StepExecutionError("Gemini returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.REFERENCE_QA_REPORT,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.LITERATURE_MATRIX_V7.value, DocumentType.KILLER_PRIOR_CHECK.value],
                outputs=[DocumentType.SELECTED_TOPIC.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.REFERENCE_QA_REPORT,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Reference QA Report"
            )

            # 提取并保存 Verified References（v7: S3b 产物之二）
            logger.info("Extracting Verified References from QA Report + Literature Matrix")
            refs_content = self._extract_verified_references(content, literature_matrix_content)
            if refs_content:
                refs_doc = self.create_document(
                    doc_type=DocumentType.VERIFIED_REFERENCES,
                    content=refs_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.REFERENCE_QA_REPORT.value, DocumentType.LITERATURE_MATRIX_V7.value],
                    outputs=[]
                )

                await self.save_to_artifact_store(
                    content=refs_content,
                    doc_type=DocumentType.VERIFIED_REFERENCES,
                    status=ArtifactStatus.FROZEN
                )
                logger.info(f"Saved to Artifact Store: {self.step_id} - Verified References")

                await self.save_and_commit(
                    document=refs_doc,
                    commit_message=f"{self.step_id}: Extract Verified References"
                )
                logger.info("Verified References created successfully")
            else:
                logger.warning("Could not extract Verified References from QA Report")

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.1b failed: {e}")

    def _extract_verified_references(self, qa_content: str, matrix_content: str) -> Optional[str]:
        """
        从 Reference QA Report 的 A) Literature Matrix (Enhanced) 表格中提取引用，
        生成 BibTeX 格式的 01_Verified_References.bib

        v7 SOP: S3b 产物之二 — 01_Verified_References.bib
        """
        import re

        try:
            # 1. 如果 QA Report 中仍有 bibtex 代码块，直接使用
            bibtex_blocks = re.findall(r'```bibtex\s*\n(.*?)```', qa_content, re.DOTALL)
            if bibtex_blocks:
                bibtex_content = "\n\n".join(block.strip() for block in bibtex_blocks)
                entry_count = len(re.findall(r'@\w+\{', bibtex_content))
                logger.info(f"Extracted {entry_count} BibTeX entries from QA Report bibtex block")
                return self._wrap_bib_content(bibtex_content, entry_count)

            # 2. 从 section A 表格解析并生成 BibTeX
            # 匹配 markdown 表格行: | # | Title | Venue/Year | DOI/Link | Status |
            table_rows = re.findall(
                r'\|\s*(\d+)\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]*)\|',
                qa_content
            )

            if not table_rows:
                # Fallback: 从 Literature Matrix 原始内容解析
                table_rows = re.findall(
                    r'\|\s*(\d+)\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]*)\|',
                    matrix_content
                )

            if not table_rows:
                logger.warning("No table rows found in QA Report or Literature Matrix")
                return None

            bibtex_entries = []
            for row_num, title, venue_year, doi_link, status in table_rows:
                title = title.strip()
                venue_year = venue_year.strip()
                doi_link = doi_link.strip()

                # 提取 URL from markdown link syntax [text](url)
                url_match = re.search(r'\[.*?\]\((https?://[^\)]+)\)', doi_link)
                url = url_match.group(1) if url_match else ""
                if not url:
                    # 尝试直接匹配 URL
                    url_match = re.search(r'(https?://\S+)', doi_link)
                    url = url_match.group(1).rstrip('.,;)') if url_match else ""

                # 解析 venue 和 year
                year_match = re.search(r'(\d{4})', venue_year)
                year = year_match.group(1) if year_match else "UNKNOWN"
                venue = re.sub(r',?\s*\d{4}.*$', '', venue_year).strip()

                # 生成 citation key
                first_word = re.sub(r'[^a-zA-Z]', '', title.split()[0].lower()) if title else "ref"
                key = f"{first_word}{year}_{row_num}"

                entry = f"""@article{{{key},
  title={{{title}}},
  journal={{{venue}}},
  year={{{year}}},
  url={{{url}}}
}}"""
                bibtex_entries.append(entry)

            bibtex_content = "\n\n".join(bibtex_entries)
            entry_count = len(bibtex_entries)
            logger.info(f"Generated {entry_count} BibTeX entries from table rows")
            return self._wrap_bib_content(bibtex_content, entry_count)

        except Exception as e:
            logger.error(f"Error extracting verified references: {e}")
            return None

    def _wrap_bib_content(self, bibtex_content: str, entry_count: int) -> str:
        """包装 BibTeX 内容为完整的 .bib 文档"""
        return f"""---
doc_type: "01_Verified_References"
version: "1.0"
status: "frozen"
created_by: "System"
inputs:
  - "01_Reference_QA_Report.md"
  - "01_C_Literature_Matrix.md"
outputs: []
gate_relevance: "Gate 1.6"
---

% Verified References — generated from Reference QA Report (Step S3b)
% Total BibTeX entries: {entry_count}

{bibtex_content}
"""


class Step1_2b_TopicAlignmentCheck(BaseStep):
    """Step 1.2b: Topic Alignment Check (ChatGPT) - DEPRECATED: merged into Gate 1 per SOP v7"""

    @property
    def step_id(self) -> str:
        return "step_1_2b"

    @property
    def step_name(self) -> str:
        return "Topic Alignment Check"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.TOPIC_ALIGNMENT_CHECK

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.openai_model

    async def execute(self) -> Document:
        """
        执行 Step 1.2b: Topic Alignment Check (Gate 1.25)
        验证选题与 Intake Card 的对齐度

        Returns:
            Document: Topic Alignment Check 文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取 Selected Topic (with fallback)
            selected_topic_content = await self.load_context_with_fallback(
                step_id="step_1_2",
                doc_type=DocumentType.SELECTED_TOPIC
            )

            if not selected_topic_content:
                raise StepExecutionError("Selected Topic not found. Please run Step 1.2 first.")

            # 获取 Project Intake Card (with fallback)
            intake_card_content = await self.load_context_with_fallback(
                step_id="step_0_1",
                doc_type=DocumentType.PROJECT_INTAKE_CARD
            )

            if not intake_card_content:
                raise StepExecutionError("Project Intake Card not found. Please run Step 0.1 first.")

            # 渲染 Prompt
            prompt = render_step_1_2b_prompt(
                selected_topic_content=selected_topic_content,
                intake_card_content=intake_card_content,
                keywords=self.project.config.keywords
            )

            # 调用 ChatGPT（PI 角色）
            logger.info("Calling ChatGPT to perform Topic Alignment Check")
            system_prompt = "You are the PI performing quality control. Your role is to ensure the selected topic aligns with the original project goals and constraints."
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
                    "intake_card_included": True,
                    "v4_new_step": True,
                    "gate_check": "Gate 1.25"
                }
            )

            if not content:
                raise StepExecutionError("ChatGPT returned empty response")

            # 创建文档
            document = self.create_document(
                doc_type=DocumentType.TOPIC_ALIGNMENT_CHECK,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.SELECTED_TOPIC.value, DocumentType.PROJECT_INTAKE_CARD.value],
                outputs=[DocumentType.KILLER_PRIOR_CHECK.value]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.TOPIC_ALIGNMENT_CHECK,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id}")

            # 保存并提交 (backward compatibility)
            await self.save_and_commit(
                document=document,
                commit_message=f"{self.step_id}: Generate Topic Alignment Check (Gate 1.25)"
            )

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.2b failed: {e}")

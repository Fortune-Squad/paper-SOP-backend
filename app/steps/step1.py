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
    render_step_1_1_prompt,
    render_step_1_2_prompt,
    render_step_1_3_prompt,
    render_step_1_4_prompt,
    render_step_1_5_prompt,
    render_step_1_1b_prompt,
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


class Step1_1_DeepResearch(BaseStep):
    """Step 1.1: Broad Deep Research (Gemini)"""

    @property
    def step_id(self) -> str:
        return "step_1_1"

    @property
    def step_name(self) -> str:
        return "Broad Deep Research"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.DEEP_RESEARCH_SUMMARY

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step 1.1: Broad Deep Research

        SOP v4.0 要求生成 4 个文档：
        1. Deep Research Summary (主文档)
        2. Search Query Log
        3. Literature Matrix
        4. Verified References (可选)

        Returns:
            Document: Deep Research Summary 文档

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
            prompt = render_step_1_1_prompt(
                topic=self.project.config.topic,
                target_venue=self.project.config.target_venue,
                research_type=self.project.config.research_type.value,
                intake_card_content=intake_card_content,
                venue_taste_content=venue_taste_content if venue_taste_content else ""
            )

            # 调用 Gemini（情报官角色）
            logger.info("Calling Gemini to generate Deep Research Summary (Agentic Wrapper DISABLED for complete output)")
            system_prompt = "You are a Chief Intelligence Officer and top-journal editor. Your role is deep research, literature analysis, and identifying research gaps."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                max_tokens=16384,  # 增加输出空间以支持长篇输出
                wrapper_mode="disabled"  # 禁用 Agentic Wrapper 以获取完整输出
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
                    "agentic_wrapper_mode": "disabled",
                    "max_tokens": 16384
                }
            )

            if not content:
                raise StepExecutionError("Gemini returned empty response")

            # 1. 创建并保存主文档 (Deep Research Summary)
            logger.info("Creating Deep Research Summary document")
            main_document = self.create_document(
                doc_type=DocumentType.DEEP_RESEARCH_SUMMARY,
                content=content,
                status=DocumentStatus.COMPLETED,
                inputs=[DocumentType.PROJECT_INTAKE_CARD.value, DocumentType.VENUE_TASTE_NOTES.value],
                outputs=[
                    DocumentType.SEARCH_QUERY_LOG.value,
                    DocumentType.LITERATURE_MATRIX.value,
                    DocumentType.VERIFIED_REFERENCES.value,
                    DocumentType.SELECTED_TOPIC.value
                ]
            )

            # v6.0: Save to Artifact Store (dual-write mode)
            await self.save_to_artifact_store(
                content=content,
                doc_type=DocumentType.DEEP_RESEARCH_SUMMARY,
                status=ArtifactStatus.FROZEN
            )
            logger.info(f"Saved to Artifact Store: {self.step_id} - Deep Research Summary")

            # Save to file system (backward compatibility)
            await self.save_and_commit(
                document=main_document,
                commit_message=f"{self.step_id}: Generate Deep Research Summary"
            )

            # HIL Integration: Check if multiple research directions found
            logger.info("Checking for multiple research directions (HIL integration)")
            research_directions = self._extract_research_directions(content)

            if len(research_directions) > 1:
                logger.info(f"Found {len(research_directions)} research directions - requesting human input")

                # Create HIL ticket for direction selection
                ticket = await self.request_human_input(
                    question=f"发现 {len(research_directions)} 个潜在研究方向，请选择优先探索的方向",
                    question_type=QuestionType.DECISION,
                    context={
                        "directions": research_directions,
                        "topic": self.project.config.topic,
                        "venue": self.project.config.target_venue
                    },
                    options=research_directions,
                    priority=TicketPriority.HIGH,
                    blocking=False,  # Non-blocking - can proceed without answer
                    timeout_hours=48.0
                )

                logger.info(f"Created HIL ticket {ticket.ticket_id} for research direction selection")
                logger.info("Step will continue without waiting for answer (non-blocking)")

            # 2. 提取并保存 Search Query Log
            logger.info("Extracting Search Query Log")
            search_log_content = self._extract_search_log(content)
            if search_log_content:
                search_log_doc = self.create_document(
                    doc_type=DocumentType.SEARCH_QUERY_LOG,
                    content=search_log_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.DEEP_RESEARCH_SUMMARY.value],
                    outputs=[DocumentType.LITERATURE_MATRIX.value]
                )

                # v6.0: Save to Artifact Store (dual-write mode)
                await self.save_to_artifact_store(
                    content=search_log_content,
                    doc_type=DocumentType.SEARCH_QUERY_LOG,
                    status=ArtifactStatus.FROZEN
                )
                logger.info(f"Saved to Artifact Store: {self.step_id} - Search Query Log")

                # Save to file system (backward compatibility)
                await self.save_and_commit(
                    document=search_log_doc,
                    commit_message=f"{self.step_id}: Extract Search Query Log"
                )
                logger.info("Search Query Log created successfully")
            else:
                logger.warning("Could not extract Search Query Log from response")

            # 3. 提取并保存 Literature Matrix
            logger.info("Extracting Literature Matrix")
            lit_matrix_content = self._extract_literature_matrix(content)
            if lit_matrix_content:
                lit_matrix_doc = self.create_document(
                    doc_type=DocumentType.LITERATURE_MATRIX,
                    content=lit_matrix_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.DEEP_RESEARCH_SUMMARY.value],
                    outputs=[DocumentType.REFERENCE_QA_REPORT.value]
                )

                # v6.0: Save to Artifact Store (dual-write mode)
                await self.save_to_artifact_store(
                    content=lit_matrix_content,
                    doc_type=DocumentType.LITERATURE_MATRIX,
                    status=ArtifactStatus.FROZEN
                )
                logger.info(f"Saved to Artifact Store: {self.step_id} - Literature Matrix")

                # Save to file system (backward compatibility)
                await self.save_and_commit(
                    document=lit_matrix_doc,
                    commit_message=f"{self.step_id}: Extract Literature Matrix"
                )
                logger.info("Literature Matrix created successfully")
            else:
                logger.warning("Could not extract Literature Matrix from response")

            # 4. 提取并保存 Verified References
            logger.info("Extracting Verified References")
            refs_content = self._extract_references(content)
            if refs_content:
                refs_doc = self.create_document(
                    doc_type=DocumentType.VERIFIED_REFERENCES,
                    content=refs_content,
                    status=DocumentStatus.COMPLETED,
                    inputs=[DocumentType.LITERATURE_MATRIX.value],
                    outputs=[]
                )

                # v6.0: Save to Artifact Store (dual-write mode)
                await self.save_to_artifact_store(
                    content=refs_content,
                    doc_type=DocumentType.VERIFIED_REFERENCES,
                    status=ArtifactStatus.FROZEN
                )
                logger.info(f"Saved to Artifact Store: {self.step_id} - Verified References")

                # Save to file system (backward compatibility)
                await self.save_and_commit(
                    document=refs_doc,
                    commit_message=f"{self.step_id}: Extract Verified References"
                )
                logger.info("Verified References created successfully")
            else:
                logger.warning("Could not extract Verified References from response")

            logger.info(f"Completed {self.step_name} - Generated 4 documents")
            return main_document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.1 failed: {e}")

    def _extract_search_log(self, content: str) -> Optional[str]:
        """
        从 Gemini 响应中提取 Search Query Log

        查找 "## 1) Actions Taken" 部分
        """
        try:
            # 查找 Actions Taken 部分
            pattern = r'##\s*1\)\s*Actions\s+Taken\s*\n(.*?)(?=\n##|\Z)'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            if match:
                actions_content = match.group(1).strip()

                # 创建完整的 Search Query Log 文档
                doc_content = f"""---
doc_type: "00_Search_Query_Log"
version: "1.0"
status: "completed"
created_by: "Gemini"
inputs:
  - "00_Deep_Research_Summary.md"
outputs:
  - "00_Literature_Matrix.md"
---

# Search Query Log

## Actions Taken

{actions_content}

## Extraction Note
This document was automatically extracted from the Deep Research Summary (Step 1.1).
"""
                return doc_content

            logger.warning("Could not find 'Actions Taken' section in response")
            return None

        except Exception as e:
            logger.error(f"Error extracting search log: {e}")
            return None

    def _extract_literature_matrix(self, content: str) -> Optional[str]:
        """
        从 Gemini 响应中提取 Literature Matrix

        查找 "## A) Literature Matrix" 部分
        """
        try:
            # 查找 Literature Matrix 部分
            pattern = r'##\s*A\)\s*Literature\s+Matrix\s*\n(.*?)(?=\n##\s*B\)|\Z)'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            if match:
                matrix_content = match.group(1).strip()

                # 创建完整的 Literature Matrix 文档
                doc_content = f"""---
doc_type: "00_Literature_Matrix"
version: "1.0"
status: "completed"
created_by: "Gemini"
inputs:
  - "00_Deep_Research_Summary.md"
outputs:
  - "00_Reference_QA_Report.md"
---

# Literature Matrix

{matrix_content}

## Extraction Note
This document was automatically extracted from the Deep Research Summary (Step 1.1).
"""
                return doc_content

            logger.warning("Could not find 'Literature Matrix' section in response")
            return None

        except Exception as e:
            logger.error(f"Error extracting literature matrix: {e}")
            return None

    def _extract_references(self, content: str) -> Optional[str]:
        """
        从 Gemini 响应中提取 Verified References

        从 Literature Matrix 中提取所有 DOI/URL
        """
        try:
            # 查找 Literature Matrix 表格
            pattern = r'##\s*A\)\s*Literature\s+Matrix\s*\n(.*?)(?=\n##\s*B\)|\Z)'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)

            if not match:
                return None

            matrix_content = match.group(1)

            # 提取所有 DOI 和 URL
            doi_pattern = r'10\.\d{4,}/[^\s\|\)]+|https?://[^\s\|\)]+|\[https?://[^\]]+\]\([^\)]+\)'
            raw_urls = re.findall(doi_pattern, matrix_content)

            if not raw_urls:
                logger.warning("No DOIs or URLs found in Literature Matrix")
                return None

            # 清理URL格式
            cleaned_urls = []
            invalid_urls = []

            for raw_url in raw_urls:
                if raw_url == "UNKNOWN":
                    continue

                # 清理URL
                clean_url = extract_clean_url(raw_url)

                # 验证URL格式
                is_valid, error_msg = validate_url_format(clean_url)

                if is_valid:
                    cleaned_urls.append(clean_url)
                else:
                    logger.warning(f"Invalid URL format: {clean_url} - {error_msg}")
                    invalid_urls.append((raw_url, error_msg))

            # 去重
            unique_urls = list(dict.fromkeys(cleaned_urls))

            if not unique_urls:
                logger.warning("No valid URLs after cleaning and validation")
                return None

            # 创建 Verified References 文档
            refs_list = "\n".join([f"- {url}" for url in unique_urls])

            # 添加无效URL报告（如果有）
            invalid_report = ""
            if invalid_urls:
                invalid_report = "\n\n## Invalid URLs (需要修复)\n\n"
                invalid_report += "\n".join([f"- {url}: {error}" for url, error in invalid_urls[:5]])  # 只显示前5个

            doc_content = f"""---
doc_type: "00_Verified_References"
version: "1.0"
status: "completed"
created_by: "System"
inputs:
  - "00_Literature_Matrix.md"
outputs: []
---

# Verified References

## Total References: {len(unique_urls)}

## DOI/URL List

{refs_list}

## Statistics
- Total references extracted: {len(raw_urls)}
- Valid DOIs/URLs: {len(unique_urls)}
- Invalid/Unknown references: {len(invalid_urls)}
{invalid_report}

## Extraction Note
This document was automatically extracted from the Literature Matrix (Step 1.1).
References should be validated using the Reference QA tool (Step 1.1b).
"""
            return doc_content

        except Exception as e:
            logger.error(f"Error extracting references: {e}")
            return None

    def _extract_research_directions(self, content: str) -> list[str]:
        """
        从 Deep Research Summary 中提取研究方向

        查找可能的研究方向关键词和列表
        """
        try:
            directions = []

            # 查找 "Research Directions" 或类似的部分
            patterns = [
                r'##\s*(?:Research\s+)?Directions?\s*\n(.*?)(?=\n##|\Z)',
                r'##\s*Potential\s+Topics?\s*\n(.*?)(?=\n##|\Z)',
                r'##\s*Candidate\s+Directions?\s*\n(.*?)(?=\n##|\Z)',
            ]

            for pattern in patterns:
                match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
                if match:
                    section_content = match.group(1).strip()

                    # 提取列表项
                    list_items = re.findall(r'[-*]\s*(.+?)(?=\n[-*]|\n\n|\Z)', section_content, re.DOTALL)

                    for item in list_items:
                        # 清理并提取方向名称（取第一行或前50个字符）
                        direction = item.strip().split('\n')[0][:100]
                        if direction and len(direction) > 10:  # 至少10个字符
                            directions.append(direction)

                    if directions:
                        break

            # 如果没有找到明确的方向列表，尝试从 Literature Matrix 中提取主题
            if not directions:
                # 查找 Literature Matrix 部分
                matrix_pattern = r'##\s*(?:2\)\s*)?Literature\s+Matrix\s*\n(.*?)(?=\n##|\Z)'
                matrix_match = re.search(matrix_pattern, content, re.DOTALL | re.IGNORECASE)

                if matrix_match:
                    matrix_content = matrix_match.group(1).strip()

                    # 提取表格中的主题列（假设格式为 | Topic | ... |）
                    topic_matches = re.findall(r'\|\s*([^|]+?)\s*\|', matrix_content)

                    # 过滤掉表头和分隔符
                    for topic in topic_matches:
                        topic = topic.strip()
                        if (topic and
                            topic.lower() not in ['topic', 'paper', 'method', 'venue', 'year', 'url', '---', '--'] and
                            len(topic) > 10 and
                            not topic.startswith('-')):
                            directions.append(topic[:100])

            # 去重并限制数量
            unique_directions = list(dict.fromkeys(directions))[:5]  # 最多5个方向

            logger.info(f"Extracted {len(unique_directions)} research directions")
            return unique_directions

        except Exception as e:
            logger.error(f"Error extracting research directions: {e}")
            return []


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

            # 获取 Deep Research Summary (with fallback)
            deep_research_content = await self.load_context_with_fallback(
                step_id="step_1_1",
                doc_type=DocumentType.DEEP_RESEARCH_SUMMARY
            )

            if not deep_research_content:
                raise StepExecutionError("Deep Research Summary not found. Please run Step 1.1 first.")

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
                deep_research_content=deep_research_content,
                target_venue=self.project.config.target_venue,
                core_keywords=core_keywords
            )

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
                    "deep_research_included": True,
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
                inputs=[DocumentType.DEEP_RESEARCH_SUMMARY.value],
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

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.2 failed: {e}")


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

            # 渲染 Prompt
            prompt = render_step_1_3_prompt(
                selected_topic_content=selected_topic_content
            )

            # 调用 Gemini（情报官/审稿人角色）
            logger.info("Calling Gemini to perform Killer Prior Check")
            system_prompt = "You are a ruthless reviewer and research librarian. Your role is to find prior work that might invalidate the proposed research."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                wrapper_mode="disabled",  # Disabled: Killer Prior Check has specific structure and very long output
                max_tokens=16384  # Large output: Plan + Actions + Evidence + Direct Collision + Partial Overlap + Changes + Verdict
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
                max_tokens=16384,  # Increased for two complete documents
                wrapper_mode="disabled"  # Disabled: Step generates 2 documents with specific formats (YAML + structured sections)
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


class Step1_1b_ReferenceQA(BaseStep):
    """Step 1.1b: Reference QA (Gemini) - v4.0 NEW"""

    @property
    def step_id(self) -> str:
        return "step_1_1b"

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

            # 获取 Deep Research Summary（包含 Literature Matrix）(with fallback)
            deep_research_content = await self.load_context_with_fallback(
                step_id="step_1_1",
                doc_type=DocumentType.DEEP_RESEARCH_SUMMARY
            )

            if not deep_research_content:
                raise StepExecutionError("Deep Research Summary not found. Please run Step 1.1 first.")

            # 渲染 Prompt
            prompt = render_step_1_1b_prompt(
                literature_matrix_content=deep_research_content
            )

            # 调用 Gemini（研究图书管理员角色）
            logger.info("Calling Gemini to perform Reference QA")
            system_prompt = "You are a meticulous research librarian and citation validator. Your role is to ensure all references are complete, valid, and properly formatted."
            content = await self.gemini_client.chat(
                prompt=prompt,
                context=[],
                system_prompt=system_prompt,
                wrapper_mode="disabled",  # Disabled: Step has specific output format (YAML + sections)
                max_tokens=16384  # Increase token limit for complete report
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
                inputs=[DocumentType.DEEP_RESEARCH_SUMMARY.value],
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

            logger.info(f"Completed {self.step_name}")
            return document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step 1.1b failed: {e}")


class Step1_2b_TopicAlignmentCheck(BaseStep):
    """Step 1.2b: Topic Alignment Check (ChatGPT) - v4.0 NEW"""

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

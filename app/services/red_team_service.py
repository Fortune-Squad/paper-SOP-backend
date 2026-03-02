"""
Controlled Red Team Service

基于 Review Packet 的审查系统，生成可执行的 patch 输出

v6.0 NEW: Structured review and patch generation
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

from app.services.ai_client import ChatGPTClient, GeminiClient

logger = logging.getLogger(__name__)


class ReviewSeverity(str, Enum):
    """审查问题严重性"""
    CRITICAL = "critical"  # 必须修复
    MAJOR = "major"        # 应该修复
    MINOR = "minor"        # 可选修复
    SUGGESTION = "suggestion"  # 建议


class ReviewIssue(BaseModel):
    """审查问题"""
    issue_id: str = Field(..., description="问题 ID")
    severity: ReviewSeverity = Field(..., description="严重性")
    category: str = Field(..., description="问题类别")
    location: str = Field(..., description="问题位置")
    description: str = Field(..., description="问题描述")
    rationale: str = Field(..., description="问题理由")
    suggested_fix: str = Field(..., description="建议修复方案")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewPacket(BaseModel):
    """审查包"""
    document_id: str = Field(..., description="文档 ID")
    document_type: str = Field(..., description="文档类型")
    reviewer_role: str = Field(..., description="审查者角色")
    issues: List[ReviewIssue] = Field(default_factory=list, description="问题列表")
    overall_assessment: str = Field(..., description="总体评估")
    recommendations: List[str] = Field(default_factory=list, description="建议列表")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PatchOperation(BaseModel):
    """Patch 操作"""
    operation_type: str = Field(..., description="操作类型 (add/delete/replace)")
    target_location: str = Field(..., description="目标位置")
    old_content: Optional[str] = Field(None, description="旧内容")
    new_content: str = Field(..., description="新内容")
    rationale: str = Field(..., description="修改理由")


class ExecutablePatch(BaseModel):
    """可执行 Patch"""
    patch_id: str = Field(..., description="Patch ID")
    document_id: str = Field(..., description="文档 ID")
    issue_id: str = Field(..., description="关联的问题 ID")
    operations: List[PatchOperation] = Field(default_factory=list, description="操作列表")
    validation_rules: List[str] = Field(default_factory=list, description="验证规则")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PatchReview(BaseModel):
    """Patch 审查结果"""
    patch_id: str = Field(..., description="Patch ID")
    approved: bool = Field(..., description="是否批准")
    reviewer_comments: str = Field(..., description="审查意见")
    modifications: List[str] = Field(default_factory=list, description="修改建议")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class RedTeamResult(BaseModel):
    """Red Team 完整结果"""
    review_packet: ReviewPacket
    patches: List[ExecutablePatch]
    patch_reviews: List[PatchReview]
    execution_time: float = Field(..., description="执行时间（秒）")
    created_at: datetime = Field(default_factory=datetime.now)


class ControlledRedTeamService:
    """
    Controlled Red Team 服务

    三阶段审查流程：
    1. Review (Gemini): 生成 Review Packet
    2. Patch (Gemini): 生成可执行 Patch
    3. Planner Review (ChatGPT): 审查 Patch
    4. Patch Application (System): 应用批准的 Patch (v6.0 Phase 3)
    """

    def __init__(
        self,
        chatgpt_client: Optional[ChatGPTClient] = None,
        gemini_client: Optional[GeminiClient] = None
    ):
        """
        初始化 Red Team 服务

        Args:
            chatgpt_client: ChatGPT 客户端（Planner Reviewer）
            gemini_client: Gemini 客户端（Red Team Reviewer + Patch Generator）
        """
        self.chatgpt_client = chatgpt_client or ChatGPTClient()
        self.gemini_client = gemini_client or GeminiClient()

    async def generate_review_packet(
        self,
        document_id: str,
        document_type: str,
        document_content: str,
        review_criteria: Optional[List[str]] = None
    ) -> ReviewPacket:
        """
        Phase 1: 生成 Review Packet

        使用 Gemini 作为 "Reviewer #2" 进行批判性审查

        Args:
            document_id: 文档 ID
            document_type: 文档类型
            document_content: 文档内容
            review_criteria: 审查标准

        Returns:
            ReviewPacket: 审查包
        """
        logger.info(f"Generating review packet for document: {document_id}")

        # 构建 prompt - 要求 JSON 格式输出
        criteria_text = "\n".join(f"- {c}" for c in review_criteria) if review_criteria else "Standard review criteria"

        prompt = f"""You are "Reviewer #2" - a critical but constructive peer reviewer. Review the following document and identify issues:

Document ID: {document_id}
Document Type: {document_type}

Review Criteria:
{criteria_text}

Document Content:
{document_content}

Please provide a comprehensive review identifying:
1. Critical Issues (must fix): Fundamental flaws, logical errors, missing key components
2. Major Issues (should fix): Significant weaknesses, unclear arguments, insufficient evidence
3. Minor Issues (optional fix): Style issues, minor inconsistencies, formatting
4. Suggestions: Improvements, enhancements, alternative approaches

**IMPORTANT: You MUST respond with a valid JSON object in the following format:**

```json
{{
  "issues": [
    {{
      "issue_id": "C1",
      "severity": "critical",
      "category": "logic",
      "location": "Section 2, Paragraph 1",
      "description": "Brief description of the issue",
      "rationale": "Why this is a problem",
      "suggested_fix": "How to fix it"
    }}
  ],
  "overall_assessment": "2-3 sentences summarizing the review",
  "recommendations": [
    "Recommendation 1",
    "Recommendation 2",
    "Recommendation 3"
  ]
}}
```

**Rules:**
- severity must be one of: "critical", "major", "minor", "suggestion"
- category examples: "logic", "evidence", "clarity", "structure", "methodology", "presentation"
- issue_id format: C1, C2 (critical), M1, M2 (major), m1, m2 (minor), S1, S2 (suggestion)
- Provide at least 2-5 issues
- Be critical but constructive

**Output only the JSON object, no additional text.**"""

        # 使用 Gemini（Red Team Reviewer 角色）
        # 使用 disabled 模式避免 wrapper 干扰 JSON 输出
        response = await self.gemini_client.chat(
            prompt=prompt,
            system_prompt="You are 'Reviewer #2' - a critical but constructive peer reviewer. You always respond with valid JSON.",
            wrapper_mode="disabled"  # 使用 disabled 模式确保 JSON 格式
        )

        # 解析响应
        review_packet = self._parse_review_packet(response, document_id, document_type)

        logger.info(f"Review packet generated: {len(review_packet.issues)} issues found")

        return review_packet

    async def generate_patches(
        self,
        review_packet: ReviewPacket,
        document_content: str
    ) -> List[ExecutablePatch]:
        """
        Phase 2: 生成可执行 Patch

        使用 Gemini 为每个 critical/major 问题生成 patch

        Args:
            review_packet: 审查包
            document_content: 原始文档内容

        Returns:
            List[ExecutablePatch]: Patch 列表
        """
        logger.info(f"Generating patches for {len(review_packet.issues)} issues")

        patches = []

        # 只为 critical 和 major 问题生成 patch
        critical_major_issues = [
            issue for issue in review_packet.issues
            if issue.severity in [ReviewSeverity.CRITICAL, ReviewSeverity.MAJOR]
        ]

        for issue in critical_major_issues:
            # 构建 prompt - 要求 JSON 格式输出
            prompt = f"""You are a patch generator. Create an executable patch to fix the following issue:

Issue ID: {issue.issue_id}
Severity: {issue.severity.value}
Category: {issue.category}
Location: {issue.location}
Description: {issue.description}
Rationale: {issue.rationale}
Suggested Fix: {issue.suggested_fix}

Original Document Content:
{document_content}

**IMPORTANT: You MUST respond with a valid JSON object in the following format:**

```json
{{
  "operations": [
    {{
      "operation_type": "replace",
      "target_location": "Section 2, Paragraph 1",
      "old_content": "The exact text to be replaced",
      "new_content": "The new improved text",
      "rationale": "Why this change fixes the issue"
    }}
  ],
  "validation_rules": [
    "Check that new content maintains document flow",
    "Verify all references are still valid"
  ]
}}
```

**Rules:**
- operation_type must be one of: "add", "delete", "replace"
- target_location must be precise (e.g., "Section 2, Paragraph 3, Line 5")
- old_content is required for "replace" and "delete" operations
- new_content is required for "add" and "replace" operations
- Provide 1-3 operations per patch
- Each operation should be minimal and precise

**Output only the JSON object, no additional text.**"""

            # 使用 Gemini（Patch Generator 角色）
            response = await self.gemini_client.chat(
                prompt=prompt,
                system_prompt="You are a patch generator specializing in creating precise, executable patches. You always respond with valid JSON.",
                wrapper_mode="disabled"  # 使用 disabled 模式确保 JSON 格式
            )

            # 解析响应
            patch = self._parse_patch(response, review_packet.document_id, issue.issue_id)
            patches.append(patch)

            logger.info(f"Patch generated for issue {issue.issue_id}: {len(patch.operations)} operations")

        return patches

    async def review_patches(
        self,
        patches: List[ExecutablePatch],
        review_packet: ReviewPacket,
        document_content: str
    ) -> List[PatchReview]:
        """
        Phase 3: Planner 审查 Patch

        使用 ChatGPT 审查生成的 patch

        Args:
            patches: Patch 列表
            review_packet: 原始审查包
            document_content: 原始文档内容

        Returns:
            List[PatchReview]: Patch 审查结果列表
        """
        logger.info(f"Reviewing {len(patches)} patches")

        patch_reviews = []

        for patch in patches:
            # 找到对应的 issue
            issue = next(
                (i for i in review_packet.issues if i.issue_id == patch.issue_id),
                None
            )

            if not issue:
                logger.warning(f"Issue {patch.issue_id} not found for patch {patch.patch_id}")
                continue

            # 构建 prompt - 要求 JSON 格式输出
            operations_text = "\n".join([
                f"- {op.operation_type}: {op.target_location}\n  Old: {op.old_content}\n  New: {op.new_content}\n  Rationale: {op.rationale}"
                for op in patch.operations
            ])

            prompt = f"""You are a technical reviewer (Planner role). Review the following patch:

Patch ID: {patch.patch_id}
Issue ID: {patch.issue_id}

Original Issue:
- Severity: {issue.severity.value}
- Category: {issue.category}
- Description: {issue.description}
- Suggested Fix: {issue.suggested_fix}

Proposed Patch Operations:
{operations_text}

Original Document Context:
{document_content[:1000]}...

Please review this patch and determine:
1. Is the patch correct and complete?
2. Does it fully address the issue?
3. Are there any side effects or risks?
4. Should it be approved, modified, or rejected?

**IMPORTANT: You MUST respond with a valid JSON object in the following format:**

```json
{{
  "approved": true,
  "reviewer_comments": "2-3 sentences explaining the decision",
  "modifications": [
    "Modification 1 (if needed)",
    "Modification 2 (if needed)"
  ]
}}
```

**Rules:**
- approved must be a boolean (true/false)
- reviewer_comments should be 2-3 sentences
- modifications is an array of strings (empty if approved without changes)
- Approve if the patch correctly fixes the issue without side effects
- Reject if the patch is incorrect, incomplete, or introduces new problems
- Suggest modifications if the patch is mostly correct but needs adjustments

**Output only the JSON object, no additional text.**"""

            # 使用 ChatGPT（Planner Reviewer 角色）
            response = await self.chatgpt_client.chat(
                prompt=prompt,
                system_prompt="You are a technical reviewer (Planner role) responsible for ensuring patch quality. You always respond with valid JSON."
            )

            # 解析响应
            patch_review = self._parse_patch_review(response, patch.patch_id)
            patch_reviews.append(patch_review)

            logger.info(f"Patch {patch.patch_id} reviewed: {'approved' if patch_review.approved else 'not approved'}")

        return patch_reviews

    async def run_red_team(
        self,
        document_id: str,
        document_type: str,
        document_content: str,
        review_criteria: Optional[List[str]] = None
    ) -> RedTeamResult:
        """
        运行完整的 Red Team 流程

        Args:
            document_id: 文档 ID
            document_type: 文档类型
            document_content: 文档内容
            review_criteria: 审查标准

        Returns:
            RedTeamResult: 完整结果
        """
        logger.info(f"Running Controlled Red Team for document: {document_id}")

        import time
        start_time = time.time()

        # Phase 1: Review
        review_packet = await self.generate_review_packet(
            document_id, document_type, document_content, review_criteria
        )

        # Phase 2: Patch Generation
        patches = await self.generate_patches(review_packet, document_content)

        # Phase 3: Planner Review
        patch_reviews = await self.review_patches(patches, review_packet, document_content)

        execution_time = time.time() - start_time

        logger.info(f"Red Team completed in {execution_time:.2f}s")

        return RedTeamResult(
            review_packet=review_packet,
            patches=patches,
            patch_reviews=patch_reviews,
            execution_time=execution_time
        )

    def _parse_review_packet(
        self,
        response: str,
        document_id: str,
        document_type: str
    ) -> ReviewPacket:
        """
        解析审查包（从 JSON 响应）

        Args:
            response: AI 响应（JSON 格式）
            document_id: 文档 ID
            document_type: 文档类型

        Returns:
            ReviewPacket: 解析后的审查包
        """
        import json
        import re

        try:
            # 提取 JSON（可能被 markdown 代码块包裹）
            json_text = self._extract_json(response)

            # 解析 JSON
            data = json.loads(json_text)

            # 构建 ReviewIssue 列表
            issues = []
            for issue_data in data.get("issues", []):
                try:
                    # 验证 severity
                    severity_str = issue_data.get("severity", "suggestion").lower()
                    if severity_str not in ["critical", "major", "minor", "suggestion"]:
                        logger.warning(f"Invalid severity: {severity_str}, defaulting to 'suggestion'")
                        severity_str = "suggestion"

                    issue = ReviewIssue(
                        issue_id=issue_data.get("issue_id", f"UNKNOWN_{len(issues)+1}"),
                        severity=ReviewSeverity(severity_str),
                        category=issue_data.get("category", "general"),
                        location=issue_data.get("location", "Unknown location"),
                        description=issue_data.get("description", "No description provided"),
                        rationale=issue_data.get("rationale", "No rationale provided"),
                        suggested_fix=issue_data.get("suggested_fix", "No fix suggested")
                    )
                    issues.append(issue)
                except Exception as e:
                    logger.warning(f"Failed to parse issue: {e}, skipping")
                    continue

            # 构建 ReviewPacket
            review_packet = ReviewPacket(
                document_id=document_id,
                document_type=document_type,
                reviewer_role="Reviewer #2",
                issues=issues,
                overall_assessment=data.get("overall_assessment", "No overall assessment provided"),
                recommendations=data.get("recommendations", []),
                metadata={
                    "raw_response_length": len(response),
                    "parsed_successfully": True
                }
            )

            logger.info(f"Successfully parsed review packet: {len(issues)} issues")
            return review_packet

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response[:500]}...")

            # 回退到文本解析
            return self._parse_review_packet_fallback(response, document_id, document_type)

        except Exception as e:
            logger.error(f"Unexpected error parsing review packet: {e}")
            return self._parse_review_packet_fallback(response, document_id, document_type)

    def _parse_review_packet_fallback(
        self,
        response: str,
        document_id: str,
        document_type: str
    ) -> ReviewPacket:
        """
        回退解析方法（当 JSON 解析失败时）

        尝试从文本中提取结构化信息
        """
        logger.warning("Using fallback text parsing for review packet")

        import re

        issues = []

        # 尝试提取问题（简单的模式匹配）
        # 查找类似 "C1:", "M1:", "m1:", "S1:" 的模式
        issue_pattern = r'([CMS]\d+):\s*(.+?)(?=\n[CMS]\d+:|\n\n|$)'
        matches = re.finditer(issue_pattern, response, re.DOTALL)

        for match in matches:
            issue_id = match.group(1)
            issue_text = match.group(2).strip()

            # 确定严重性
            if issue_id.startswith('C'):
                severity = ReviewSeverity.CRITICAL
            elif issue_id.startswith('M'):
                severity = ReviewSeverity.MAJOR
            elif issue_id.startswith('m'):
                severity = ReviewSeverity.MINOR
            else:
                severity = ReviewSeverity.SUGGESTION

            issues.append(ReviewIssue(
                issue_id=issue_id,
                severity=severity,
                category="general",
                location="See review text",
                description=issue_text[:200],  # 前 200 字符
                rationale="See full review",
                suggested_fix="See review recommendations"
            ))

        # 如果没有找到任何问题，创建一个默认问题
        if not issues:
            issues.append(ReviewIssue(
                issue_id="PARSE_ERROR",
                severity=ReviewSeverity.SUGGESTION,
                category="parsing",
                location="N/A",
                description="Failed to parse structured review, see raw response",
                rationale="JSON parsing failed",
                suggested_fix="Review the raw AI response"
            ))

        return ReviewPacket(
            document_id=document_id,
            document_type=document_type,
            reviewer_role="Reviewer #2",
            issues=issues,
            overall_assessment="Parsing failed - see raw response",
            recommendations=["Review raw AI response for details"],
            metadata={
                "raw_response_length": len(response),
                "parsed_successfully": False,
                "fallback_used": True,
                "raw_response": response[:1000]  # 保存前 1000 字符
            }
        )

    def _parse_patch(
        self,
        response: str,
        document_id: str,
        issue_id: str
    ) -> ExecutablePatch:
        """
        解析 Patch（从 JSON 响应）

        Args:
            response: AI 响应（JSON 格式）
            document_id: 文档 ID
            issue_id: 问题 ID

        Returns:
            ExecutablePatch: 解析后的 Patch
        """
        import json
        import uuid

        try:
            # 提取 JSON
            json_text = self._extract_json(response)

            # 解析 JSON
            data = json.loads(json_text)

            # 构建 PatchOperation 列表
            operations = []
            for op_data in data.get("operations", []):
                try:
                    # 验证 operation_type
                    op_type = op_data.get("operation_type", "replace").lower()
                    if op_type not in ["add", "delete", "replace"]:
                        logger.warning(f"Invalid operation_type: {op_type}, defaulting to 'replace'")
                        op_type = "replace"

                    operation = PatchOperation(
                        operation_type=op_type,
                        target_location=op_data.get("target_location", "Unknown location"),
                        old_content=op_data.get("old_content"),
                        new_content=op_data.get("new_content", ""),
                        rationale=op_data.get("rationale", "No rationale provided")
                    )
                    operations.append(operation)
                except Exception as e:
                    logger.warning(f"Failed to parse operation: {e}, skipping")
                    continue

            # 构建 ExecutablePatch
            patch = ExecutablePatch(
                patch_id=f"patch_{uuid.uuid4().hex[:8]}",
                document_id=document_id,
                issue_id=issue_id,
                operations=operations,
                validation_rules=data.get("validation_rules", []),
                metadata={
                    "raw_response_length": len(response),
                    "parsed_successfully": True
                }
            )

            logger.info(f"Successfully parsed patch: {len(operations)} operations")
            return patch

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response[:500]}...")

            # 回退到默认 patch
            return self._parse_patch_fallback(response, document_id, issue_id)

        except Exception as e:
            logger.error(f"Unexpected error parsing patch: {e}")
            return self._parse_patch_fallback(response, document_id, issue_id)

    def _parse_patch_fallback(
        self,
        response: str,
        document_id: str,
        issue_id: str
    ) -> ExecutablePatch:
        """
        回退解析方法（当 JSON 解析失败时）
        """
        import uuid

        logger.warning("Using fallback parsing for patch")

        # 创建一个默认的 patch
        return ExecutablePatch(
            patch_id=f"patch_{uuid.uuid4().hex[:8]}",
            document_id=document_id,
            issue_id=issue_id,
            operations=[
                PatchOperation(
                    operation_type="replace",
                    target_location="See raw response",
                    old_content="N/A",
                    new_content="See raw response for suggested changes",
                    rationale="JSON parsing failed - manual review required"
                )
            ],
            validation_rules=["Manual review required"],
            metadata={
                "raw_response_length": len(response),
                "parsed_successfully": False,
                "fallback_used": True,
                "raw_response": response[:1000]
            }
        )

    def _parse_patch_review(
        self,
        response: str,
        patch_id: str
    ) -> PatchReview:
        """
        解析 Patch 审查（从 JSON 响应）

        Args:
            response: AI 响应（JSON 格式）
            patch_id: Patch ID

        Returns:
            PatchReview: 解析后的审查结果
        """
        import json

        try:
            # 提取 JSON
            json_text = self._extract_json(response)

            # 解析 JSON
            data = json.loads(json_text)

            # 构建 PatchReview
            patch_review = PatchReview(
                patch_id=patch_id,
                approved=data.get("approved", False),
                reviewer_comments=data.get("reviewer_comments", "No comments provided"),
                modifications=data.get("modifications", [])
            )

            logger.info(f"Successfully parsed patch review: approved={patch_review.approved}")
            return patch_review

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response[:500]}...")

            # 回退到默认审查
            return self._parse_patch_review_fallback(response, patch_id)

        except Exception as e:
            logger.error(f"Unexpected error parsing patch review: {e}")
            return self._parse_patch_review_fallback(response, patch_id)

    def _parse_patch_review_fallback(
        self,
        response: str,
        patch_id: str
    ) -> PatchReview:
        """
        回退解析方法（当 JSON 解析失败时）
        """
        logger.warning("Using fallback parsing for patch review")

        # 尝试从文本中判断是否批准
        response_lower = response.lower()
        approved = any(word in response_lower for word in ["approve", "approved", "accept", "looks good", "lgtm"])

        return PatchReview(
            patch_id=patch_id,
            approved=approved,
            reviewer_comments=f"Parsing failed - see raw response. Auto-detected: {'approved' if approved else 'not approved'}",
            modifications=["Manual review required - JSON parsing failed"],
            metadata={
                "raw_response_length": len(response),
                "parsed_successfully": False,
                "fallback_used": True,
                "raw_response": response[:1000]
            }
        )

    def _extract_json(self, text: str) -> str:
        """
        从文本中提取 JSON（处理 markdown 代码块）

        Args:
            text: 包含 JSON 的文本

        Returns:
            str: 提取的 JSON 字符串
        """
        import re

        # 尝试提取 markdown 代码块中的 JSON
        # 匹配 ```json ... ``` 或 ``` ... ```
        code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        match = re.search(code_block_pattern, text, re.DOTALL)

        if match:
            return match.group(1).strip()

        # 如果没有代码块，尝试查找 JSON 对象
        # 查找第一个 { 到最后一个 }
        json_pattern = r'\{.*\}'
        match = re.search(json_pattern, text, re.DOTALL)

        if match:
            return match.group(0)

        # 如果都没找到，返回原文本
        return text.strip()

    async def validate_patch(
        self,
        patch: ExecutablePatch,
        document_content: str
    ) -> tuple[bool, str]:
        """
        验证 Patch 是否可以安全应用

        Args:
            patch: ExecutablePatch 对象
            document_content: 文档内容

        Returns:
            tuple[bool, str]: (是否有效, 错误信息)
        """
        logger.info(f"Validating patch {patch.patch_id}")

        for i, operation in enumerate(patch.operations, 1):
            # 验证操作类型
            if operation.operation_type not in ["add", "delete", "replace"]:
                return False, f"Operation {i}: Invalid operation type '{operation.operation_type}'"

            # 对于 delete 和 replace 操作，验证 old_content 存在
            if operation.operation_type in ["delete", "replace"]:
                if not operation.old_content:
                    return False, f"Operation {i}: Missing old_content for {operation.operation_type} operation"

                # 验证 old_content 在文档中存在
                if operation.old_content not in document_content:
                    return False, f"Operation {i}: old_content not found in document"

            # 对于 add 和 replace 操作，验证 new_content 存在
            if operation.operation_type in ["add", "replace"]:
                if not operation.new_content:
                    return False, f"Operation {i}: Missing new_content for {operation.operation_type} operation"

        logger.info(f"Patch {patch.patch_id} validation passed")
        return True, "Valid"

    async def apply_patch(
        self,
        patch: ExecutablePatch,
        document_content: str
    ) -> tuple[str, List[str]]:
        """
        应用 Patch 到文档

        Args:
            patch: ExecutablePatch 对象
            document_content: 原始文档内容

        Returns:
            tuple[str, List[str]]: (更新后的文档内容, 应用日志)
        """
        logger.info(f"Applying patch {patch.patch_id} with {len(patch.operations)} operations")

        # 验证 patch
        is_valid, error_msg = await self.validate_patch(patch, document_content)
        if not is_valid:
            logger.error(f"Patch validation failed: {error_msg}")
            raise ValueError(f"Patch validation failed: {error_msg}")

        updated_content = document_content
        apply_log = []

        # 应用每个操作
        for i, operation in enumerate(patch.operations, 1):
            try:
                if operation.operation_type == "replace":
                    # Replace 操作
                    if operation.old_content not in updated_content:
                        error_msg = f"Operation {i}: old_content not found in document (may have been modified by previous operation)"
                        logger.warning(error_msg)
                        apply_log.append(f"⚠️ {error_msg}")
                        continue

                    updated_content = updated_content.replace(
                        operation.old_content,
                        operation.new_content,
                        1  # 只替换第一次出现
                    )
                    apply_log.append(f"✅ Operation {i}: Replaced content at {operation.target_location}")
                    logger.info(f"Applied replace operation {i}")

                elif operation.operation_type == "delete":
                    # Delete 操作
                    if operation.old_content not in updated_content:
                        error_msg = f"Operation {i}: old_content not found in document"
                        logger.warning(error_msg)
                        apply_log.append(f"⚠️ {error_msg}")
                        continue

                    updated_content = updated_content.replace(
                        operation.old_content,
                        "",
                        1  # 只删除第一次出现
                    )
                    apply_log.append(f"✅ Operation {i}: Deleted content at {operation.target_location}")
                    logger.info(f"Applied delete operation {i}")

                elif operation.operation_type == "add":
                    # Add 操作
                    # 尝试在目标位置附近添加内容
                    # 如果指定了 old_content，在其后添加
                    if operation.old_content and operation.old_content in updated_content:
                        updated_content = updated_content.replace(
                            operation.old_content,
                            operation.old_content + "\n\n" + operation.new_content,
                            1
                        )
                        apply_log.append(f"✅ Operation {i}: Added content after {operation.target_location}")
                    else:
                        # 否则添加到文档末尾
                        updated_content += "\n\n" + operation.new_content
                        apply_log.append(f"✅ Operation {i}: Added content at end of document")
                    logger.info(f"Applied add operation {i}")

            except Exception as e:
                error_msg = f"Operation {i}: Failed to apply - {str(e)}"
                logger.error(error_msg)
                apply_log.append(f"❌ {error_msg}")

        logger.info(f"Patch {patch.patch_id} applied successfully: {len([l for l in apply_log if l.startswith('✅')])} operations succeeded")

        return updated_content, apply_log


# 全局 Red Team 实例
_red_team_instance = None


def get_red_team_service() -> ControlledRedTeamService:
    """
    获取全局 Red Team Service 实例

    Returns:
        ControlledRedTeamService: Red Team 服务实例
    """
    global _red_team_instance
    if _red_team_instance is None:
        _red_team_instance = ControlledRedTeamService()
    return _red_team_instance

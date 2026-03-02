"""
S-1 Bootloader Service

预项目启动阶段服务，生成 Domain Dictionary、OOT Candidates 和 Resource Card

v6.0 NEW: Pre-project initialization service
"""
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.models.bootloader import (
    DomainDictionary,
    DomainTerm,
    OOTCandidates,
    OOTCandidate,
    ResourceCard,
    ResourceItem,
    BootloaderResult
)
from app.services.ai_client import ChatGPTClient, GeminiClient

logger = logging.getLogger(__name__)


class BootloaderService:
    """
    S-1 Bootloader 服务

    在项目正式启动前，生成领域知识和资源准备
    """

    def __init__(
        self,
        chatgpt_client: Optional[ChatGPTClient] = None,
        gemini_client: Optional[GeminiClient] = None
    ):
        """
        初始化 Bootloader 服务

        Args:
            chatgpt_client: ChatGPT 客户端（用于结构化分析）
            gemini_client: Gemini 客户端（用于深度研究）
        """
        self.chatgpt_client = chatgpt_client or ChatGPTClient()
        self.gemini_client = gemini_client or GeminiClient()

    async def generate_domain_dictionary(
        self,
        domain: str,
        context: Optional[str] = None
    ) -> DomainDictionary:
        """
        生成领域词典

        Args:
            domain: 研究领域
            context: 额外上下文信息

        Returns:
            DomainDictionary: 领域词典
        """
        logger.info(f"Generating domain dictionary for: {domain}")

        # 构建 prompt
        prompt = f"""You are a domain expert. Generate a comprehensive domain dictionary for the following research domain:

Domain: {domain}

{f"Context: {context}" if context else ""}

Please identify and define 10-15 key terms that are essential for understanding this domain. For each term, provide:
1. Term name
2. Clear definition
3. Synonyms (if any)
4. Related terms
5. Importance level (high/medium/low)

Focus on terms that are:
- Fundamental to the domain
- Frequently used in research papers
- Important for understanding state-of-the-art work
- Potentially ambiguous or domain-specific

Format your response as a structured list."""

        # 使用 ChatGPT 生成（结构化任务）
        response = await self.chatgpt_client.chat(
            system_prompt="You are a domain expert specializing in technical terminology and definitions.",
            prompt=prompt
        )

        # 解析响应（简化版，实际应该更robust）
        terms = self._parse_domain_terms(response)

        return DomainDictionary(
            domain=domain,
            terms=terms,
            metadata={
                "context": context,
                "generated_by": "chatgpt",
                "term_count": len(terms)
            }
        )

    async def generate_oot_candidates(
        self,
        domain: str,
        constraints: Optional[str] = None
    ) -> OOTCandidates:
        """
        生成 Out-of-Tree (OOT) 候选主题

        Args:
            domain: 研究领域
            constraints: 约束条件

        Returns:
            OOTCandidates: OOT 候选主题列表
        """
        logger.info(f"Generating OOT candidates for: {domain}")

        # 构建 prompt
        prompt = f"""You are a research strategist. Identify 5-8 promising "Out-of-Tree" (OOT) research topics in the following domain:

Domain: {domain}

{f"Constraints: {constraints}" if constraints else ""}

OOT topics are research directions that:
- Are NOT mainstream or heavily explored
- Have high novelty potential
- Are feasible with current technology
- Could have significant impact if successful
- Represent "blue ocean" opportunities

For each OOT candidate, provide:
1. Topic name
2. Brief description
3. Novelty score (0-1)
4. Feasibility score (0-1)
5. Impact score (0-1)
6. Rationale for recommendation
7. Potential risks

Format your response as a structured list."""

        # 使用 Gemini 生成（创意任务）
        response = await self.gemini_client.chat(
            system_prompt="You are a creative research strategist specializing in identifying novel research opportunities.",
            prompt=prompt,
            wrapper_mode="lite"  # 使用 lite 模式获取 Evidence
        )

        # 解析响应
        candidates = self._parse_oot_candidates(response)

        return OOTCandidates(
            domain=domain,
            candidates=candidates,
            metadata={
                "constraints": constraints,
                "generated_by": "gemini",
                "candidate_count": len(candidates)
            }
        )

    async def generate_resource_card(
        self,
        domain: str,
        focus_areas: Optional[List[str]] = None
    ) -> ResourceCard:
        """
        生成资源卡片

        Args:
            domain: 研究领域
            focus_areas: 关注领域

        Returns:
            ResourceCard: 资源卡片
        """
        logger.info(f"Generating resource card for: {domain}")

        # 构建 prompt
        prompt = f"""You are a research resource specialist. Identify key resources for the following research domain:

Domain: {domain}

{f"Focus Areas: {', '.join(focus_areas)}" if focus_areas else ""}

Please identify 15-20 essential resources across these categories:
1. Datasets (public/restricted/private)
2. Tools and frameworks
3. Seminal papers and surveys
4. Expert researchers and groups

For each resource, provide:
1. Resource type
2. Name
3. Description
4. URL (if available)
5. Availability status
6. Relevance score (0-1)

Prioritize resources that are:
- Widely used in the community
- High quality and well-maintained
- Accessible (prefer public over restricted)
- Relevant to current research trends

Format your response as a structured list."""

        # 使用 Gemini 生成（研究任务）
        response = await self.gemini_client.chat(
            system_prompt="You are a research resource specialist with deep knowledge of academic resources and tools.",
            prompt=prompt,
            wrapper_mode="lite"
        )

        # 解析响应
        resources = self._parse_resources(response)

        return ResourceCard(
            domain=domain,
            resources=resources,
            metadata={
                "focus_areas": focus_areas,
                "generated_by": "gemini",
                "resource_count": len(resources)
            }
        )

    async def run_bootloader(
        self,
        domain: str,
        context: Optional[str] = None,
        constraints: Optional[str] = None,
        focus_areas: Optional[List[str]] = None
    ) -> BootloaderResult:
        """
        运行完整的 Bootloader 流程

        Args:
            domain: 研究领域
            context: 额外上下文
            constraints: 约束条件
            focus_areas: 关注领域

        Returns:
            BootloaderResult: Bootloader 执行结果
        """
        logger.info(f"Running S-1 Bootloader for domain: {domain}")
        start_time = time.time()

        # 并行生成三个组件
        domain_dict = await self.generate_domain_dictionary(domain, context)
        oot_candidates = await self.generate_oot_candidates(domain, constraints)
        resource_card = await self.generate_resource_card(domain, focus_areas)

        execution_time = time.time() - start_time

        logger.info(f"Bootloader completed in {execution_time:.2f}s")

        return BootloaderResult(
            domain_dictionary=domain_dict,
            oot_candidates=oot_candidates,
            resource_card=resource_card,
            execution_time=execution_time
        )

    def _parse_domain_terms(self, response: str) -> List[DomainTerm]:
        """
        解析领域术语（简化版）

        实际实现应该更robust，使用结构化解析
        """
        # 简化实现：返回示例数据
        # 实际应该解析 AI 响应
        return [
            DomainTerm(
                term="Example Term",
                definition="Example definition from AI response",
                synonyms=["synonym1"],
                related_terms=["related1"],
                importance="high"
            )
        ]

    def _parse_oot_candidates(self, response: str) -> List[OOTCandidate]:
        """
        解析 OOT 候选主题（简化版）
        """
        return [
            OOTCandidate(
                topic="Example OOT Topic",
                description="Example description from AI response",
                novelty_score=0.8,
                feasibility_score=0.7,
                impact_score=0.9,
                rationale="Example rationale",
                risks=["risk1", "risk2"]
            )
        ]

    def _parse_resources(self, response: str) -> List[ResourceItem]:
        """
        解析资源列表（简化版）
        """
        return [
            ResourceItem(
                resource_type="dataset",
                name="Example Dataset",
                description="Example description from AI response",
                url="https://example.com",
                availability="public",
                relevance_score=0.9
            )
        ]

    def format_domain_dictionary(self, domain_dict: DomainDictionary) -> str:
        """
        格式化 Domain Dictionary 为 Markdown

        Args:
            domain_dict: DomainDictionary 对象

        Returns:
            str: Markdown 格式的文档
        """
        content = f"""# Domain Dictionary: {domain_dict.domain}

**Generated**: {domain_dict.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Term Count**: {len(domain_dict.terms)}

---

## Purpose

This domain dictionary provides clear definitions for key terms in the **{domain_dict.domain}** domain. It eliminates terminology ambiguity and ensures alignment before starting the research project.

---

## Key Terms

"""

        # 按重要性分组
        high_importance = [t for t in domain_dict.terms if t.importance == "high"]
        medium_importance = [t for t in domain_dict.terms if t.importance == "medium"]
        low_importance = [t for t in domain_dict.terms if t.importance == "low"]

        # High Importance Terms
        if high_importance:
            content += "### 🔴 High Importance\n\n"
            for term in high_importance:
                content += f"#### {term.term}\n\n"
                content += f"**Definition**: {term.definition}\n\n"
                if term.synonyms:
                    content += f"**Synonyms**: {', '.join(term.synonyms)}\n\n"
                if term.related_terms:
                    content += f"**Related Terms**: {', '.join(term.related_terms)}\n\n"
                content += "---\n\n"

        # Medium Importance Terms
        if medium_importance:
            content += "### 🟡 Medium Importance\n\n"
            for term in medium_importance:
                content += f"#### {term.term}\n\n"
                content += f"**Definition**: {term.definition}\n\n"
                if term.synonyms:
                    content += f"**Synonyms**: {', '.join(term.synonyms)}\n\n"
                content += "---\n\n"

        # Low Importance Terms
        if low_importance:
            content += "### 🟢 Low Importance\n\n"
            for term in low_importance:
                content += f"#### {term.term}\n\n"
                content += f"**Definition**: {term.definition}\n\n"
                content += "---\n\n"

        # Metadata
        content += f"""---

## Metadata

- **Domain**: {domain_dict.domain}
- **Total Terms**: {len(domain_dict.terms)}
- **High Importance**: {len(high_importance)}
- **Medium Importance**: {len(medium_importance)}
- **Low Importance**: {len(low_importance)}
- **Generated By**: {domain_dict.metadata.get('generated_by', 'system')}
"""

        return content

    def format_oot_candidates(self, oot_candidates: OOTCandidates) -> str:
        """
        格式化 OOT Candidates 为 Markdown

        Args:
            oot_candidates: OOTCandidates 对象

        Returns:
            str: Markdown 格式的文档
        """
        content = f"""# Out-of-Tree (OOT) Candidates: {oot_candidates.domain}

**Generated**: {oot_candidates.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Candidate Count**: {len(oot_candidates.candidates)}

---

## Purpose

This document identifies promising "Out-of-Tree" (OOT) research topics in the **{oot_candidates.domain}** domain. These are non-mainstream research directions with high novelty potential and significant impact opportunity.

---

## Evaluation Criteria

- **Novelty** (0-1): How unique and unexplored is this direction?
- **Feasibility** (0-1): Can this be accomplished with current technology and resources?
- **Impact** (0-1): What is the potential impact if successful?

---

## OOT Candidates

"""

        # 按综合评分排序
        sorted_candidates = sorted(
            oot_candidates.candidates,
            key=lambda c: (c.novelty_score + c.feasibility_score + c.impact_score) / 3,
            reverse=True
        )

        for i, candidate in enumerate(sorted_candidates, 1):
            avg_score = (candidate.novelty_score + candidate.feasibility_score + candidate.impact_score) / 3
            content += f"""### Candidate {i}: {candidate.topic}

**Description**: {candidate.description}

**Scores**:
- Novelty: {candidate.novelty_score:.2f}
- Feasibility: {candidate.feasibility_score:.2f}
- Impact: {candidate.impact_score:.2f}
- **Average**: {avg_score:.2f}

**Rationale**: {candidate.rationale}

**Potential Risks**:
"""
            for risk in candidate.risks:
                content += f"- {risk}\n"
            content += "\n---\n\n"

        # Summary
        content += f"""---

## Summary

**Total OOT Candidates**: {len(oot_candidates.candidates)}
**Average Novelty**: {sum(c.novelty_score for c in oot_candidates.candidates) / len(oot_candidates.candidates):.2f}
**Average Feasibility**: {sum(c.feasibility_score for c in oot_candidates.candidates) / len(oot_candidates.candidates):.2f}
**Average Impact**: {sum(c.impact_score for c in oot_candidates.candidates) / len(oot_candidates.candidates):.2f}

**Note**: These OOT candidates represent "blue ocean" opportunities. They should be evaluated alongside mainstream topics during Step 1.2 (Topic Selection).
"""

        return content

    def format_resource_card(self, resource_card: ResourceCard) -> str:
        """
        格式化 Resource Card 为 Markdown

        Args:
            resource_card: ResourceCard 对象

        Returns:
            str: Markdown 格式的文档
        """
        content = f"""# Resource Card: {resource_card.domain}

**Generated**: {resource_card.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Resource Count**: {len(resource_card.resources)}

---

## Purpose

This resource card identifies key resources (datasets, tools, papers, experts) for the **{resource_card.domain}** domain. It helps identify resource dependencies and constraints before starting the project.

---

## Resources by Category

"""

        # 按类型分组
        resources_by_type = {}
        for resource in resource_card.resources:
            if resource.resource_type not in resources_by_type:
                resources_by_type[resource.resource_type] = []
            resources_by_type[resource.resource_type].append(resource)

        # 定义类型顺序
        type_order = ["dataset", "tool", "paper", "expert", "other"]
        type_icons = {
            "dataset": "📊",
            "tool": "🔧",
            "paper": "📄",
            "expert": "👤",
            "other": "📌"
        }

        for resource_type in type_order:
            if resource_type not in resources_by_type:
                continue

            resources = sorted(
                resources_by_type[resource_type],
                key=lambda r: r.relevance_score,
                reverse=True
            )

            icon = type_icons.get(resource_type, "📌")
            content += f"### {icon} {resource_type.upper()}s\n\n"

            for resource in resources:
                # 可用性图标
                avail_icon = "✅" if resource.availability == "public" else ("🔒" if resource.availability == "restricted" else "❌")

                content += f"#### {resource.name} {avail_icon}\n\n"
                content += f"**Description**: {resource.description}\n\n"
                if resource.url:
                    content += f"**URL**: {resource.url}\n\n"
                content += f"**Availability**: {resource.availability}\n\n"
                content += f"**Relevance**: {resource.relevance_score:.2f}\n\n"
                content += "---\n\n"

        # Summary
        public_count = sum(1 for r in resource_card.resources if r.availability == "public")
        restricted_count = sum(1 for r in resource_card.resources if r.availability == "restricted")
        private_count = sum(1 for r in resource_card.resources if r.availability == "private")

        content += f"""---

## Summary

**Total Resources**: {len(resource_card.resources)}
**By Availability**:
- ✅ Public: {public_count}
- 🔒 Restricted: {restricted_count}
- ❌ Private: {private_count}

**Average Relevance**: {sum(r.relevance_score for r in resource_card.resources) / len(resource_card.resources):.2f}

**Note**: This resource card should be reviewed and updated during Step 0.1 (Project Intake Card).
"""

        return content


# 全局 Bootloader 实例
_bootloader_instance = None


def get_bootloader_service() -> BootloaderService:
    """
    获取全局 Bootloader Service 实例

    Returns:
        BootloaderService: Bootloader 服务实例
    """
    global _bootloader_instance
    if _bootloader_instance is None:
        _bootloader_instance = BootloaderService()
    return _bootloader_instance

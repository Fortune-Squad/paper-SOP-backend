"""
Planner-Hunter Service

三阶段文献搜索架构：Plan (ChatGPT) → Hunt (Gemini) → Synthesis (ChatGPT)

v6.0 NEW: Separation of planning and hunting responsibilities
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.services.ai_client import ChatGPTClient, GeminiClient

logger = logging.getLogger(__name__)


class SearchPlan(BaseModel):
    """搜索计划"""
    research_question: str = Field(..., description="研究问题")
    search_strategy: str = Field(..., description="搜索策略")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    search_queries: List[str] = Field(default_factory=list, description="搜索查询列表")
    inclusion_criteria: List[str] = Field(default_factory=list, description="纳入标准")
    exclusion_criteria: List[str] = Field(default_factory=list, description="排除标准")
    expected_paper_count: int = Field(..., description="预期论文数量")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HuntResult(BaseModel):
    """搜索结果"""
    query: str = Field(..., description="搜索查询")
    papers_found: List[Dict[str, Any]] = Field(default_factory=list, description="找到的论文")
    search_notes: str = Field(..., description="搜索笔记")
    quality_assessment: str = Field(..., description="质量评估")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SynthesisResult(BaseModel):
    """综合结果"""
    research_question: str = Field(..., description="研究问题")
    total_papers: int = Field(..., description="总论文数")
    selected_papers: List[Dict[str, Any]] = Field(default_factory=list, description="精选论文")
    key_findings: List[str] = Field(default_factory=list, description="关键发现")
    research_gaps: List[str] = Field(default_factory=list, description="研究空白")
    recommendations: List[str] = Field(default_factory=list, description="建议")
    synthesis_narrative: str = Field(..., description="综合叙述")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlannerHunterResult(BaseModel):
    """Planner-Hunter 完整结果"""
    search_plan: SearchPlan
    hunt_results: List[HuntResult]
    synthesis: SynthesisResult
    execution_time: float = Field(..., description="执行时间（秒）")
    created_at: datetime = Field(default_factory=datetime.now)


class PlannerHunterService:
    """
    Planner-Hunter 服务

    三阶段文献搜索：
    1. Plan (ChatGPT): 制定搜索计划
    2. Hunt (Gemini): 执行深度搜索
    3. Synthesis (ChatGPT): 综合分析结果
    """

    def __init__(
        self,
        chatgpt_client: Optional[ChatGPTClient] = None,
        gemini_client: Optional[GeminiClient] = None
    ):
        """
        初始化 Planner-Hunter 服务

        Args:
            chatgpt_client: ChatGPT 客户端（Planner + Synthesizer）
            gemini_client: Gemini 客户端（Hunter）
        """
        self.chatgpt_client = chatgpt_client or ChatGPTClient()
        self.gemini_client = gemini_client or GeminiClient()

    async def plan(
        self,
        research_question: str,
        context: Optional[str] = None,
        constraints: Optional[str] = None
    ) -> SearchPlan:
        """
        Phase 1: Plan - 制定搜索计划

        使用 ChatGPT 进行结构化规划

        Args:
            research_question: 研究问题
            context: 额外上下文
            constraints: 约束条件

        Returns:
            SearchPlan: 搜索计划
        """
        logger.info(f"Planning search for: {research_question}")

        # 构建 prompt
        prompt = f"""You are a research planning expert. Create a comprehensive literature search plan for the following research question:

Research Question: {research_question}

{f"Context: {context}" if context else ""}
{f"Constraints: {constraints}" if constraints else ""}

Please provide:
1. Search Strategy: Overall approach to finding relevant literature
2. Keywords: 10-15 key terms to search for
3. Search Queries: 5-8 specific search queries (Boolean combinations)
4. Inclusion Criteria: What papers should be included
5. Exclusion Criteria: What papers should be excluded
6. Expected Paper Count: Estimated number of relevant papers

Focus on:
- Comprehensive coverage of the topic
- Balancing breadth and depth
- Identifying seminal works and recent advances
- Avoiding redundancy

Format your response as a structured plan."""

        # 使用 ChatGPT（Planner 角色）
        response = await self.chatgpt_client.chat(
            system_prompt="You are a research planning expert specializing in systematic literature reviews.",
            user_prompt=prompt
        )

        # 解析响应（简化版）
        plan = self._parse_search_plan(response, research_question)

        logger.info(f"Search plan created: {len(plan.search_queries)} queries, {plan.expected_paper_count} expected papers")

        return plan

    async def hunt(
        self,
        search_plan: SearchPlan
    ) -> List[HuntResult]:
        """
        Phase 2: Hunt - 执行深度搜索

        使用 Gemini 进行深度文献搜索

        Args:
            search_plan: 搜索计划

        Returns:
            List[HuntResult]: 搜索结果列表
        """
        logger.info(f"Hunting literature with {len(search_plan.search_queries)} queries")

        hunt_results = []

        for query in search_plan.search_queries:
            # 构建 prompt
            prompt = f"""You are a literature search specialist. Execute a deep literature search for the following query:

Query: {query}

Research Question: {search_plan.research_question}

Search Strategy: {search_plan.search_strategy}

Inclusion Criteria:
{chr(10).join(f"- {c}" for c in search_plan.inclusion_criteria)}

Exclusion Criteria:
{chr(10).join(f"- {c}" for c in search_plan.exclusion_criteria)}

Please:
1. Search for relevant papers using this query
2. List papers found (title, authors, year, venue, DOI if available)
3. Provide search notes (what worked, what didn't)
4. Assess quality of results (coverage, relevance, recency)

Focus on:
- High-quality venues (top conferences and journals)
- Recent work (last 3-5 years) and seminal papers
- Papers that directly address the research question
- Avoiding duplicates and low-quality sources

Format your response as a structured list."""

            # 使用 Gemini（Hunter 角色）
            response = await self.gemini_client.chat(
                system_prompt="You are a literature search specialist with deep knowledge of academic databases and search techniques.",
                user_prompt=prompt,
                wrapper_mode="lite"  # 使用 lite 模式获取 Evidence
            )

            # 解析响应
            hunt_result = self._parse_hunt_result(response, query)
            hunt_results.append(hunt_result)

            logger.info(f"Hunt completed for query '{query}': {len(hunt_result.papers_found)} papers found")

        return hunt_results

    async def synthesize(
        self,
        search_plan: SearchPlan,
        hunt_results: List[HuntResult]
    ) -> SynthesisResult:
        """
        Phase 3: Synthesis - 综合分析结果

        使用 ChatGPT 进行结构化综合

        Args:
            search_plan: 搜索计划
            hunt_results: 搜索结果列表

        Returns:
            SynthesisResult: 综合结果
        """
        logger.info(f"Synthesizing results from {len(hunt_results)} hunt sessions")

        # 统计总论文数
        total_papers = sum(len(hr.papers_found) for hr in hunt_results)

        # 构建 prompt
        hunt_summary = "\n\n".join([
            f"Query: {hr.query}\nPapers Found: {len(hr.papers_found)}\nNotes: {hr.search_notes}\nQuality: {hr.quality_assessment}"
            for hr in hunt_results
        ])

        prompt = f"""You are a research synthesis expert. Analyze and synthesize the following literature search results:

Research Question: {search_plan.research_question}

Search Plan Summary:
- Strategy: {search_plan.search_strategy}
- Queries: {len(search_plan.search_queries)}
- Expected Papers: {search_plan.expected_paper_count}
- Actual Papers Found: {total_papers}

Hunt Results:
{hunt_summary}

Please provide:
1. Selected Papers: Top 15-20 most relevant papers (title, authors, year, venue, why selected)
2. Key Findings: 5-8 major findings from the literature
3. Research Gaps: 3-5 gaps or opportunities identified
4. Recommendations: 3-5 recommendations for future research
5. Synthesis Narrative: 2-3 paragraph narrative synthesizing the literature

Focus on:
- Identifying the most impactful and relevant papers
- Extracting actionable insights
- Highlighting research opportunities
- Providing clear recommendations

Format your response as a structured synthesis."""

        # 使用 ChatGPT（Synthesizer 角色）
        response = await self.chatgpt_client.chat(
            system_prompt="You are a research synthesis expert specializing in literature review and meta-analysis.",
            user_prompt=prompt
        )

        # 解析响应
        synthesis = self._parse_synthesis(response, search_plan.research_question, total_papers)

        logger.info(f"Synthesis completed: {len(synthesis.selected_papers)} papers selected, {len(synthesis.key_findings)} findings")

        return synthesis

    async def run_planner_hunter(
        self,
        research_question: str,
        context: Optional[str] = None,
        constraints: Optional[str] = None
    ) -> PlannerHunterResult:
        """
        运行完整的 Planner-Hunter 流程

        Args:
            research_question: 研究问题
            context: 额外上下文
            constraints: 约束条件

        Returns:
            PlannerHunterResult: 完整结果
        """
        logger.info(f"Running Planner-Hunter for: {research_question}")

        import time
        start_time = time.time()

        # Phase 1: Plan
        search_plan = await self.plan(research_question, context, constraints)

        # Phase 2: Hunt
        hunt_results = await self.hunt(search_plan)

        # Phase 3: Synthesis
        synthesis = await self.synthesize(search_plan, hunt_results)

        execution_time = time.time() - start_time

        logger.info(f"Planner-Hunter completed in {execution_time:.2f}s")

        return PlannerHunterResult(
            search_plan=search_plan,
            hunt_results=hunt_results,
            synthesis=synthesis,
            execution_time=execution_time
        )

    def _parse_search_plan(self, response: str, research_question: str) -> SearchPlan:
        """解析搜索计划（简化版）"""
        return SearchPlan(
            research_question=research_question,
            search_strategy="Example strategy from AI response",
            keywords=["keyword1", "keyword2", "keyword3"],
            search_queries=["query1", "query2", "query3"],
            inclusion_criteria=["criteria1", "criteria2"],
            exclusion_criteria=["criteria1", "criteria2"],
            expected_paper_count=20,
            metadata={"raw_response_length": len(response)}
        )

    def _parse_hunt_result(self, response: str, query: str) -> HuntResult:
        """解析搜索结果（简化版）"""
        return HuntResult(
            query=query,
            papers_found=[
                {
                    "title": "Example Paper 1",
                    "authors": ["Author A", "Author B"],
                    "year": 2024,
                    "venue": "Example Conference"
                }
            ],
            search_notes="Example search notes from AI response",
            quality_assessment="Example quality assessment",
            metadata={"raw_response_length": len(response)}
        )

    def _parse_synthesis(self, response: str, research_question: str, total_papers: int) -> SynthesisResult:
        """解析综合结果（简化版）"""
        return SynthesisResult(
            research_question=research_question,
            total_papers=total_papers,
            selected_papers=[
                {
                    "title": "Selected Paper 1",
                    "authors": ["Author A"],
                    "year": 2024,
                    "venue": "Top Conference",
                    "reason": "Highly relevant"
                }
            ],
            key_findings=["Finding 1", "Finding 2"],
            research_gaps=["Gap 1", "Gap 2"],
            recommendations=["Recommendation 1", "Recommendation 2"],
            synthesis_narrative="Example synthesis narrative from AI response",
            metadata={"raw_response_length": len(response)}
        )


# 全局 Planner-Hunter 实例
_planner_hunter_instance = None


def get_planner_hunter_service() -> PlannerHunterService:
    """
    获取全局 Planner-Hunter Service 实例

    Returns:
        PlannerHunterService: Planner-Hunter 服务实例
    """
    global _planner_hunter_instance
    if _planner_hunter_instance is None:
        _planner_hunter_instance = PlannerHunterService()
    return _planner_hunter_instance

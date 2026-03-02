"""
S-1 Bootloader Service

预项目启动阶段服务，生成 Domain Dictionary、OOT Candidates 和 Resource Card

v6.0 NEW: Pre-project initialization service
v7.0 FIX: Real AI response parsing (replaces hardcoded example data)
"""
import logging
import re
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
        生成领域词典 (v7 SOP: S-1 Document 1)

        Args:
            domain: 用户的模糊研究想法
            context: 用户背景/资源信息

        Returns:
            DomainDictionary: 领域词典
        """
        logger.info(f"Generating domain dictionary for: {domain}")

        # v7 SOP prompt (6.S-1)
        prompt = f"""ROLE: PI / Domain Analyst
TASK: Break down a fuzzy research intent into structured, searchable components.

INPUT:
- User's fuzzy idea: {domain}
{f"- User's background/resources: {context}" if context else ""}

ACTION — Produce a Domain Dictionary (S-1_Domain_Dictionary.md):

Take the key "big word" in the idea (e.g., "combinatorics", "MIMO", "federated learning").
Break it into 3-8 sub-meanings / sub-fields.

For each sub-meaning, provide:
1. Sub-field name
2. 1-line definition
3. 2 representative papers/methods (with year and venue if known)
4. Whether the user likely means this one (YES / MAYBE / NO) based on the fuzzy idea

End with: "Recommended interpretation: ___" — pick the most likely sub-meaning.

OUTPUT FORMAT:
Begin with YAML front-matter:
```yaml
---
doc_type: DomainDictionary
version: "0.1"
status: draft
created_by: chatgpt
gate_relevance: Loop1
---
```
Then provide the structured list. Each sub-meaning should be clearly numbered."""

        # 使用 ChatGPT 生成（结构化任务）
        response = await self.chatgpt_client.chat(
            system_prompt="You are a PI and domain analyst. Your role is to break down fuzzy research intents into structured, searchable components.",
            prompt=prompt
        )

        # 解析响应
        terms = self._parse_domain_terms(response)

        return DomainDictionary(
            domain=domain,
            terms=terms,
            metadata={
                "context": context,
                "generated_by": "chatgpt",
                "term_count": len(terms),
                "raw_response": response
            }
        )

    async def generate_oot_candidates(
        self,
        domain: str,
        constraints: Optional[str] = None
    ) -> OOTCandidates:
        """
        生成 OOT (Object-Observable-Tool) 候选 (v7 SOP: S-1 Document 2)

        Args:
            domain: 用户的模糊研究想法
            constraints: 约束条件

        Returns:
            OOTCandidates: OOT 候选列表
        """
        logger.info(f"Generating OOT candidates for: {domain}")

        # v7 SOP prompt (6.S-1)
        prompt = f"""ROLE: PI / Domain Analyst
TASK: Generate Object-Observable-Tool (OOT) triples for a fuzzy research idea.

INPUT:
- User's fuzzy idea: {domain}
{f"- Constraints: {constraints}" if constraints else ""}

ACTION — Produce OOT Candidates (S-1_OOT_Candidates.md):

Generate >=3 Object-Observable-Tool triples:
- Object: what entity/system are we studying?
- Observable: what measurable quantity are we trying to predict/optimize/prove?
- Tool: what mathematical/computational method do we apply?

Example: Object=MIMO channel | Observable=BER | Tool=deep unfolding of MMSE

For each OOT triple, provide:
1. Object (the entity/system)
2. Observable (the measurable quantity)
3. Tool (the method/approach)
4. 1-line description of the research direction
5. Feasibility assessment (do we have the data/compute?)
6. Novelty assessment (how explored is this direction?)
7. Venue fit assessment (which venues would accept this?)
8. Key risks

Rank all triples by: feasibility (do we have the data/compute?), novelty, venue fit.

OUTPUT FORMAT:
Begin with YAML front-matter:
```yaml
---
doc_type: OOTCandidates
version: "0.1"
status: draft
created_by: gemini
gate_relevance: Loop1
---
```
Then provide the structured list with clear numbering."""

        # 使用 Gemini 生成（创意任务）
        # meta_tail 模式：OOT prompt 有特定输出格式（编号列表 + OOT triples），
        # lite 模式会截断为 Deliverables 段落导致内容丢失
        response = await self.gemini_client.chat(
            system_prompt="You are a PI and domain analyst specializing in identifying structured research opportunities from fuzzy ideas.",
            prompt=prompt,
            wrapper_mode="meta_tail"
        )

        # 解析响应
        candidates = self._parse_oot_candidates(response)

        return OOTCandidates(
            domain=domain,
            candidates=candidates,
            metadata={
                "constraints": constraints,
                "generated_by": "gemini",
                "candidate_count": len(candidates),
                "raw_response": response
            }
        )

    async def generate_resource_card(
        self,
        domain: str,
        focus_areas: Optional[List[str]] = None
    ) -> ResourceCard:
        """
        生成资源卡片 (v7 SOP: S-1 Document 3)

        v7 SOP: 盘点用户已有的资源和明确的缺口，而非推荐外部资源

        Args:
            domain: 用户的模糊研究想法
            focus_areas: 关注领域（用户提供的背景信息）

        Returns:
            ResourceCard: 资源卡片
        """
        logger.info(f"Generating resource card for: {domain}")

        focus_info = ""
        if focus_areas:
            focus_info = f"- User's mentioned focus areas / background: {', '.join(focus_areas)}"

        # v7 SOP prompt (6.S-1)
        prompt = f"""ROLE: PI / Domain Analyst
TASK: Create a Resource Card that inventories what the user has and what is missing.

INPUT:
- User's fuzzy idea: {domain}
{focus_info}

ACTION — Produce a Resource Card (S-1_Resource_Card.md):

Answer each of the following questions. If the user hasn't provided enough info, make reasonable assumptions and mark them as [ASSUMED — needs confirmation].

1. **Data Access**: What data does the user have access to? (or can simulate?)
   - List each dataset/data source with availability status (have / can-get / need-collect)

2. **Compute & Equipment**: What compute/equipment is available?
   - GPU/CPU resources, cloud access, specialized hardware

3. **Domain Expertise**: What domain expertise exists in the team?
   - List relevant skills and experience levels

4. **Reusable Code & Libraries**: What code/libraries/prior work can be reused?
   - Existing implementations, frameworks, baselines

5. **Hard Constraints**: What are the hard time/budget constraints?
   - Deadlines, budget limits, publication targets

6. **Explicit Gaps**: What is NOT available? (explicit gaps that need to be filled)
   - Missing data, missing expertise, missing compute, etc.

For each resource item, provide:
- Resource type (dataset / tool / expertise / code / constraint / gap)
- Name or description
- Availability (available / partial / missing)
- Relevance to the research idea (high / medium / low)

OUTPUT FORMAT:
Begin with YAML front-matter:
```yaml
---
doc_type: ResourceCard
version: "0.1"
status: draft
created_by: gemini
gate_relevance: Loop1
---
```
Then provide the structured list grouped by category."""

        # 使用 Gemini 生成（研究任务）
        # meta_tail 模式：Resource Card prompt 有特定输出格式（分类列表），
        # lite 模式会截断为 Deliverables 段落导致内容丢失
        response = await self.gemini_client.chat(
            system_prompt="You are a PI and domain analyst. Your role is to inventory research resources and identify gaps for a research project.",
            prompt=prompt,
            wrapper_mode="meta_tail"
        )

        # 解析响应
        resources = self._parse_resources(response)

        return ResourceCard(
            domain=domain,
            resources=resources,
            metadata={
                "focus_areas": focus_areas,
                "generated_by": "gemini",
                "resource_count": len(resources),
                "raw_response": response
            }
        )

    async def run_bootloader(
        self,
        domain: str,
        context: Optional[str] = None,
        constraints: Optional[str] = None,
        focus_areas: Optional[List[str]] = None,
        user_resource_card: Optional[Dict[str, Any]] = None
    ) -> BootloaderResult:
        """
        运行完整的 Bootloader 流程

        Args:
            domain: 研究领域
            context: 额外上下文
            constraints: 约束条件
            focus_areas: 关注领域
            user_resource_card: 用户填写的 Resource Card 表单数据（v7.2 NEW）

        Returns:
            BootloaderResult: Bootloader 执行结果
        """
        logger.info(f"Running S-1 Bootloader for domain: {domain}")
        start_time = time.time()

        # 生成 Domain Dictionary 和 OOT Candidates（始终由 AI 生成）
        domain_dict = await self.generate_domain_dictionary(domain, context)
        oot_candidates = await self.generate_oot_candidates(domain, constraints)

        # Resource Card: 根据用户输入决定生成方式
        if user_resource_card and not user_resource_card.get("is_skipped", False):
            # 用户填写了表单 → 从用户输入构建
            logger.info("Building Resource Card from user input")
            resource_card = self._build_resource_card_from_user_input(domain, user_resource_card)
        elif user_resource_card and user_resource_card.get("is_skipped", False):
            # 用户跳过 → 生成默认纯理论仿真 Resource Card
            logger.info("Building default theoretical Resource Card (user skipped)")
            resource_card = self._build_default_theoretical_resource_card(domain)
        else:
            # 无用户数据 → 保留原 AI 生成路径（向后兼容）
            logger.info("Generating Resource Card via AI (legacy path)")
            resource_card = await self.generate_resource_card(domain, focus_areas)

        execution_time = time.time() - start_time

        logger.info(f"Bootloader completed in {execution_time:.2f}s")

        return BootloaderResult(
            domain_dictionary=domain_dict,
            oot_candidates=oot_candidates,
            resource_card=resource_card,
            execution_time=execution_time
        )

    def _build_resource_card_from_user_input(
        self,
        domain: str,
        user_input: Dict[str, Any]
    ) -> ResourceCard:
        """
        从用户填写的表单数据构建 ResourceCard

        每个非空字段生成一个 ResourceItem，按 v7 SOP 6 分类映射。

        Args:
            domain: 研究领域
            user_input: 用户表单数据

        Returns:
            ResourceCard: 资源卡片
        """
        resources = []
        field_mapping = [
            ("data_access", "dataset", "Data Access"),
            ("compute_equipment", "tool", "Compute & Equipment"),
            ("domain_expertise", "expertise", "Domain Expertise"),
            ("reusable_code", "code", "Reusable Code & Libraries"),
            ("hard_constraints", "constraint", "Hard Constraints"),
            ("explicit_gaps", "gap", "Explicit Gaps"),
        ]

        for field_key, resource_type, display_name in field_mapping:
            value = user_input.get(field_key, "").strip()
            if value:
                resources.append(ResourceItem(
                    resource_type=resource_type,
                    name=display_name,
                    description=value,
                    url=None,
                    availability="available" if resource_type not in ("constraint", "gap") else "missing",
                    relevance_score=1.0
                ))

        return ResourceCard(
            domain=domain,
            resources=resources,
            metadata={
                "source": "user_input",
                "generated_by": "user",
                "resource_count": len(resources),
            }
        )

    def _build_default_theoretical_resource_card(self, domain: str) -> ResourceCard:
        """
        生成默认"纯理论仿真性研究" ResourceCard（用户跳过表单时使用）

        Args:
            domain: 研究领域

        Returns:
            ResourceCard: 默认资源卡片
        """
        resources = [
            ResourceItem(
                resource_type="dataset",
                name="Data Access",
                description="纯理论/仿真研究 — 无需外部数据集，使用合成数据或数学推导",
                url=None,
                availability="available",
                relevance_score=0.5
            ),
            ResourceItem(
                resource_type="tool",
                name="Compute & Equipment",
                description="标准计算资源（个人电脑/实验室服务器），无特殊硬件需求",
                url=None,
                availability="available",
                relevance_score=0.5
            ),
            ResourceItem(
                resource_type="gap",
                name="Explicit Gaps",
                description="用户未提供详细资源信息，建议在后续步骤中补充",
                url=None,
                availability="missing",
                relevance_score=0.8
            ),
        ]

        return ResourceCard(
            domain=domain,
            resources=resources,
            metadata={
                "source": "default_skip",
                "generated_by": "system",
                "resource_count": len(resources),
                "note": "用户跳过 Resource Card 表单，默认为纯理论/仿真性研究"
            }
        )

    def _parse_domain_terms(self, response: str) -> List[DomainTerm]:
        """
        解析领域术语 — 从 AI 响应中提取 sub-field 条目

        v7 prompt 要求格式: 编号列表，每项含 sub-field name, definition,
        representative papers, YES/MAYBE/NO 判断
        """
        terms = []
        if not response or not response.strip():
            return terms

        # 按编号段落拆分 (1. / 1) / ### 1 等)
        sections = re.split(r'\n(?=(?:\d+[\.\)]\s|#{1,3}\s*\d+|#{1,3}\s+Sub))', response)

        for section in sections:
            section = section.strip()
            if not section:
                continue

            # 提取 sub-field name: 编号后的第一行文本
            name_match = re.match(
                r'(?:\d+[\.\)]\s*|#{1,3}\s*\d*\.?\s*)'
                r'(?:\*\*)?(.+?)(?:\*\*)?(?:\n|$)',
                section
            )
            if not name_match:
                continue

            term_name = name_match.group(1).strip().rstrip(':').strip()
            if not term_name or len(term_name) > 200:
                continue

            # 提取 definition (1-line definition)
            def_match = re.search(
                r'(?:definition|定义|描述)[:\s：]*(.+?)(?:\n|$)',
                section, re.IGNORECASE
            )
            definition = def_match.group(1).strip() if def_match else ""
            if not definition:
                # fallback: 取 name 之后的第一行非空文本
                lines = section.split('\n')
                for line in lines[1:]:
                    line = line.strip().lstrip('-*• ')
                    if line and not re.match(r'^(?:representative|papers|whether|user|synonyms|related)', line, re.IGNORECASE):
                        definition = line
                        break

            if not definition:
                definition = section[:200]

            # 提取 YES/MAYBE/NO 判断 → 映射到 importance
            importance = "medium"
            relevance_match = re.search(r'\b(YES|MAYBE|NO)\b', section)
            if relevance_match:
                mapping = {"YES": "high", "MAYBE": "medium", "NO": "low"}
                importance = mapping.get(relevance_match.group(1), "medium")

            # 提取 representative papers 作为 related_terms
            related = []
            paper_match = re.search(
                r'(?:representative|papers|methods|references)[:\s：]*(.+?)(?=\n(?:\d+[\.\)]|#{1,3}|whether|$))',
                section, re.IGNORECASE | re.DOTALL
            )
            if paper_match:
                paper_text = paper_match.group(1)
                paper_items = re.findall(r'[-•*]\s*(.+?)(?:\n|$)', paper_text)
                related = [p.strip() for p in paper_items if p.strip()][:4]

            terms.append(DomainTerm(
                term=term_name,
                definition=definition,
                synonyms=[],
                related_terms=related,
                importance=importance
            ))

        # 如果解析失败，用整个响应作为单条 fallback
        if not terms:
            logger.warning("Domain Dictionary parsing extracted 0 terms, using raw response as fallback")
            terms.append(DomainTerm(
                term="AI Analysis Result",
                definition=response[:500],
                synonyms=[],
                related_terms=[],
                importance="high"
            ))

        return terms

    def _parse_oot_candidates(self, response: str) -> List[OOTCandidate]:
        """
        解析 OOT 候选 — 从 AI 响应中提取 Object-Observable-Tool triples

        v7 prompt 要求格式: >=3 个 OOT triple，每个含 Object, Observable, Tool,
        description, feasibility, novelty, venue fit, risks

        AI 响应典型格式:
          **Triple 1 (Rank 1): Title**
          1. **Object**: ...
          2. **Observable**: ...
          ---
          **Triple 2 (Rank 3): Title**
          ...
        """
        candidates = []
        if not response or not response.strip():
            return candidates

        # 按 triple 级别的分隔符拆分（不是子项编号）
        # 匹配: **Triple N, ### Triple, ### OOT Triple, ### Candidate, --- 分隔线
        sections = re.split(
            r'\n(?=\*\*Triple\s+\d+|#{1,3}\s*(?:OOT\s+)?(?:Triple|Candidate)\s+\d+|---\s*\n\s*\*\*Triple)',
            response
        )

        # 如果上面的模式没拆分出多段，尝试用 --- 分隔线拆分
        if len(sections) <= 1:
            sections = re.split(r'\n---\s*\n', response)

        for section in sections:
            section = section.strip()
            if not section or len(section) < 50:
                continue

            # 必须包含 Object/Observable/Tool 关键词才算是一个 OOT triple
            has_object = re.search(r'\*?\*?object\*?\*?[:\s]', section, re.IGNORECASE)
            has_observable = re.search(r'\*?\*?observable\*?\*?[:\s]', section, re.IGNORECASE)
            has_tool = re.search(r'\*?\*?tool\*?\*?[:\s]', section, re.IGNORECASE)

            if not (has_object and has_observable):
                continue

            # 提取 Object
            obj_match = re.search(
                r'(?:object|对象)[:\s：|]*(.+?)(?:\n|\||$)',
                section, re.IGNORECASE
            )
            # 提取 Observable
            obs_match = re.search(
                r'(?:observable|观测量|可观测)[:\s：|]*(.+?)(?:\n|\||$)',
                section, re.IGNORECASE
            )
            # 提取 Tool
            tool_match = re.search(
                r'(?:tool|工具|方法)[:\s：|]*(.+?)(?:\n|\||$)',
                section, re.IGNORECASE
            )

            # 构建 topic 名称
            obj_str = obj_match.group(1).strip() if obj_match else ""
            obs_str = obs_match.group(1).strip() if obs_match else ""
            tool_str = tool_match.group(1).strip() if tool_match else ""

            if obj_str or obs_str or tool_str:
                topic = " | ".join(filter(None, [obj_str, obs_str, tool_str]))
            else:
                # fallback: 取标题行
                title_match = re.match(
                    r'(?:\d+[\.\)]\s*|#{1,3}\s*)(.+?)(?:\n|$)', section
                )
                topic = title_match.group(1).strip() if title_match else section[:100]

            if not topic:
                continue

            # 提取 description
            desc_match = re.search(
                r'(?:description|描述|research direction|方向)[:\s：]*(.+?)(?:\n|$)',
                section, re.IGNORECASE
            )
            description = desc_match.group(1).strip() if desc_match else ""
            if not description:
                lines = section.split('\n')
                for line in lines[1:]:
                    line = line.strip().lstrip('-*• ')
                    if line and len(line) > 20:
                        description = line
                        break
            if not description:
                description = section[:300]

            # 提取评分 (feasibility / novelty / venue fit → 映射到 0-1)
            def extract_score(pattern: str, text: str) -> float:
                m = re.search(pattern, text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip().lower()
                    # 数字评分
                    num_match = re.search(r'(\d+(?:\.\d+)?)', val)
                    if num_match:
                        score = float(num_match.group(1))
                        return score if score <= 1.0 else score / 10.0
                    # 文字评分
                    if any(w in val for w in ['high', '高', 'strong', 'excellent']):
                        return 0.85
                    if any(w in val for w in ['medium', '中', 'moderate', 'good']):
                        return 0.6
                    if any(w in val for w in ['low', '低', 'weak', 'poor']):
                        return 0.35
                return 0.5

            feasibility = extract_score(r'(?:feasibility|可行性)[:\s：]*(.+?)(?:\n|$)', section)
            novelty = extract_score(r'(?:novelty|新颖性|新颖)[:\s：]*(.+?)(?:\n|$)', section)
            impact = extract_score(r'(?:venue fit|impact|影响力|venue)[:\s：]*(.+?)(?:\n|$)', section)

            # 提取 risks
            risks = []
            risk_match = re.search(
                r'(?:risk|风险)[s:\s：]*(.+?)(?=\n(?:\d+[\.\)]|#{1,3})|$)',
                section, re.IGNORECASE | re.DOTALL
            )
            if risk_match:
                risk_text = risk_match.group(1)
                risk_items = re.findall(r'[-•*]\s*(.+?)(?:\n|$)', risk_text)
                risks = [r.strip() for r in risk_items if r.strip()][:5]

            # rationale: 用 description 或 section 摘要
            rationale = description if description != section[:300] else section[:200]

            candidates.append(OOTCandidate(
                topic=topic[:200],
                description=description[:500],
                novelty_score=novelty,
                feasibility_score=feasibility,
                impact_score=impact,
                rationale=rationale[:300],
                risks=risks
            ))

        # fallback
        if not candidates:
            logger.warning("OOT parsing extracted 0 candidates, using raw response as fallback")
            candidates.append(OOTCandidate(
                topic="AI Analysis Result",
                description=response[:500],
                novelty_score=0.5,
                feasibility_score=0.5,
                impact_score=0.5,
                rationale="See raw response for full analysis",
                risks=[]
            ))

        return candidates

    def _parse_resources(self, response: str) -> List[ResourceItem]:
        """
        解析资源列表 — 从 AI 响应中提取资源条目

        v7 prompt 要求格式: 按类别分组 (Data Access, Compute, Expertise, Code, Constraints, Gaps)
        每项含 resource type, name, availability, relevance
        """
        resources = []
        if not response or not response.strip():
            return resources

        # 类别关键词 → resource_type 映射
        category_map = {
            'data': 'dataset', 'dataset': 'dataset', '数据': 'dataset',
            'compute': 'tool', 'equipment': 'tool', 'gpu': 'tool', 'cpu': 'tool',
            '计算': 'tool', '设备': 'tool',
            'expertise': 'expert', 'domain expertise': 'expert', '专业': 'expert',
            'code': 'tool', 'library': 'tool', 'libraries': 'tool', '代码': 'tool',
            'constraint': 'other', 'budget': 'other', 'deadline': 'other', '约束': 'other',
            'gap': 'other', 'missing': 'other', '缺口': 'other',
        }

        # 按大标题拆分 (## / ### / 数字标题)
        category_sections = re.split(
            r'\n(?=(?:#{1,3}\s+\d*\.?\s*\*?\*?(?:Data|Compute|Domain|Reusable|Hard|Explicit|Gap|Resource)))',
            response, flags=re.IGNORECASE
        )

        current_type = "other"

        for cat_section in category_sections:
            cat_section = cat_section.strip()
            if not cat_section:
                continue

            # 检测当前类别
            header_match = re.match(r'#{1,3}\s*\d*\.?\s*\*?\*?(.+?)(?:\*\*)?(?:\n|$)', cat_section)
            if header_match:
                header_text = header_match.group(1).strip().lower()
                for keyword, rtype in category_map.items():
                    if keyword in header_text:
                        current_type = rtype
                        break

            # 提取列表项 (- / * / • / 数字)
            items = re.findall(
                r'(?:^|\n)\s*[-•*]\s+\*?\*?(.+?)(?:\*\*)?(?:\n|$)',
                cat_section
            )
            if not items:
                # 尝试子标题格式
                items = re.findall(
                    r'(?:^|\n)\s*(?:#{3,4}|####)\s+(.+?)(?:\n|$)',
                    cat_section
                )

            for item_text in items:
                item_text = item_text.strip()
                if not item_text or len(item_text) < 5:
                    continue

                # 提取名称和描述
                # 格式可能是 "Name: description" 或 "Name (status)" 或 "Name — description"
                name_desc_match = re.match(
                    r'(.+?)(?:\s*[:\-—–]\s*(.+))?$', item_text
                )
                if name_desc_match:
                    name = name_desc_match.group(1).strip().rstrip(':')
                    desc = name_desc_match.group(2) or ""
                    desc = desc.strip()
                else:
                    name = item_text[:80]
                    desc = item_text

                # 提取 availability
                availability = "public"
                avail_match = re.search(
                    r'\b(have|available|can.?get|need.?collect|missing|partial|unavailable)\b',
                    item_text, re.IGNORECASE
                )
                if avail_match:
                    val = avail_match.group(1).lower().replace('-', '').replace(' ', '')
                    if val in ('have', 'available'):
                        availability = "public"
                    elif val in ('canget', 'partial'):
                        availability = "restricted"
                    else:
                        availability = "private"

                # 提取 relevance
                rel_match = re.search(r'\b(high|medium|low)\b', item_text, re.IGNORECASE)
                relevance = 0.7
                if rel_match:
                    mapping = {"high": 0.9, "medium": 0.6, "low": 0.3}
                    relevance = mapping.get(rel_match.group(1).lower(), 0.7)

                resources.append(ResourceItem(
                    resource_type=current_type,
                    name=name[:100],
                    description=desc[:300] if desc else item_text[:300],
                    url=None,
                    availability=availability,
                    relevance_score=relevance
                ))

        # fallback
        if not resources:
            logger.warning("Resource Card parsing extracted 0 items, using raw response as fallback")
            resources.append(ResourceItem(
                resource_type="other",
                name="AI Analysis Result",
                description=response[:500],
                url=None,
                availability="public",
                relevance_score=0.7
            ))

        return resources

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

"""
Step 0 Prompt 模板
项目启动阶段的 Prompt 模板
"""

# Step 0.1: Project Intake Card (ChatGPT with Thinking Mode)
STEP_0_1_PROMPT = """You are an experienced research PI and paper architect. Your task is to create a comprehensive Project Intake Card for a new research project.

## Input Information:
- **Topic**: {topic}
- **Target Venue**: {target_venue}
- **Research Type**: {research_type}
- **Data Status**: {data_status}
- **Hard Constraints**: {hard_constraints}
- **Time Budget**: {time_budget}
- **Keywords**: {keywords}
- **Rigor Profile**: {rigor_profile} (v6.0 NEW - Research rigor level)

## Your Task:
Create a detailed Project Intake Card that includes:

1. **North-Star Question** (SOP v4.0 - CRITICAL for Gate 1.25)
   - ONE clear, specific question that this research aims to answer
   - Must be answerable with empirical evidence or rigorous analysis
   - Should guide all subsequent decisions (topic selection, claims, experiments)
   - Format: "Can we [specific action] to [measurable outcome] under [constraints]?"
   - Example: "Can we reduce inference latency by 50% while maintaining 95% accuracy on edge devices?"

2. **Project Overview**
   - Clear problem statement
   - Research motivation and significance
   - Target venue and why it's appropriate
   - How this work addresses the North-Star Question

3. **Definition of Done (DoD)** - At least 3 specific, measurable criteria:
   - What constitutes a successful paper submission?
   - What are the minimum requirements for acceptance?
   - What are the quality benchmarks?

4. **Hard Constraints** - At least 3 non-negotiable requirements:
   - Technical constraints (e.g., must use specific hardware/software)
   - Methodological constraints (e.g., must include experiments)
   - Resource constraints (e.g., time, budget, data availability)

5. **Research Scope** (SOP v4.0 - Use explicit IN/OUT format)

   **IN SCOPE (What we WILL do):**
   - [Specific item 1]
   - [Specific item 2]
   - [Specific item 3]
   - ...

   **OUT OF SCOPE (What we will NOT do):**
   - [Specific item 1]
   - [Specific item 2]
   - [Specific item 3]
   - ...

   **Boundary Conditions:**
   - Clear criteria for what's included vs excluded
   - Edge cases and how to handle them

6. **Deep Research Keywords** (SOP v4.0 - For Step 1.1)
   - **English Keywords** (5-10): [keyword1, keyword2, ...]
   - **Chinese Keywords** (5-10): [关键词1, 关键词2, ...]
   - Include both technical terms and domain-specific phrases

7. **Risk Analysis** (Top 10 + Mitigation)
   - List top 10 risks ranked by severity × probability
   - For each risk: brief description + mitigation strategy
   - Include technical, methodological, and resource risks

8. **Success Metrics**
   - How will we measure progress?
   - What are the key milestones?
   - What are the stop/pivot criteria?

9. **Rigor Profile** (v6.0 NEW)
   - **Selected Profile**: {rigor_profile}
   - **Profile Description**:
     - **top_journal**: Strict mode for top-tier venues. All gates must pass with high standards. Requires manual verification and red-team review.
     - **fast_track**: Flexible mode for rapid validation or conference submissions. Some gates can be skipped or have lower pass rates.
   - **Implications for this project**:
     - Gate pass requirements (e.g., Gate 0 requires 100% vs 67% pass rate)
     - Literature quality standards (e.g., 30 vs 15 minimum papers, 90% vs 70% DOI parseability)
     - Manual verification requirements
     - Red-team review requirements

## Output Format:
Provide your response in a structured markdown format with clear sections. Be specific and actionable.

**IMPORTANT - YAML Front-Matter (SOP v6.0):**
Your output MUST begin with YAML front-matter containing:

```yaml
---
doc_type: ProjectIntakeCard
version: 0.1
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
topic: "[One-line summary]"
north_star_question: "[The North-Star Question]"
rigor_profile: "{rigor_profile}"
inputs:
  - "User requirements"
outputs:
  - "00_Project_Intake_Card.md"
gate_relevance: "Gate0"
---
```

Then provide the main content with all 9 sections listed above.

Think carefully about the research landscape, venue requirements, and feasibility before responding.
"""

# Step 0.2: Venue Taste Primer (Gemini)
STEP_0_2_PROMPT = """You are an expert research intelligence officer specializing in academic venue analysis. Your task is to analyze the target venue and provide detailed taste notes.

**CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
1) 先列 Plan（最多 6 步），再执行检索/核验，再输出产物；不要先写结论。
2) 每个关键判断必须给 Evidence（DOI/出版社页面/IEEE Xplore/ArXiv 链接之一）。
3) 不允许占位符 DOI（如 10.1109/xxx.2024.1）；若找不到就标记 UNKNOWN 并降级结论。
4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。

## Input:
You have been provided with a Project Intake Card containing:
- Topic: {topic}
- Target Venue: {target_venue}
- Research context and constraints

## Your Task:
Conduct a comprehensive analysis of the target venue and create Venue Taste Notes that include:

1. **Venue Profile**
   - Venue type (journal/conference)
   - Impact factor / ranking
   - Acceptance rate
   - Review process characteristics
   - Typical paper length and structure

2. **Content Preferences**
   - What types of papers does this venue prefer?
   - What are the common themes in recent publications?
   - What methodologies are favored?
   - What level of novelty is expected?

3. **Writing Style**
   - Tone (formal/informal, technical/accessible)
   - Structure preferences
   - Figure/table expectations
   - Citation style and density

4. **Recent Trends** (analyze last 2-3 years)
   - Hot topics in this venue
   - Emerging research directions
   - Common rejection reasons
   - Success patterns

5. **Fit Analysis**
   - How well does our proposed topic fit this venue?
   - What aspects should we emphasize?
   - What aspects should we de-emphasize?
   - Potential concerns or red flags

6. **Strategic Recommendations**
   - How should we position our work?
   - What should be our key selling points?
   - What are the must-have elements?
   - What are the nice-to-have elements?

## Output Format (MANDATORY - SOP v4.0):

### 1. Plan (执行计划)
List 3-6 specific steps you will take to analyze this venue:
1. [Step 1]
2. [Step 2]
...

### 2. Actions Taken (检索动作)
Document your research actions:
- Search queries used
- Databases/sources consulted
- Papers/articles reviewed
- Key findings from each source

### 3. Evidence Table (证据表)
For each key claim about the venue, provide evidence:

| Claim | Evidence Type | Source | DOI/URL | Confidence |
|-------|--------------|--------|---------|------------|
| [Claim 1] | Paper/Trend | [Source] | [DOI or URL] | High/Med/Low |
| [Claim 2] | ... | ... | ... | ... |

**CRITICAL**: Use real DOIs or URLs. Mark as "UNKNOWN" if not found. NO placeholder DOIs like "10.1109/xxx.2024.1".

### 4. Deliverables (产物)
Provide the complete Venue Taste Notes with all 6 sections above (Venue Profile, Content Preferences, Writing Style, Recent Trends, Fit Analysis, Strategic Recommendations).

**DO NOT wrap the deliverables in markdown code blocks (```markdown```).**

### 5. Risks (风险列表)
List at least 5 risks or uncertainties:
1. [Risk 1]
2. [Risk 2]
3. [Risk 3]
4. [Risk 4]
5. [Risk 5]

### 6. Verification Checklist (核验清单)
List at least 5 items that should be manually verified:
1. [Verification item 1]
2. [Verification item 2]
3. [Verification item 3]
4. [Verification item 4]
5. [Verification item 5]

### 7. Confidence Score
Overall confidence in this analysis: [0.0-1.0]

Reasoning: [Brief explanation of confidence level]

---

Use your deep research capabilities to gather comprehensive, evidence-based information about this venue.
"""


def render_step_0_1_prompt(
    topic: str,
    target_venue: str,
    research_type: str,
    data_status: str,
    hard_constraints: list,
    time_budget: str,
    keywords: list,
    rigor_profile: str = "top_journal"
) -> str:
    """
    渲染 Step 0.1 Prompt 模板

    Args:
        topic: 研究主题
        target_venue: 目标期刊/会议
        research_type: 研究类型 (theory/simulation/system/experiment)
        data_status: 数据状态 (available/need-collection/none)
        hard_constraints: 硬约束列表
        time_budget: 时间预算
        keywords: 关键词列表
        rigor_profile: 研究强度档位 (top_journal/fast_track) - v6.0 NEW

    Returns:
        str: 渲染后的 Prompt
    """
    # 格式化硬约束
    constraints_str = "\n".join([f"   - {c}" for c in hard_constraints])

    # 格式化关键词
    keywords_str = ", ".join(keywords)

    return STEP_0_1_PROMPT.format(
        topic=topic,
        target_venue=target_venue,
        research_type=research_type,
        data_status=data_status,
        hard_constraints=constraints_str,
        time_budget=time_budget,
        keywords=keywords_str,
        rigor_profile=rigor_profile
    )


def render_step_0_2_prompt(topic: str, target_venue: str) -> str:
    """
    渲染 Step 0.2 Prompt 模板
    
    Args:
        topic: 研究主题
        target_venue: 目标期刊/会议
    
    Returns:
        str: 渲染后的 Prompt
    """
    return STEP_0_2_PROMPT.format(
        topic=topic,
        target_venue=target_venue
    )

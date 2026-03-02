"""
Step 1 Prompts
Step 1 阶段的所有提示词模板
"""


def render_step_1_1_prompt(topic: str, target_venue: str, research_type: str,
                           intake_card_content: str, venue_taste_content: str = "") -> str:
    """
    渲染 Step 1.1 Prompt: Broad Deep Research (Gemini)

    Args:
        topic: 研究主题
        target_venue: 目标期刊
        research_type: 研究类型
        intake_card_content: Project Intake Card 内容
        venue_taste_content: Venue Taste Notes 内容（可选）

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are my Chief Intelligence Officer + top-journal editor.

**CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
1) 先列 Plan（最多 6 步），再执行检索/核验，再输出产物；不要先写结论。
2) 每个关键判断必须给 Evidence（DOI/出版社页面/IEEE Xplore/ArXiv 链接之一）。
3) 不允许占位符 DOI（如 10.1109/xxx.2024.1）；若找不到就标记 UNKNOWN 并降级结论。
4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。

Deep research for topic: {topic} (Target venue: {target_venue}; Research type: {research_type})

## Context from Project Intake Card:
{intake_card_content}

"""

    if venue_taste_content:
        prompt += f"""## Context from Venue Taste Notes:
{venue_taste_content}

"""

    prompt += """Output (MUST be structured, no long essay):

## 0) Plan
List 3-6 steps you will take to complete this deep research:
- Step 1: [action]
- Step 2: [action]
- ...

## 1) Actions Taken
Document what you actually did:
- Searched: [keywords/databases]
- Reviewed: [number] papers
- Validated: [evidence sources]

## 2) Evidence Validation
For each key claim or finding, provide:
- Claim: [statement]
- Evidence: [DOI or URL - NO placeholders]
- Status: VERIFIED / UNKNOWN

## A) Literature Matrix
(>=30 papers preferred; prioritize last 5 years, but include classics if needed)

Create a table with columns:
- Venue/Year | Title | Core Problem | Method | Key Assumptions | Data/Setup | Main Results | Limitations (gap candidates) | Open Questions | Link/DOI

**IMPORTANT**: Every row MUST have a valid DOI or URL. If DOI is unavailable, mark as UNKNOWN and note in limitations.

## B) Landscape Map
Cluster the field into 4–6 clusters. For each cluster: 5–8 representative papers + 1-line narrative.

## C) Gap-to-Opportunity
List 10 candidate gaps. Each gap must explicitly point to specific papers/limitations in the matrix with DOI/URL evidence.

## D) Candidate Directions
Propose 3 candidate directions:
For each: 1-line contribution, minimal viable validation, biggest risk.

## E) Risk List
List >=5 risks identified during research:
- Risk 1: [description]
- Risk 2: [description]
- ...

## F) Verification Checklist
List >=5 items that need verification:
- [ ] Item 1: [what needs to be verified]
- [ ] Item 2: [what needs to be verified]
- ...

## G) Confidence Score
Overall confidence in this research: [0.0-1.0]
- Literature coverage: [0.0-1.0]
- Evidence quality: [0.0-1.0]
- Gap identification: [0.0-1.0]

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "00_Deep_Research_Summary"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "{target_venue}"
topic: "[One-line summary of the research topic]"
inputs:
  - "00_Project_Intake_Card.md"
  - "00_Venue_Taste_Notes.md"
outputs:
  - "00_Deep_Research_Summary.md"
gate_relevance: "Gate 1"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections 0-G).

Return as a comprehensive markdown document (00_Deep_Research_Summary.md).

**REMINDER**: Do NOT wrap the entire output in ```markdown``` code blocks. Output should be direct markdown content.
"""

    return prompt


def render_step_1_2_prompt(deep_research_content: str, target_venue: str, core_keywords: str = "") -> str:
    """
    渲染 Step 1.2 Prompt: Topic Decision & Draft Claim Set (ChatGPT)

    Args:
        deep_research_content: Deep Research Summary 内容
        target_venue: 目标期刊
        core_keywords: 核心关键词列表（可选）

    Returns:
        str: 渲染后的 prompt
    """
    # 如果提供了核心关键词，添加到 prompt 中
    keywords_instruction = ""
    if core_keywords:
        keywords_instruction = f"""

## CRITICAL: Core Keywords Requirement (Gate 1.25)

The selected topic MUST incorporate at least 3-5 of the following core keywords from the Project Intake Card:

{core_keywords}

**IMPORTANT**: The topic title should naturally include these keywords to ensure alignment with the project's North-Star Question and research scope. This is required to pass Gate 1.25 (Topic Alignment Check).
"""

    prompt = f"""You are the PI. I attach the Deep Research Summary (literature matrix + venue notes).

Target venue: {target_venue}
{keywords_instruction}

## Deep Research Summary:
{deep_research_content}

## Tasks:

1) Extract <=10 "Gap Statements" (each must cite specific paper(s) from the matrix).

2) Propose 3 candidate topics. Score each 1–5 on:
   - Novelty
   - Feasibility
   - Venue-fit
   - Interpretability
   - Risk

   **IMPORTANT**: Each candidate topic title should incorporate 3-5 core keywords from the list above.

3) Select Top-1 and Top-2 backup.

4) For Top-1: write a Draft Claim Set:
   - 6 claims (what we assert)
   - 6 non-claims (what we explicitly do NOT claim)

5) Provide a minimal figure/table set (<=4) that would prove the main story.

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "01_Selected_Topic"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "{target_venue}"
topic: "[One-line summary of the selected topic]"
inputs:
  - "00_Deep_Research_Summary.md"
outputs:
  - "01_Selected_Topic.md"
gate_relevance: "Gate 1"
---
```

After the YAML front-matter, provide the complete document content including:
- Gap statements
- Candidate topics with scores
- Selected topic (Top-1 and backup)
- Draft claims and non-claims
- Minimal figure/table set
"""

    return prompt


def render_step_1_3_prompt(selected_topic_content: str) -> str:
    """
    渲染 Step 1.3 Prompt: Killer Prior Check (Gemini) - MANDATORY
    Enhanced with Agentic Wrapper (v4.0)

    Args:
        selected_topic_content: Selected Topic 内容（包含 draft claims）

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""KILLER PRIOR CHECK (mandatory). You are a ruthless reviewer + research librarian.

**CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
1) 先列 Plan（最多 6 步），再执行检索/核验，再输出产物；不要先写结论。
2) 每个关键判断必须给 Evidence（DOI/出版社页面/IEEE Xplore/ArXiv 链接之一）。
3) 不允许占位符 DOI（如 10.1109/xxx.2024.1）；若找不到就标记 UNKNOWN 并降级结论。
4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。

## Given Selected Topic + Draft Claims:
{selected_topic_content}

## Goal:
Find the most similar prior work (>=15 items; include very recent papers, preprints, conference abstracts if relevant).

For each prior work:
- What overlaps with our claims (map to claim numbers)
- What is truly new in our approach (if any)
- How we must differentiate (claims, method, evaluation, narrative)

## Output (MUST be structured, no long essay):

## 0) Plan
List 3-6 steps you will take to complete this Killer Prior Check:
- Step 1: [action - e.g., extract core claims from selected topic]
- Step 2: [action - e.g., search for papers with similar claims]
- Step 3: [action - e.g., validate DOI/URLs for each prior work]
- Step 4: [action - e.g., map overlaps to claim numbers]
- Step 5: [action - e.g., assess differentiation strategy]
- Step 6: [action - e.g., determine PASS/FAIL verdict]

## 1) Actions Taken
Document what you actually did:
- Searched: [keywords/databases used for prior work search]
- Reviewed: [number] papers/preprints/abstracts
- Validated: [number] DOI/URLs verified
- Mapped: [number] overlaps to claim numbers

## 2) Evidence Table
For each prior work found (>=15 items), provide:

| Prior Work | Venue/Year | Overlap with Our Claims | DOI/URL | Status |
|------------|------------|-------------------------|---------|--------|
| [Title 1] | [Venue/Year] | Claims [1,2,3]: [brief description] | [DOI or URL] | VERIFIED / UNKNOWN |
| [Title 2] | [Venue/Year] | Claims [4]: [brief description] | [DOI or URL] | VERIFIED / UNKNOWN |
| ... | ... | ... | ... | ... |

**IMPORTANT**: Every row MUST have a valid DOI or URL. If DOI is unavailable, mark as UNKNOWN and note in recommendations.

## 3) Deliverables

### A) "Direct Collision" List
Works that already cover our main claim set (>=3 claims overlap):

For each work:
- **Title**: [title]
- **Venue/Year**: [venue/year]
- **DOI/URL**: [link - NO placeholders]
- **Claims Covered**: [list claim numbers, e.g., Claims 1, 2, 3]
- **Overlap Description**: [1-2 sentences on what they already claim]
- **Our Differentiation**: [what is still new in our approach, if any]

### B) "Partial Overlap" List
Works that cover some claims (1-2 claims overlap):

For each work:
- **Title**: [title]
- **Venue/Year**: [venue/year]
- **DOI/URL**: [link - NO placeholders]
- **Claims Covered**: [list claim numbers]
- **Overlap Description**: [1-2 sentences]
- **How We Differ**: [method/evaluation/narrative differences]

### C) Recommended Changes (<=5)
Based on the prior work analysis, recommend specific changes:
1. [Revise claim X to emphasize Y]
2. [Change narrative identity from A to B]
3. [Add or swap key figure(s) to show Z]
4. [Change baseline comparisons to include W]
5. [Adjust evaluation metrics to highlight V]

### D) Verdict: PASS / FAIL

**Definition:**
- **PASS** = no single prior work fully covers our claims + our differentiator is crisp and defensible.
- **FAIL** = a prior work already claims the same core contributions.

**Verdict**: [PASS / FAIL]

**Justification**: [2-3 sentences explaining the verdict based on evidence]

## 4) Risks
List >=5 risks identified during Killer Prior Check:
- Risk 1: [e.g., Recent preprint (arXiv:XXXX) may publish before us with similar claims]
- Risk 2: [e.g., Claim 3 has weak differentiation from [Paper Title]]
- Risk 3: [e.g., Missing DOI for 3 key prior works - need manual verification]
- Risk 4: [e.g., Venue X published similar work in last 6 months - may reject as incremental]
- Risk 5: [e.g., Our differentiation relies on dataset Y which may not be available]
- ...

## 5) Verification Checklist
List >=5 items that need verification before proceeding:
- [ ] Item 1: [e.g., Verify DOI for [Paper Title] - currently marked UNKNOWN]
- [ ] Item 2: [e.g., Check if [Recent Preprint] has been published since search]
- [ ] Item 3: [e.g., Confirm our dataset Y is accessible and usable]
- [ ] Item 4: [e.g., Validate that Claim 3 differentiation is defensible with reviewers]
- [ ] Item 5: [e.g., Search for very recent papers (last 3 months) in target venue]
- ...

## 6) Confidence Score
Overall confidence in this Killer Prior Check: [0.0-1.0]
- Prior work coverage: [0.0-1.0] (how thoroughly we searched)
- Evidence quality: [0.0-1.0] (% of DOI/URLs verified)
- Differentiation clarity: [0.0-1.0] (how crisp our differentiator is)
- Verdict confidence: [0.0-1.0] (confidence in PASS/FAIL decision)

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "01_Killer_Prior_Check"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "[Extract from selected topic]"
topic: "[One-line summary from selected topic]"
inputs:
  - "01_Selected_Topic.md"
outputs:
  - "01_Killer_Prior_Check.md"
gate_relevance: "Gate 1.5"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections 0-6).

Return as 01_Killer_Prior_Check.md (with citations/links).

**REMINDER**: Do NOT wrap the entire output in ```markdown``` code blocks. Output should be direct markdown content.
"""

    return prompt


def render_step_1_4_prompt(killer_prior_content: str, target_venue: str) -> str:
    """
    渲染 Step 1.4 Prompt: Claims Freeze (ChatGPT)

    Args:
        killer_prior_content: Killer Prior Check 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI. We have a Killer Prior Check result.

Target venue: {target_venue}

## Killer Prior Check Result:
{killer_prior_content}

## Tasks:

1) Update and FREEZE the claim set:
   - >=6 claims
   - >=6 non-claims

2) Define a Minimal Verification Set (<=6 units).
   For each unit:
   - inputs
   - outputs
   - PASS/FAIL criteria

3) Define Pivot Rules:
   If the key phenomenon is weak or absent, what is the closest alternative paper identity that still fits {target_venue}?

## YAML Front-Matter Requirements

You MUST output THREE separate markdown documents with clear delimiters. Each document MUST begin with its own YAML front-matter:

**For 01_Claims_and_NonClaims.md:**
```yaml
---
doc_type: "01_Claims_and_NonClaims"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "{target_venue}"
topic: "[One-line summary from killer prior check]"
inputs:
  - "01_Killer_Prior_Check.md"
outputs:
  - "01_Claims_and_NonClaims.md"
gate_relevance: "Gate 1"
---
```

**For 01_Minimal_Verification_Set.md:**
```yaml
---
doc_type: "01_Minimal_Verification_Set"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "{target_venue}"
topic: "[One-line summary from killer prior check]"
inputs:
  - "01_Killer_Prior_Check.md"
  - "01_Claims_and_NonClaims.md"
outputs:
  - "01_Minimal_Verification_Set.md"
gate_relevance: "Gate 1"
---
```

**For 01_Pivot_Rules.md:**
```yaml
---
doc_type: "01_Pivot_Rules"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "{target_venue}"
topic: "[One-line summary from killer prior check]"
inputs:
  - "01_Killer_Prior_Check.md"
  - "01_Claims_and_NonClaims.md"
outputs:
  - "01_Pivot_Rules.md"
gate_relevance: "Gate 1"
---
```

## IMPORTANT - Output Format:

You MUST output THREE separate markdown documents with clear delimiters:

---DOCUMENT_1: 01_Claims_and_NonClaims.md---
[Content for frozen claims and non-claims]
---END_DOCUMENT_1---

---DOCUMENT_2: 01_Minimal_Verification_Set.md---
[Content for minimal verification set with <=6 units, each with inputs/outputs/PASS-FAIL criteria]
---END_DOCUMENT_2---

---DOCUMENT_3: 01_Pivot_Rules.md---
[Content for pivot rules - what to do if key phenomenon is weak or absent]
---END_DOCUMENT_3---

Each document should be complete and standalone.
"""

    return prompt


def render_step_1_5_prompt(frozen_claims_content: str, target_venue: str) -> str:
    """
    渲染 Step 1.5 Prompt: Paper Identity & Figure-First Story (Gemini)
    Enhanced with Agentic Wrapper (v4.0)

    Args:
        frozen_claims_content: Frozen Claims 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the senior editor of {target_venue}.

**CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
1) 先列 Plan（最多 6 步），再执行分析/设计，再输出产物；不要先写结论。
2) 每个关键判断必须给 Evidence（引用 frozen claims 中的具体 claim 编号或 figure 编号）。
3) 不允许占位符或模糊引用；若找不到就标记 UNKNOWN 并降级结论。
4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。

## Given Frozen Claims + Minimal Figure List:
{frozen_claims_content}

## Goal:
Build a figure-first narrative that maps each figure to reviewer questions, and provide 3 title + abstract candidates for {target_venue}.

## Output (MUST be structured, no long essay):

## 0) Plan
List 3-6 steps you will take to complete this Figure-First Story:
- Step 1: [action - e.g., extract frozen claims and identify key assertions]
- Step 2: [action - e.g., map each claim to potential reviewer questions]
- Step 3: [action - e.g., design figure sequence to answer questions]
- Step 4: [action - e.g., draft caption style for {target_venue}]
- Step 5: [action - e.g., generate 3 title + abstract candidates]
- Step 6: [action - e.g., validate narrative coherence and venue fit]

## 1) Actions Taken
Document what you actually did:
- Analyzed: [number] frozen claims
- Mapped: [number] figures to reviewer questions
- Designed: [description of narrative structure]
- Generated: [number] title + abstract candidates
- Validated: [what was checked for venue fit]

## 2) Evidence Validation
For each key narrative decision, provide:
- Decision: [e.g., Figure 1 should show X]
- Evidence: [e.g., Supports Claim 1 and Claim 3 from frozen claims]
- Reviewer Question: [e.g., "Does the method work on real data?"]
- Status: VALIDATED / NEEDS_VERIFICATION

## 3) Deliverables

### A) Figure-First Narrative

For each figure in the minimal figure list:

**Figure [N]: [Title/Description]**
- **Reviewer Question**: [What question does this figure answer?]
- **Claims Supported**: [List claim numbers from frozen claims, e.g., Claims 1, 3, 5]
- **Key Message**: [1-2 sentences on what this figure proves]
- **Caption Style for {target_venue}**: [Brief guidance on caption length, tone, and emphasis]
- **What to Emphasize**: [Specific elements to highlight - e.g., error bars, baselines, statistical significance]
- **Potential Reviewer Concerns**: [What might reviewers question about this figure?]

**Narrative Flow**:
[2-3 sentences describing how the figures connect to tell a coherent story from introduction to conclusion]

### B) Title + Abstract Candidates

**Candidate 1:**
- **Title**: [Concise title, no hype]
- **Abstract**: [150-200 words, structured as: Problem → Gap → Our Contribution → Key Results → Implications. NO invented results, only what frozen claims promise.]
- **Venue Fit Score**: [0.0-1.0] - [Brief justification for {target_venue}]

**Candidate 2:**
- **Title**: [Alternative angle, no hype]
- **Abstract**: [150-200 words, different emphasis than Candidate 1]
- **Venue Fit Score**: [0.0-1.0] - [Brief justification for {target_venue}]

**Candidate 3:**
- **Title**: [Third option, no hype]
- **Abstract**: [150-200 words, different emphasis than Candidates 1 & 2]
- **Venue Fit Score**: [0.0-1.0] - [Brief justification for {target_venue}]

**Recommendation**: [Which candidate is strongest for {target_venue} and why?]

## 4) Risks
List >=5 risks identified during Figure-First Story design:
- Risk 1: [e.g., Figure 2 may not be sufficient to prove Claim 4 - needs additional baseline]
- Risk 2: [e.g., Abstract Candidate 1 may be too technical for {target_venue} audience]
- Risk 3: [e.g., Narrative flow assumes Figure 3 results will be strong - may need pivot if weak]
- Risk 4: [e.g., Caption style for {target_venue} requires extensive statistical details - may exceed space limits]
- Risk 5: [e.g., Reviewer Question for Figure 1 may be too broad - needs refinement]
- ...

## 5) Verification Checklist
List >=5 items that need verification before proceeding:
- [ ] Item 1: [e.g., Confirm Figure 1 design can actually answer the stated reviewer question]
- [ ] Item 2: [e.g., Validate that all frozen claims are covered by at least one figure]
- [ ] Item 3: [e.g., Check that abstract candidates match {target_venue} word limits]
- [ ] Item 4: [e.g., Verify caption style examples from recent {target_venue} papers]
- [ ] Item 5: [e.g., Ensure no hype or invented results in title + abstract candidates]
- ...

## 6) Confidence Score
Overall confidence in this Figure-First Story: [0.0-1.0]
- Figure-to-question mapping: [0.0-1.0] (how well figures answer reviewer questions)
- Narrative coherence: [0.0-1.0] (how well figures connect to tell a story)
- Venue fit: [0.0-1.0] (how well title + abstracts match {target_venue} style)
- Claims coverage: [0.0-1.0] (% of frozen claims covered by figures)

## YAML Front-Matter Requirements

You MUST output TWO separate markdown documents with clear delimiters. Each document MUST begin with its own YAML front-matter:

**For 01_Figure_First_Story.md:**
```yaml
---
doc_type: "01_Figure_First_Story"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "{target_venue}"
topic: "[One-line summary from frozen claims]"
inputs:
  - "01_Claims_and_NonClaims.md"
  - "01_Minimal_Verification_Set.md"
outputs:
  - "01_Figure_First_Story.md"
gate_relevance: "Gate 1"
---
```

**For 01_Title_Abstract_Candidates.md:**
```yaml
---
doc_type: "01_Title_Abstract_Candidates"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "{target_venue}"
topic: "[One-line summary from frozen claims]"
inputs:
  - "01_Claims_and_NonClaims.md"
  - "01_Figure_First_Story.md"
outputs:
  - "01_Title_Abstract_Candidates.md"
gate_relevance: "Gate 1"
---
```

## IMPORTANT - Output Format:

You MUST output TWO separate markdown documents with clear delimiters.

**CRITICAL FORMAT REQUIREMENTS:**
1. Start with the delimiter line: ---DOCUMENT_1: 01_Figure_First_Story.md---
2. Do NOT use code blocks (```) anywhere in your response
3. Do NOT wrap YAML front-matter in code blocks
4. Output raw markdown text only

**EXACT FORMAT (follow this precisely):**

---DOCUMENT_1: 01_Figure_First_Story.md---
---
doc_type: "01_Figure_First_Story"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "{target_venue}"
topic: "[topic from frozen claims]"
inputs:
  - "01_Claims_and_NonClaims.md"
  - "01_Minimal_Verification_Set.md"
outputs:
  - "01_Figure_First_Story.md"
gate_relevance: "Gate 1"
---

## 0) Plan
[Your plan here]

## 1) Actions Taken
[Your actions here]

[... rest of sections 2-6 ...]

---END_DOCUMENT_1---

---DOCUMENT_2: 01_Title_Abstract_Candidates.md---
---
doc_type: "01_Title_Abstract_Candidates"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "{target_venue}"
topic: "[topic from frozen claims]"
inputs:
  - "01_Claims_and_NonClaims.md"
  - "01_Figure_First_Story.md"
outputs:
  - "01_Title_Abstract_Candidates.md"
gate_relevance: "Gate 1"
---

### B) Title + Abstract Candidates

[Your candidates here]

---END_DOCUMENT_2---

**REMINDER**:
- NO code blocks (```) anywhere
- NO wrapping in ```yaml or ```markdown
- Start directly with: ---DOCUMENT_1: 01_Figure_First_Story.md---
- Output raw markdown text only
"""

    return prompt


def render_step_1_1b_prompt(literature_matrix_content: str) -> str:
    """
    渲染 Step 1.1b Prompt: Reference QA (Gemini) - v4.0 NEW

    Args:
        literature_matrix_content: Literature Matrix 内容（来自 Deep Research Summary）

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are a meticulous research librarian and citation validator.

## Given Literature Matrix:
{literature_matrix_content}

## Tasks:

1) **Extract and Validate References**
   - Extract all references from the literature matrix
   - For each reference, extract:
     * Title
     * Authors (if available)
     * Venue/Year
     * DOI or URL
   - Create a structured table with these fields

2) **Quality Checks**
   - Identify references missing DOI/URL
   - Flag potential duplicates (similar titles)
   - Check for incomplete citations

3) **Generate Verified References**
   - Create a clean bibliography in BibTeX format
   - Include only references with valid DOI or verifiable URL
   - Use consistent citation keys (e.g., author_year_keyword)

## Output Format:

### A) Literature Matrix (Enhanced)
[Reproduce the literature matrix with DOI column highlighted]

### B) Reference Quality Report
- Total references: [count]
- References with DOI: [count] ([percentage]%)
- References with URL only: [count]
- Missing DOI/URL: [count]
- Potential duplicates: [list]

### C) Verified References (BibTeX)
```bibtex
[Clean BibTeX entries for all references with valid DOI/URL]
```

### D) Action Items
[List of references that need DOI/URL added or need to be replaced]

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "00_Reference_QA_Report"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "[Extract from project context]"
topic: "[One-line summary from deep research]"
inputs:
  - "00_Deep_Research_Summary.md"
  - "00_Literature_Matrix.md"
outputs:
  - "00_Reference_QA_Report.md"
  - "00_Verified_References.bib"
gate_relevance: "Gate 1.6"
evidence_quality: "[0.0-1.0 based on DOI validation rate]"
doi_validation_passed: "[true/false based on quality threshold]"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections A-D).

Return as 00_Reference_QA_Report.md with embedded BibTeX section.
"""

    return prompt


def render_step_1_2b_prompt(selected_topic_content: str, intake_card_content: str,
                            keywords: list) -> str:
    """
    渲染 Step 1.2b Prompt: Topic Alignment Check (ChatGPT) - v4.0 NEW

    Args:
        selected_topic_content: Selected Topic 内容
        intake_card_content: Project Intake Card 内容
        keywords: 关键词列表

    Returns:
        str: 渲染后的 prompt
    """
    keywords_str = ", ".join(keywords)

    prompt = f"""You are the PI performing a Topic Alignment Check (Gate 1.25).

## Given Project Intake Card:
{intake_card_content}

## Given Selected Topic:
{selected_topic_content}

## Original Keywords:
{keywords_str}

## Tasks:

1) **North-Star Question Coverage**
   - Extract the "North-Star Question" from the Intake Card
   - Verify that the selected topic directly addresses this question
   - Score: PASS / FAIL

2) **Keyword Alignment**
   - Check how many of the original keywords (3-5 core terms) appear in the selected topic
   - **IMPORTANT**: A keyword is considered "present" if:
     * The exact keyword appears in the topic (e.g., "Compressed Sensing")
     * A substantial part of the keyword appears (e.g., "Physics-Driven" matches "Physics-Driven Algorithm")
     * A singular/plural variant appears (e.g., "Characteristic Mode" matches "Characteristic Modes")
   - **Count rule**: Count each keyword as present if ANY substantial part appears in the topic
   - Calculate keyword match score = (keywords present) / (total keywords)
   - Identify missing keywords and assess if they should be incorporated
   - **Example**: Topic "Physics-Driven Compressed Sensing Using Characteristic Mode Incoherence" contains:
     * "Physics-Driven" → matches "Physics-Driven Algorithm" (partial match)
     * "Compressed Sensing" → exact match
     * "Characteristic Mode" → matches "Characteristic Modes" (singular/plural)
     * "Incoherence" → exact match
     * Total: 4 keywords present

3) **Scope Boundary Check**
   - Verify that the Non-Claims section explicitly defines what is OUT of scope
   - Check that scope boundaries align with the original constraints from Intake Card
   - Score: CLEAR / UNCLEAR

4) **Alignment Score**
   - Overall alignment score (0-1) based on:
     * North-Star coverage (40%)
     * Keyword match (30%)
     * Scope clarity (30%)

## Output Format:

### 1) North-Star Question Analysis
- Original North-Star Question: [extract from Intake]
- Coverage in Selected Topic: [YES/NO with explanation]
- Verdict: PASS / FAIL

### 2) Keyword Alignment Analysis
- Core keywords present: [list with count]
- Core keywords missing: [list]
- Keyword match score: [0.0-1.0]
- Verdict: PASS (>=0.7) / FAIL (<0.7)

### 3) Scope Boundary Analysis
- Scope boundaries in Non-Claims: [extract]
- Alignment with Intake constraints: [analysis]
- Verdict: CLEAR / UNCLEAR

### 4) Overall Alignment
- Alignment score: [0.0-1.0]
- Gate 1.25 Verdict: PASS / FAIL
- Recommendations: [if FAIL, what needs to be adjusted]

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "01_Topic_Alignment_Check"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "[Extract from intake card]"
topic: "[One-line summary from selected topic]"
inputs:
  - "00_Project_Intake_Card.md"
  - "01_Selected_Topic.md"
outputs:
  - "01_Topic_Alignment_Check.md"
gate_relevance: "Gate 1.25"
north_star_question: "[Extract from intake card]"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections 1-4).

Return as 01_Topic_Alignment_Check.md.
"""

    return prompt

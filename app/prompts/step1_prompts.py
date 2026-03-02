"""
Step 1 Prompts
Step 1 阶段的所有提示词模板
"""


# v7 SOP 6.3 [S1a] — Search Plan (ChatGPT)
def render_step_1_1a_prompt(topic: str, target_venue: str, research_type: str,
                            intake_card_content: str, venue_taste_content: str = "") -> str:
    """
    渲染 Step 1.1a Prompt: Search Plan (ChatGPT)
    v7 SOP 6.3 — Research Strategist role

    Args:
        topic: 研究主题
        target_venue: 目标期刊
        research_type: 研究类型
        intake_card_content: Project Intake Card 内容
        venue_taste_content: Venue Taste Notes 内容（可选）

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are a Research Strategist(The Planner).

## Task
Create a structured search plan for deep literature research on the topic below.

## Input
- Topic: {topic}
- Target Venue: {target_venue}
- Research Type: {research_type}
- Project Intake Card is attached below for full context.

## Context from Project Intake Card:
{intake_card_content}

"""

    if venue_taste_content:
        prompt += f"""## Context from Venue Taste Notes:
{venue_taste_content}

"""

    prompt += f"""## Actions

### 1. Decompose the Topic into 3 Dimensions
- **Method Gaps**: what techniques are missing or underexplored?
- **Application Constraints**: what practical limitations exist?
- **SOTA Baselines**: what are the current best approaches?

### 2. Generate Search Questions
For each dimension, generate 3 specific "Search Questions" (answerable by finding papers).

### 3. Generate Keyword Combinations
For each dimension, generate 5 "Keyword Combinations" (for Google Scholar / IEEE Xplore / arXiv).

### 4. Negative Keywords
Identify "Negative Keywords" to exclude (Survey, Review, Tutorial — unless explicitly needed).

### 5. Define coverage criteria
Define coverage criteria: what would a "sufficient" search look like? (min papers per dimension)

## Output Format
File: `01_A_Search_Plan.md`

Begin with YAML front-matter:
```yaml
---
doc_type: SearchPlan
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
topic: "[One-line summary]"
inputs: ["artifacts/00_intake/00_Project_Intake_Card.md"]
gate_relevance: Gate1
---
```

Then provide all sections above as structured markdown.
"""

    return prompt


# v7 SOP 6.4 [S1b] — The Hunt (Gemini)
def render_step_1_1b_hunt_prompt(search_plan_content: str, topic: str, target_venue: str, rigor_profile: str = "top_journal") -> str:
    """
    渲染 Step 1.1b Prompt: The Hunt (Gemini)
    v7 SOP 6.4 — Intelligence Officer / The Hunter role

    Args:
        search_plan_content: Search Plan 内容
        topic: 研究主题
        target_venue: 目标期刊
        rigor_profile: 研究强度档位 (top_journal / fast_track)

    Returns:
        str: 渲染后的 prompt
    """
    MIN_PAPERS = 30 if rigor_profile == "top_journal" else 15

    prompt = f"""You are an Intelligence Officer (The Hunter).

## Task
Execute the search plan below. Find and catalog relevant papers systematically.Execute Search & Extract Evidence according to the Search Plan.

## Input
- Topic: {topic}
- Target Venue: {target_venue}
- Search Plan is attached below.

## Search Plan:
{search_plan_content}

## CONSTRAINT:
- Focus on papers from last 5 years; prioritize last 3 years.
- DO NOT SUMMARIZE or write narrative. Extract structured data only.
- Each paper must have: DOI or arXiv link or publisher page URL. If none found, mark [UNVERIFIED].

## Actions

For EACH search query from the search plan:
1) Locate top 3-5 papers per query.
2) Extract per paper: 
   - [Title] | [Year] | [Venue]
   - [Claimed Solution / Core Method]
   - [Admitted Limitation / Gap]
   - [DOI or Link]
3) After all queries: list any unexpected findings or emerging trends.

## Format
structured table, one row per paper. Minimum {MIN_PAPERS} papers total.
(Top-Journal: MIN_PAPERS=30, Fast-Track: MIN_PAPERS=15)

## Output
File: `01_B_Raw_Intel_Log.md`

Begin with YAML front-matter:
```yaml
---
doc_type: RawIntelLog
version: "0.1"
status: draft
created_by: Gemini
target_venue: "{target_venue}"
topic: "[One-line summary]"
gate_relevance: Gate1
---
```

Then provide a structured table of all papers found, organized by search query.
Be evidence-first — every paper needs a DOI or link.

IMPORTANT: You MUST include at least {MIN_PAPERS} papers AND end with a section listing unexpected findings or emerging trends. Do not stop early.
"""

    return prompt


# v7 SOP 6.5 [S1c] — Literature Synthesis (ChatGPT)
def render_step_1_1c_prompt(raw_intel_content: str, topic: str, target_venue: str, rigor_profile: str = "top_journal") -> str:
    """
    渲染 Step 1.1c Prompt: Literature Synthesis (ChatGPT)
    v7 SOP 6.5 — PI role

    Args:
        raw_intel_content: Raw Intel Log 内容
        topic: 研究主题
        target_venue: 目标期刊
        rigor_profile: 研究强度档位 (top_journal / fast_track)

    Returns:
        str: 渲染后的 prompt
    """
    # Count papers in Raw Intel Log to set explicit expectation
    import re
    raw_lines = raw_intel_content.split('\n')
    paper_count = 0
    for line in raw_lines:
        s = line.strip()
        if s.startswith('|') and '---' not in s and 'Title' not in s.split('|')[1] if len(s.split('|')) > 1 else True:
            paper_count += 1
    if paper_count == 0:
        paper_count = len(re.findall(r'^\|', raw_intel_content, re.MULTILINE)) - 2  # subtract header + separator

    prompt = f"""You are the PI.

## Task
Synthesize the raw intelligence into a structured literature matrix and identify research opportunities.

## Input
- Topic: {topic}
- Target Venue: {target_venue}
- Raw Intel Log ({paper_count} papers) is attached below.

## Raw Intel Log:
{raw_intel_content}

## Actions

### 1. Filter
List papers to EXCLUDE (only clearly off-topic or pure review/survey papers). State exclusion reason for each.
Be conservative — when in doubt, keep the paper.

### 2. Literature Matrix
Build a numbered table with these columns for EVERY paper that was NOT excluded in Step 1:

| # | Venue/Year | Title | Core Problem | Method | Limitations (gap candidates) | DOI/Link |
|---|------------|-------|--------------|--------|------------------------------|----------|
| 1 | [Venue, Year] | [Title] | [Core problem] | [Method] | [Limitations] | [DOI] |

Keep each cell concise (1-2 sentences max). You MUST produce one row per included paper. Number rows sequentially starting from 1.
The Raw Intel Log contains {paper_count} papers. After excluding a few, you should have approximately {paper_count - 5} to {paper_count} rows.

### 3. Schools of Thought
Cluster remaining papers into 4-6 "Schools of Thought". For each cluster: representative papers + 1-line narrative.

### 4. Empty Spaces
Identify "Empty Spaces" — gaps no one has solved. Each gap must point to specific paper limitations.

### 5. Candidate Directions
Propose 3 candidate research directions. For each:
- 1-line contribution statement
- Minimal viable validation approach
- Biggest risk

## Output Format
File: `01_C_Literature_Matrix.md`

Begin with YAML front-matter:
```yaml
---
doc_type: LiteratureMatrix
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
topic: "[One-line summary]"
inputs: ["artifacts/01_research/01_B_Raw_Intel_Log.md"]
gate_relevance: Gate1
---
```

Then provide all sections above as structured markdown. Be evidence-first — every claim needs a DOI or link.

CRITICAL: Do NOT stop early. You must process ALL {paper_count} papers from the Raw Intel Log. The Literature Matrix table must have approximately {paper_count - 5}+ rows.
"""

    return prompt


# ============================================================
# LEGACY: Step 1.1 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_1_1_prompt_v4_legacy(topic, target_venue, research_type,
#                            intake_card_content, venue_taste_content=""):
#     prompt = f"""You are my Chief Intelligence Officer + top-journal editor.
#
#     **CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
#     1) 先列 Plan（最多 6 步），再执行检索/核验，再输出产物；不要先写结论。
#     2) 每个关键判断必须给 Evidence（DOI/出版社页面/IEEE Xplore/ArXiv 链接之一）。
#     3) 不允许占位符 DOI（如 10.1109/xxx.2024.1）；若找不到就标记 UNKNOWN 并降级结论。
#     4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
#     5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。
#
#     Deep research for topic: {topic} (Target venue: {target_venue}; Research type: {research_type})
#
#     ## Context from Project Intake Card:
#     {intake_card_content}
#
#     Output (MUST be structured, no long essay):
#     ## 0) Plan ... ## 1) Actions Taken ... ## 2) Evidence Validation ...
#     ## A) Literature Matrix ... ## B) Landscape Map ... ## C) Gap-to-Opportunity ...
#     ## D) Candidate Directions ... ## E) Risk List ... ## F) Verification Checklist ...
#     ## G) Confidence Score ...
#     """
#     return prompt


# v7 SOP 6.6 [S2] Topic Decision + Draft Claims — ChatGPT
def render_step_1_2_prompt(literature_matrix_content: str, target_venue: str,
                           core_keywords: str = "", venue_taste_content: str = "") -> str:
    """
    渲染 Step 1.2 Prompt: Topic Decision & Draft Claim Set (ChatGPT)
    v7 SOP 6.6 — PI role, 6 specific actions

    Args:
        literature_matrix_content: Literature Matrix v7 内容
        target_venue: 目标期刊
        core_keywords: 核心关键词列表（可选）
        venue_taste_content: Venue Taste Notes 内容（可选）

    Returns:
        str: 渲染后的 prompt
    """
    keywords_section = ""
    if core_keywords:
        keywords_section = f"""

## Core Keywords (from Intake Card):
{core_keywords}

The selected topic MUST incorporate at least 3-5 of these core keywords.
"""

    venue_taste_section = ""
    if venue_taste_content:
        venue_taste_section = f"""

## Venue Taste Notes:
{venue_taste_content}
"""

    prompt = f"""You are the PI.

## Task
Turn intelligence into a decision — narrow to Top-1 topic with backup.

## Input
- Literature Matrix is attached below.
- Target Venue: {target_venue}
{keywords_section}
## Literature Matrix:
{literature_matrix_content}
{venue_taste_section}
## Actions (complete all six)

### 1. Gap Statements
Extract <=10 "Gap Statements" (each must cite specific paper(s) from the matrix by their row number or DOI).

### 2. Candidate Topics
Propose 3 candidate topics. Score each 1-5 on: Novelty, Feasibility, Venue-fit, Interpretability, Risk.

### 3. Selection
Select Top-1 and Top-2 backup. Justify selection.

### 4. Draft Claim Set
For Top-1, write a Draft Claim Set:
- >=6 claims (what we assert)
- >=6 non-claims (what we explicitly do NOT claim)

### 5. Minimal Figure/Table Set
Provide a minimal figure/table set (<=4). For each figure:
- What it proves
- Which reviewer attack it defends against

### 6. Topic Alignment Check (自检)
- Does Top-1 directly answer the North-Star Question from Intake?
- Does it contain all 3-5 core keywords from Intake?
- Is everything outside scope written into non-claims?

## Output Format
Files: `01_Selected_Topic.md`, `01_Draft_Claims.md`

Begin with YAML front-matter:
```yaml
---
doc_type: SelectedTopic
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
topic: "[One-line summary]"
gate_relevance: Gate1
---
```

Then provide all 6 sections above.
"""

    return prompt


# ============================================================
# LEGACY: Step 1.2 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_1_2_prompt_v4_legacy(literature_matrix_content, target_venue,
#                            core_keywords="", venue_taste_content=""):
#     keywords_instruction = ""
#     if core_keywords:
#         keywords_instruction = f"""
#     ## CRITICAL: Core Keywords Requirement (Gate 1.25)
#     The selected topic MUST incorporate at least 3-5 of the following core keywords:
#     {core_keywords}
#     """
#     prompt = f"""You are the PI. I attach the Literature Matrix and venue notes.
#     Target venue: {target_venue}
#     {keywords_instruction}
#     ## Literature Matrix: {literature_matrix_content}
#     ## Tasks:
#     1) Extract <=10 "Gap Statements" ...
#     2) Propose 3 candidate topics. Score each 1-5 ...
#     3) Select Top-1 and Top-2 backup ...
#     4) For Top-1: write a Draft Claim Set (6 claims + 6 non-claims) ...
#     5) Provide a minimal figure/table set (<=4) ...
#     6) TOPIC ALIGNMENT CHECK ...
#     """
#     return prompt


# v7 SOP 6.7 [S3] Killer Prior Check — Gemini (MANDATORY)
# Agentic Wrapper is handled by wrapper_mode parameter, NOT inlined in prompt.
def render_step_1_3_prompt(selected_topic_content: str, draft_claims_content: str, rigor_profile: str = "top_journal") -> str:
    """
    渲染 Step 1.3 Prompt: Killer Prior Check (Gemini) - MANDATORY
    v7 SOP 6.7 — Ruthless Reviewer + Research Librarian role

    Args:
        selected_topic_content: Selected Topic 内容
        draft_claims_content: Draft Claims 内容（v7 必须输入）
        rigor_profile: 研究强度档位 (top_journal / fast_track)

    Returns:
        str: 渲染后的 prompt
    """
    MIN_SIMILAR = 15 if rigor_profile == "top_journal" else 10
    recency = "last 12-18 months" if rigor_profile == "top_journal" else "last 6-12 months"

    prompt = f"""You are a Ruthless Reviewer + Research Librarian.

## Task
KILL THIS PROJECT if a direct prior exists. This is a mandatory gate.

## Input
- Selected Topic is attached below.
- Draft Claims are attached below.

## Selected Topic:
{selected_topic_content}

## Draft Claims:
{draft_claims_content}

## Goal
Find the most similar prior work. Minimum {MIN_SIMILAR} items.
Include: published papers, preprints (arXiv), conference abstracts, recent workshop papers.
Prioritize {recency}.

## Actions
For each prior work found:
- What overlaps with our claims (map to claim numbers: C1, C2, ...)
- What is truly new in our approach (if any)
- How we must differentiate (claims, method, evaluation, narrative)

## Output Sections

### 1. "Direct Collision" List
Works that already cover >=80% of our claim set. For each:
- Title, Venue/Year, DOI
- Overlapping Claims
- Our Differentiator

### 2. "Partial Overlap" List
Works that cover some claims. Same format as above.

### 3. Collision Map
Markdown table with ALL prior works mapped to claims. Use this exact format:

| # | Prior Work | DOI | Overlapping Claims | Our Differentiator |
|---|------------|-----|--------------------|--------------------|
| 1 | [Title, Venue/Year] | [DOI or link] | [C1, C2, ...] | [How we differ] |

Every paper from sections 1 and 2 must appear in this table. Number rows sequentially starting from 1.

### 4. Recommended Changes (<=5)
- Revise which claims / change narrative identity / add or swap key figure / change baseline

### 5. VERDICT: PASS or FAIL
- PASS = no single prior work fully covers our claims + our differentiator is crisp and defensible.
- FAIL = a prior work already claims the same core contributions.

## Output Format
File: `01_Killer_Prior_Check.md`

Begin with YAML front-matter:
```yaml
---
doc_type: KillerPriorCheck
version: "0.1"
status: draft
created_by: Gemini
target_venue: "[from selected topic]"
topic: "[One-line summary]"
gate_relevance: Gate1.5
---
```

Then provide all 5 sections above. Every prior work MUST have a DOI or link — no placeholders.
"""

    return prompt


# ============================================================
# LEGACY: Step 1.3 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_1_3_prompt_v4_legacy(selected_topic_content, draft_claims_content):
#     prompt = f"""KILLER PRIOR CHECK (mandatory). You are a ruthless reviewer + research librarian.
#     **CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
#     1) 先列 Plan ... 2) Evidence ... 3) 不允许占位符 DOI ... 4) 结构化 ... 5) Risk list + Confidence
#     ## Given Selected Topic: {selected_topic_content}
#     ## Draft Claims: {draft_claims_content}
#     ## Goal: Find >=15 similar works
#     ## Output: sections 0-6 (Plan, Actions, Evidence Table, Deliverables, Risks, Verification, Confidence)
#     """
#     return prompt


# v7 SOP 6.8 [S4] Claims Freeze — ChatGPT
def render_step_1_4_prompt(killer_prior_content: str, target_venue: str) -> str:
    """
    渲染 Step 1.4 Prompt: Claims Freeze (ChatGPT)
    v7 SOP 6.8 — PI role, 3 specific actions

    Args:
        killer_prior_content: Killer Prior Check 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI.

## Task
Lock claims & scope after de-risking via Killer Prior.

## Input
- `01_Killer_Prior_Check.md` (must be PASSED) — attached below.

## Killer Prior Check Result:
{killer_prior_content}

## Actions (complete all three)

### 1. Update and FREEZE the Claim Set
Incorporate Killer Prior recommended changes, then freeze:
- >=6 claims (final, frozen)
- >=6 non-claims (final, frozen)

### 2. Define Minimal Verification Set (MVS, <=6 units)
For each unit:
- Inputs (what goes in)
- Outputs (what comes out)
- PASS/FAIL criteria (binary, no ambiguity)

### 3. Define Pivot Rules
- If the key phenomenon is weak or absent, what is the closest alternative paper identity that still fits {target_venue}?
- Define 3 stop/pivot triggers with concrete thresholds.

## Output Format
Three files, each with YAML front-matter (gate_relevance: Gate2):
- `01_Claims_and_NonClaims.md` (status: frozen)
- `01_Minimal_Verification_Set.md`
- `01_Pivot_Rules.md`

You MUST output THREE separate markdown documents with clear delimiters:

---DOCUMENT_1: 01_Claims_and_NonClaims.md---
```yaml
---
doc_type: ClaimsAndNonClaims
version: "0.1"
status: frozen
created_by: ChatGPT
target_venue: "{target_venue}"
gate_relevance: Gate2
---
```
[Frozen claims and non-claims content]
---END_DOCUMENT_1---

---DOCUMENT_2: 01_Minimal_Verification_Set.md---
```yaml
---
doc_type: MinimalVerificationSet
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
gate_relevance: Gate2
---
```
[MVS with <=6 units, each with inputs/outputs/PASS-FAIL criteria]
---END_DOCUMENT_2---

---DOCUMENT_3: 01_Pivot_Rules.md---
```yaml
---
doc_type: PivotRules
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
gate_relevance: Gate2
---
```
[Pivot rules with 3 stop/pivot triggers]
---END_DOCUMENT_3---

Each document should be complete and standalone.
"""

    return prompt


# ============================================================
# LEGACY: Step 1.4 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_1_4_prompt_v4_legacy(killer_prior_content, target_venue):
#     prompt = f"""You are the PI. We have a Killer Prior Check result.
#     Target venue: {target_venue}
#     ## Killer Prior Check Result: {killer_prior_content}
#     ## Tasks:
#     1) Update and FREEZE the claim set (>=6 claims, >=6 non-claims)
#     2) Define a Minimal Verification Set (<=6 units, inputs/outputs/PASS-FAIL)
#     3) Define Pivot Rules (alternative paper identity if phenomenon is weak)
#     ## Output: THREE documents with YAML front-matter and delimiters
#     """
#     return prompt


# v7 SOP 6.15 [可选] Figure-First Story — Gemini
# Agentic Wrapper is handled by wrapper_mode parameter, NOT inlined in prompt.
def render_step_1_5_prompt(frozen_claims_content: str, target_venue: str) -> str:
    """
    渲染 Step 1.5 Prompt: Figure-First Story (Gemini)
    v7 SOP 6.15 — Senior Editor role, 3 specific actions

    Args:
        frozen_claims_content: Frozen Claims 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are a Senior Editor of {target_venue}.

## Task
Build a figure-first narrative after claims are frozen.

## Input
- `01_Claims_and_NonClaims.md` (frozen) — attached below.
- `01_Minimal_Verification_Set.md` — attached below.

## Frozen Claims + Minimal Figure List:
{frozen_claims_content}

## Actions (complete all three)

### 1. Figure-First Narrative
Build a figure-first narrative: each figure answers which reviewer question?

For each figure:
- Reviewer Question it answers
- Claims Supported (by claim number)
- Key Message (1-2 sentences)
- Caption style and emphasis points for {target_venue}

Describe the narrative flow: how figures connect to tell a coherent story.

### 2. Title + Abstract Candidates
Provide 3 title + abstract candidates (no hype, no invented results).

For each candidate:
- Title (concise, no hype)
- Abstract (150-200 words: Problem → Gap → Contribution → Key Results → Implications)
- Venue Fit Score (0.0-1.0) with justification

Recommend one with brief justification.

### 3. Caption Style Guidance
Suggest caption style and emphasis points for {target_venue}.

## Output Format
Two files with YAML front-matter:

---DOCUMENT_1: 01_Figure_First_Story.md---
```yaml
---
doc_type: FigureFirstStory
version: "0.1"
status: draft
created_by: Gemini
target_venue: "{target_venue}"
gate_relevance: Gate1
---
```
[Figure-first narrative + caption guidance]
---END_DOCUMENT_1---

---DOCUMENT_2: 01_Title_Abstract_Candidates.md---
```yaml
---
doc_type: TitleAbstractCandidates
version: "0.1"
status: draft
created_by: Gemini
target_venue: "{target_venue}"
gate_relevance: Gate1
---
```
[3 title + abstract candidates with recommendation]
---END_DOCUMENT_2---
"""

    return prompt


# ============================================================
# LEGACY: Step 1.5 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_1_5_prompt_v4_legacy(frozen_claims_content, target_venue):
#     prompt = f"""You are the senior editor of {target_venue}.
#     **CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
#     1) 先列 Plan ... 2) Evidence ... 3) 不允许占位符 ... 4) 结构化 ... 5) Risk list + Confidence
#     ## Given Frozen Claims: {frozen_claims_content}
#     ## Goal: Build figure-first narrative + 3 title/abstract candidates
#     ## Output: sections 0-6 (Plan, Actions, Evidence, Deliverables with Figure Narrative
#     ##   + Title/Abstract Candidates, Risks, Verification, Confidence)
#     ## Two documents: 01_Figure_First_Story.md + 01_Title_Abstract_Candidates.md
#     """
#     return prompt


def render_step_1_3b_prompt(literature_matrix_content: str, killer_prior_content: str = "") -> str:
    """
    渲染 Step 1.3b Prompt: Reference QA (Gemini) - v4.0 NEW (renamed from step_1_1b)

    Args:
        literature_matrix_content: Literature Matrix v7 内容
        killer_prior_content: Killer Prior Check 内容（可选，v7 S3b 输入）

    Returns:
        str: 渲染后的 prompt
    """
    killer_prior_section = ""
    if killer_prior_content:
        killer_prior_section = f"""

## Killer Prior Check Context:
{killer_prior_content}

Use the Killer Prior Check to cross-validate references and identify any additional references that should be verified.
"""

    prompt = f"""You are a meticulous research librarian and citation validator.

## Given Literature Matrix:
{literature_matrix_content}
{killer_prior_section}

## CRITICAL RULE — DO NOT FABRICATE DOIs OR URLs

You MUST copy the EXACT DOI or URL from the input documents for each reference.
- If the input has a full URL like `https://ieeexplore.ieee.org/document/9398860`, use EXACTLY that URL.
- If the input has `[10.1109/ACCESS.2022.3204981](https://ieeexplore.ieee.org/document/9868779)`, use EXACTLY that URL.
- If the input has a raw DOI identifier like `10.1109/ACCESS.2022.3204981` or `DOI: 10.2528/PIERM20061502` WITHOUT a full URL, convert it to a doi.org resolver link: `https://doi.org/10.1109/ACCESS.2022.3204981`. This is NOT fabrication — doi.org is the official DOI resolver.
- NEVER invent, guess, or "correct" a DOI number itself. If NO DOI and NO URL is present in the input for a reference, write "NO_DOI".
- NEVER convert an existing full URL (e.g., IEEE Xplore) to a doi.org URL. Keep existing full URLs as-is. Only use doi.org for raw DOI identifiers that have no accompanying URL.

## Tasks:

1) **Extract and Merge References**
   - Extract all references from the Literature Matrix AND the Killer Prior Check (if provided)
   - Merge and deduplicate by title similarity
   - Copy the ORIGINAL DOI/URL exactly as it appears in the input

2) **Quality Checks**
   - Identify references missing DOI/URL
   - Flag potential duplicates (similar titles)
   - Check for incomplete citations (missing venue, year, etc.)

3) **Generate Verified References**
   - Create a clean bibliography in BibTeX format
   - Use the ORIGINAL URL/DOI from the input documents in each BibTeX entry
   - Use consistent citation keys (e.g., author_year_keyword)

## Output Format:

### A) Literature Matrix (Enhanced)
Reproduce ALL references as a numbered markdown table with these columns:

| # | Title | Venue/Year | DOI/Link | Status |
|---|-------|------------|----------|--------|
| 1 | [Paper title] | [Venue, Year] | [Link](ORIGINAL_URL_FROM_INPUT) | HAS_URL / NO_DOI |

Rules for DOI/Link column:
- If the input has a full URL, copy it EXACTLY: `[Link](https://ieeexplore.ieee.org/document/XXXXXXX)`
- If the input has only a raw DOI (e.g., `10.1109/...`), convert to resolver link: `[DOI](https://doi.org/10.1109/...)`
- If neither URL nor DOI exists in the input, write `NO_DOI`.
- NEVER fabricate a DOI number. Only use DOI identifiers that appear in the input documents.

Every reference from both input documents must appear. Number rows sequentially starting from 1.

### B) Reference Quality Report
- Total references: [count]
- References with URL/DOI: [count] ([percentage]%)
- Missing DOI/URL: [count]
- Potential duplicates: [list if any]

### C) Action Items
[List of references that are missing URL/DOI or have incomplete metadata]

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
  - "01_C_Literature_Matrix.md"
  - "01_Killer_Prior_Check.md"
outputs:
  - "01_Reference_QA_Report.md"
  - "01_Verified_References.bib"
gate_relevance: "Gate 1.6"
evidence_quality: "[0.0-1.0 based on URL coverage rate]"
doi_validation_passed: "[true/false based on quality threshold]"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections A-C).

## FINAL REMINDER
DO NOT fabricate any DOI number. Every DOI identifier in your output must exist in the input documents. Converting a raw DOI like `10.xxxx/yyyy` to `https://doi.org/10.xxxx/yyyy` is allowed and encouraged — that is the official DOI resolver, not fabrication.
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

    prompt = f"""You are the PI performing a Topic Alignment Check (Gate 1).

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
- Gate 1 Verdict: PASS / FAIL
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
gate_relevance: "Gate 1"
north_star_question: "[Extract from intake card]"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections 1-4).

Return as 01_Topic_Alignment_Check.md.
"""

    return prompt


# v7.1 S1-1: Core terms addendum for Topic Decision
TOPIC_DECISION_CORE_TERMS_ADDENDUM = """

## Additional Requirement (v7.1): Core Terms Declaration

At the end of your output, include a YAML block listing the core academic terms used:

```yaml
core_terms:
  - "term_1"
  - "term_2"
  - "term_3"
  - "term_4"
  - "term_5"
```

These terms will be validated against OpenAlex and Crossref at Gate 1.
Use established academic terminology. Avoid invented or overly niche terms.
"""


# v7.1 S1-2: Idea-Lab prompts
IDEA_LAB_GEMINI_PROMPT = """You are a creative research ideation agent. Your goal is to generate 10-15 divergent research idea candidates based on the literature matrix.

## Literature Matrix
{literature_matrix}

## Research Context
- Topic area: {topic}
- Target venue: {venue}

## Task
Generate 10-15 candidate research ideas. For each idea, provide:

1. **title**: A concise, descriptive title (1 line)
2. **gap**: The specific research gap this idea addresses (2-3 sentences)
3. **mechanism**: The proposed mechanism or approach (2-3 sentences)
4. **novelty_delta**: What makes this different from existing work (1-2 sentences)
5. **feasibility_score**: Estimated feasibility (0.0-1.0) with brief justification

## Output Format (MUST follow exactly)

### Idea 1
- **title**: [title]
- **gap**: [gap description]
- **mechanism**: [mechanism description]
- **novelty_delta**: [novelty description]
- **feasibility_score**: [0.0-1.0] — [justification]

### Idea 2
...

(Repeat for all ideas)

## Guidelines
- Be creative and divergent — explore different angles
- At least 2 ideas should be "high-risk, high-reward"
- At least 1 idea should be conservative and highly feasible
- Ground each idea in evidence from the literature matrix
- Avoid ideas that are trivial extensions of existing work
"""


TOPIC_DECISION_IDEALAB_ADDENDUM = """

## Additional Context: Idea-Lab Candidates

The following divergent research ideas were generated by the Idea-Lab:

{idea_lab_content}

Consider these candidates alongside the literature analysis when making your topic decision.
You may select one of these ideas, combine elements, or propose something entirely different.
"""

"""
Step 2 Prompts
Step 2 阶段的所有提示词模板
"""


def render_step_2_1_prompt(selected_topic_content: str, frozen_claims_content: str,
                           target_venue: str) -> str:
    """
    渲染 Step 2.1 Prompt: Full Proposal (ChatGPT)

    Args:
        selected_topic_content: Selected Topic 内容
        frozen_claims_content: Frozen Claims 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""Topic is frozen. You are the PI. Write a full Research Proposal (the constitution).

Target venue: {target_venue}

## Selected Topic:
{selected_topic_content}

## Frozen Claims and NonClaims:
{frozen_claims_content}

## Must include:

1) **System/Study Model** (formal definitions; endpoints; time axis; cohorts/sim setup).

2) **Main method** (math/stat/algorithm logic; NOT just pseudocode).

3) **Evaluation design:**
   - baselines (>=2) with fairness justification
   - ablations
   - robustness checks (>=6, prioritized by likely reviewer attacks)

4) **Uncertainty / statistical reporting plan** (CI/bootstrap/etc as appropriate).

5) **Claim-to-Evidence map:** each claim points to specific figure/table/tests.

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "02_Full_Proposal"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "{target_venue}"
topic: "[One-line summary from selected topic]"
inputs:
  - "01_Selected_Topic.md"
  - "01_Claims_and_NonClaims.md"
  - "02_Figure_Table_List.md"
outputs:
  - "02_Full_Proposal.md"
gate_relevance: "Gate 2"
---
```

After the YAML front-matter, provide the complete document content including all required sections (1-5).

Output as a comprehensive markdown document (02_Full_Proposal.md).
"""

    return prompt


def render_step_2_2_prompt(full_proposal_content: str) -> str:
    """
    渲染 Step 2.2 Prompt: Data/Simulation Spec (ChatGPT)

    Args:
        full_proposal_content: Full Proposal 内容

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""Translate the proposal into an engineering-grade Data/Simulation Spec.

## Full Proposal:
{full_proposal_content}

## Include:

1) **Table(s) / parameter schema**

2) **For each field:** definition, unit, range, missingness rule, cleaning rule

3) **Derived variables:** formulas + edge cases

4) **Alignment rules:** join keys, timepoint matching, multi-source merging

5) **QC rules:** outlier detection & exclusion criteria (reproducible)

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "02_Data_or_Sim_Spec"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from full proposal]"
inputs:
  - "02_Full_Proposal.md"
outputs:
  - "02_Data_or_Sim_Spec.md"
gate_relevance: "Gate 2"
---
```

After the YAML front-matter, provide the complete document content including all required sections (1-5).

Output as a comprehensive markdown document (02_Data_or_Sim_Spec.md).
"""

    return prompt


def render_step_2_3_prompt(full_proposal_content: str, data_spec_content: str = "") -> str:
    """
    渲染 Step 2.3 Prompt: Engineering Decomposition (ChatGPT)

    Args:
        full_proposal_content: Full Proposal 内容
        data_spec_content: Data/Sim Spec 内容（可选）

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""Decompose the proposal into independent engineering modules (for Claude to implement).

## Full Proposal:
{full_proposal_content}

"""

    if data_spec_content:
        prompt += f"""## Data/Simulation Spec:
{data_spec_content}

"""

    prompt += """## IMPORTANT - Output Format:

You MUST output TWO separate markdown documents with clear delimiters. Each document MUST begin with its own YAML front-matter:

**For 03_Engineering_Spec.md:**
```yaml
---
doc_type: "03_Engineering_Spec"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from full proposal]"
inputs:
  - "02_Full_Proposal.md"
  - "02_Data_or_Sim_Spec.md"
outputs:
  - "03_Engineering_Spec.md"
gate_relevance: "Gate 2"
---
```

**For 03_TestPlan.md:**
```yaml
---
doc_type: "03_TestPlan"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from full proposal]"
inputs:
  - "02_Full_Proposal.md"
  - "03_Engineering_Spec.md"
outputs:
  - "03_TestPlan.md"
gate_relevance: "Gate 2"
---
```

---DOCUMENT_1: 03_Engineering_Spec.md---
[Content for Engineering Spec containing:

1) **Global parameters** (defaults + sweep ranges + random seeds policy)

2) **Ordered module breakdown:**
   - Module ID, purpose
   - Inputs (shape/type/unit), Outputs (shape/type/unit)
   - Verification logic (unit tests + invariants)

3) **End-to-end sanity checks**

4) **Reproducibility:**
   - directory layout
   - run commands
   - artifact paths (figures/tables/logs)]
---END_DOCUMENT_1---

---DOCUMENT_2: 03_TestPlan.md---
[Content for Test Plan containing:
- List of all tests (unit tests, integration tests, end-to-end tests)
- For each test:
  - Test ID
  - Purpose
  - Inputs
  - Expected outputs
  - PASS criteria
  - FAIL criteria
- Test execution order
- Dependencies between tests]
---END_DOCUMENT_2---

Each document should be complete and standalone.
"""

    return prompt


def render_step_2_4_prompt(full_proposal_content: str, engineering_spec_content: str,
                           target_venue: str) -> str:
    """
    渲染 Step 2.4 Prompt: Reviewer #2 Red-Team (Gemini)

    Args:
        full_proposal_content: Full Proposal 内容
        engineering_spec_content: Engineering Spec 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are Reviewer #2 (strict). Review the proposal + engineering spec.

**CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
1) 先列 Plan（最多 6 步），再执行审查/分析，再输出产物；不要先写结论。
2) 每个关键判断必须给 Evidence（引用 proposal 或 engineering spec 中的具体章节）。
3) 不允许占位符或模糊引用；若找不到就标记 UNKNOWN 并降级结论。
4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。

Target venue: {target_venue}

## Full Proposal:
{full_proposal_content}

## Engineering Spec:
{engineering_spec_content}

## Output (MUST be structured, no long essay):

## 0) Plan
List 3-6 steps you will take to complete this Red-Team Review:
- Step 1: [action - e.g., extract main claims from proposal]
- Step 2: [action - e.g., identify evaluation gaps]
- Step 3: [action - e.g., check baseline fairness]
- Step 4: [action - e.g., assess robustness checks]
- Step 5: [action - e.g., rank fatal issues]
- Step 6: [action - e.g., generate minimal patch set]

## 1) Actions Taken
Document what you actually did:
- Reviewed: [sections of proposal and engineering spec]
- Identified: [number] potential issues
- Ranked: [number] fatal issues
- Generated: [number] patches

## 2) Evidence Validation
For each key issue identified, provide:
- Issue: [description]
- Evidence: [specific section/claim from proposal or engineering spec]
- Severity: FATAL / MAJOR / MINOR
- Status: VERIFIED / NEEDS_VERIFICATION

## 3) Deliverables

### A) Fatal Issues (Ranked)

**List 20 most fatal issues (ranked by severity):**

For each issue:
- **Issue ID**: [e.g., FATAL-01]
- **Description**: [What is the problem?]
- **Evidence**: [Which section of proposal/engineering spec reveals this issue?]
- **Why Fatal**: [Why would this cause rejection at {target_venue}?]
- **Already Covered**: [YES/NO - Is this already addressed in the proposal?]
- **Minimal Fix**: [What specific change is needed? E.g., "Add Figure X showing Y", "Tighten definition of Z", "Add robustness check for W"]

### B) Minimal Patch Set (<=5 items)

Based on the fatal issues, provide a minimal patch set:

**Patch 1:**
- **Addresses Issues**: [List issue IDs, e.g., FATAL-01, FATAL-03]
- **Change Required**: [Specific action - e.g., "Add baseline comparison with method X"]
- **Impact**: [Which sections need updating - e.g., "Section 3.2, Figure 2, Table 1"]
- **Priority**: HIGH / MEDIUM / LOW

**Patch 2:**
[Same structure]

**Patch 3:**
[Same structure]

**Patch 4:**
[Same structure]

**Patch 5:**
[Same structure]

## 4) Risks
List >=5 risks identified during Red-Team Review:
- Risk 1: [e.g., Baseline X may not be available for comparison]
- Risk 2: [e.g., Robustness check Y requires additional data not specified]
- Risk 3: [e.g., Statistical test Z may not be sufficient for {target_venue} standards]
- Risk 4: [e.g., Claim 3 lacks sufficient evidence in current figure set]
- Risk 5: [e.g., Engineering spec missing implementation details for module M]
- ...

## 5) Verification Checklist
List >=5 items that need verification before proceeding:
- [ ] Item 1: [e.g., Confirm baseline X is implementable with available resources]
- [ ] Item 2: [e.g., Verify that robustness check Y is standard for {target_venue}]
- [ ] Item 3: [e.g., Check if additional figures are needed for Claim 3]
- [ ] Item 4: [e.g., Validate that engineering spec covers all proposal requirements]
- [ ] Item 5: [e.g., Ensure all fatal issues have corresponding patches]
- ...

## 6) Confidence Score
Overall confidence in this Red-Team Review: [0.0-1.0]
- Issue identification: [0.0-1.0] (how thoroughly we reviewed)
- Evidence quality: [0.0-1.0] (% of issues with clear evidence)
- Patch effectiveness: [0.0-1.0] (how well patches address fatal issues)
- Venue alignment: [0.0-1.0] (how well review matches {target_venue} standards)

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "03_RedTeam_Reviewer2"
version: "0.1"
status: "draft"
created_by: "Gemini"
target_venue: "{target_venue}"
topic: "[One-line summary from full proposal]"
inputs:
  - "02_Full_Proposal.md"
  - "03_Engineering_Spec.md"
outputs:
  - "03_RedTeam_Reviewer2.md"
gate_relevance: "Gate 2"
---
```

After the YAML front-matter, provide the complete document content following the structure above (sections 0-6).

Output as a comprehensive markdown document (03_RedTeam_Reviewer2.md).

**REMINDER**: Do NOT wrap the entire output in ```markdown``` code blocks. Output should be direct markdown content.
"""

    return prompt


def render_step_2_5_prompt(full_proposal_content: str, engineering_spec_content: str,
                           redteam_content: str, frozen_claims_content: str) -> str:
    """
    渲染 Step 2.5 Prompt: Plan Freeze Package (ChatGPT)

    Args:
        full_proposal_content: Full Proposal 内容
        engineering_spec_content: Engineering Spec 内容
        redteam_content: Red Team Review 内容
        frozen_claims_content: Frozen Claims 内容

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""Create the Plan Freeze package.

## Frozen Claims:
{frozen_claims_content}

## Full Proposal:
{full_proposal_content}

## Engineering Spec:
{engineering_spec_content}

## Red Team Review:
{redteam_content}

## Tasks:

1) **Compile the final frozen plan:**
   - claims + non-claims
   - figure/table list
   - method + evaluation + robustness + subgroup plan
   - baselines + ablations

2) **Add Stop/Pivot checkpoints (3–5):**
   - after which key deliverables we decide go / pivot / stop

3) **Add versioning rules:**
   execution cannot add new modules unless the plan version increments and re-passes Gate 2.

4) **Reference Killer Prior Check:**
   - IMPORTANT: Include a section that references the Killer Prior Check (Gate 1.5) PASS result
   - Summarize how this research differentiates from prior work
   - This is MANDATORY for Gate 2 to pass

## YAML Front-Matter Requirements

You MUST output THREE separate markdown documents with clear delimiters. Each document MUST begin with its own YAML front-matter:

**For 04_Research_Plan_FROZEN.md:**
```yaml
---
doc_type: "04_Research_Plan_FROZEN"
version: "1.0"
status: "frozen"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from frozen claims]"
inputs:
  - "01_Claims_and_NonClaims.md"
  - "02_Full_Proposal.md"
  - "03_Engineering_Spec.md"
  - "03_RedTeam_Reviewer2.md"
  - "01_Killer_Prior_Check.md"
outputs:
  - "04_Research_Plan_FROZEN.md"
gate_relevance: "Gate 2"
killer_prior_status: "PASS"
---
```

**For 04_Execution_Order.md:**
```yaml
---
doc_type: "04_Execution_Order"
version: "1.0"
status: "frozen"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from frozen claims]"
inputs:
  - "03_Engineering_Spec.md"
  - "03_TestPlan.md"
outputs:
  - "04_Execution_Order.md"
gate_relevance: "Gate 2"
---
```

**For 04_Stop_or_Pivot_Checkpoints.md:**
```yaml
---
doc_type: "04_Stop_or_Pivot_Checkpoints"
version: "1.0"
status: "frozen"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from frozen claims]"
inputs:
  - "04_Research_Plan_FROZEN.md"
  - "01_Pivot_Rules.md"
outputs:
  - "04_Stop_or_Pivot_Checkpoints.md"
gate_relevance: "Gate 2"
---
```

## IMPORTANT - Output Format:

You MUST output THREE separate markdown documents with clear delimiters:

---DOCUMENT_1: 04_Research_Plan_FROZEN.md---
[Content for frozen plan containing:
- Final frozen claims + non-claims
- Figure/table list
- Method + evaluation + robustness + subgroup plan
- Baselines + ablations
- Killer Prior Check reference (MANDATORY)
- Versioning rules]
---END_DOCUMENT_1---

---DOCUMENT_2: 04_Execution_Order.md---
[Content for execution order containing:
- Ordered list of engineering modules (from Engineering Spec)
- Dependencies between modules
- Estimated timeline
- Critical path
- Parallel execution opportunities]
---END_DOCUMENT_2---

---DOCUMENT_3: 04_Stop_or_Pivot_Checkpoints.md---
[Content for stop/pivot checkpoints containing:
- 3-5 checkpoints with:
  * Checkpoint ID
  * After which deliverable(s)
  * Success criteria (GO)
  * Pivot criteria (PIVOT - what to change)
  * Stop criteria (STOP - when to abandon)
  * Decision timeline]
---END_DOCUMENT_3---

Each document should be complete and standalone.
"""

    return prompt


def render_step_2_0_prompt(frozen_claims_content: str, target_venue: str) -> str:
    """
    渲染 Step 2.0 Prompt: Figure/Table List (ChatGPT) - v4.0 NEW

    Args:
        frozen_claims_content: Frozen Claims 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI. Before writing the full proposal, create a comprehensive Figure/Table List.

Target venue: {target_venue}

## Frozen Claims and NonClaims:
{frozen_claims_content}

## Tasks:

1) **List all planned figures and tables (<=8 total)**
   For each figure/table:
   - ID (e.g., Fig1, Table1)
   - Title/Caption (draft)
   - Purpose: Which claim(s) does it support?
   - Content: What will be shown? (axes, metrics, comparisons)
   - Acceptance criteria: What pattern/result would make this figure "successful"?

2) **Map Claims to Figures/Tables**
   - For each claim, list which figure(s)/table(s) provide evidence
   - Ensure every claim has at least one figure/table

3) **Prioritize by Importance**
   - Mark which figures are CRITICAL (must-have for main claims)
   - Mark which are SUPPORTING (nice-to-have for robustness)

4) **Venue-Specific Guidance**
   - What figure style does {target_venue} prefer?
   - What level of detail in captions?
   - Any specific requirements (e.g., error bars, statistical tests)?

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "02_Figure_Table_List"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "{target_venue}"
topic: "[One-line summary from frozen claims]"
inputs:
  - "01_Claims_and_NonClaims.md"
  - "01_Figure_First_Story.md"
outputs:
  - "02_Figure_Table_List.md"
gate_relevance: "Gate 2"
---
```

After the YAML front-matter, provide the complete document content including:

## Output Format:

### A) Figure/Table List
[Table with columns: ID | Title | Purpose (Claims) | Content | Acceptance Criteria | Priority]

### B) Claim-to-Evidence Map
[For each claim, list supporting figures/tables]

### C) Venue-Specific Notes
[Style guidance for {target_venue}]

Return as 02_Figure_Table_List.md.
"""

    return prompt


def render_step_2_4b_prompt(redteam_content: str, full_proposal_content: str,
                            engineering_spec_content: str) -> str:
    """
    渲染 Step 2.4b Prompt: Patch Propagation (ChatGPT) - v4.0 NEW

    Args:
        redteam_content: Red Team Review 内容
        full_proposal_content: Full Proposal 内容
        engineering_spec_content: Engineering Spec 内容

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI. Apply the Red Team patches to the proposal and engineering spec.

## Red Team Review (with minimal patch set):
{redteam_content}

## Current Full Proposal:
{full_proposal_content}

## Current Engineering Spec:
{engineering_spec_content}

## Tasks:

1) **Extract Patch Items**
   - List all patches from the Red Team review (<=5 items)
   - For each patch:
     * Issue ID
     * Issue description
     * Proposed fix
     * Impact (which sections need updating)

2) **Apply Patches**
   - For each patch, describe:
     * What changes in the Full Proposal
     * What changes in the Engineering Spec
     * What new figures/tables/tests are needed
   - Generate a diff-style summary

3) **Verify Coverage**
   - Check that all critical issues are addressed
   - Identify any remaining risks

4) **Update Checklist**
   - List all sections that need manual review/update
   - Prioritize by urgency

## YAML Front-Matter Requirements

Your output MUST begin with the following YAML front-matter (fill in the bracketed values):

```yaml
---
doc_type: "03_Patch_Diff"
version: "0.1"
status: "draft"
created_by: "ChatGPT"
target_venue: "[Extract from full proposal]"
topic: "[One-line summary from full proposal]"
inputs:
  - "03_RedTeam_Reviewer2.md"
  - "02_Full_Proposal.md"
  - "03_Engineering_Spec.md"
outputs:
  - "03_Patch_Diff.md"
gate_relevance: "Gate 2"
---
```

After the YAML front-matter, provide the complete document content including:

## Output Format:

### A) Patch Summary
[Table: Patch ID | Issue | Fix | Impact | Status]

### B) Proposal Changes
[Diff-style summary of changes to Full Proposal]

### C) Engineering Spec Changes
[Diff-style summary of changes to Engineering Spec]

### D) New Requirements
[List of new figures/tables/tests needed]

### E) Manual Review Checklist
[Prioritized list of sections needing manual update]

Return as 03_Patch_Diff.md.
"""

    return prompt

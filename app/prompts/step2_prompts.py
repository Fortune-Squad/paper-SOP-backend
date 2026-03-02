"""
Step 2 Prompts
Step 2 阶段的所有提示词模板
"""


# v7 SOP 6.9 [S5a] Full Proposal — ChatGPT
def render_step_2_1_prompt(selected_topic_content: str, frozen_claims_content: str,
                           target_venue: str, mvs_content: str = "") -> str:
    """
    渲染 Step 2.1 Prompt: Full Proposal (ChatGPT)
    v7 SOP 6.9 — PI role, 5 required sections

    Args:
        selected_topic_content: Selected Topic 内容
        frozen_claims_content: Frozen Claims 内容
        target_venue: 目标期刊
        mvs_content: Minimal Verification Set 内容（可选）

    Returns:
        str: 渲染后的 prompt
    """
    mvs_section = ""
    if mvs_content:
        mvs_section = f"""

## Minimal Verification Set:
{mvs_content}

Use the MVS to ensure the proposal's evaluation design covers all required verification units.
"""

    prompt = f"""You are the PI.

## Task
Write a full Research Proposal — the "constitution" of this project.

## Input
- `01_Selected_Topic.md` — attached below.
- `01_Claims_and_NonClaims.md` (frozen) — attached below.
- `01_Minimal_Verification_Set.md` — attached below.

## Selected Topic:
{selected_topic_content}

## Frozen Claims and NonClaims:
{frozen_claims_content}
{mvs_section}
## Must Include (all five sections)

### 1. System/Study Model
Formal definitions, endpoints, time axis, cohorts/sim setup.

### 2. Core Method
Math/stat/algorithm logic (NOT just pseudocode — show the math).

### 3. Evaluation Design
- Baselines (>=2) with fairness justification
- Ablations
- Robustness checks (>=6 for Top-Journal, >=3 for Fast-Track, prioritized by likely reviewer attacks)

### 4. Uncertainty / Statistical Reporting Plan
CI/bootstrap/etc as appropriate.

### 5. Claim-to-Evidence Map
Each claim → specific figure/table/test that proves it.

## Output Format
File: `02_Full_Proposal.md`

Begin with YAML front-matter:
```yaml
---
doc_type: FullProposal
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
topic: "[One-line summary]"
gate_relevance: Gate2
---
```

Then provide all 5 sections above as a comprehensive markdown document.
"""

    return prompt


# ============================================================
# LEGACY: Step 2.1 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_2_1_prompt_v4_legacy(selected_topic_content, frozen_claims_content,
#                            target_venue, mvs_content=""):
#     prompt = f"""Topic is frozen. You are the PI. Write a full Research Proposal (the constitution).
#     Target venue: {target_venue}
#     ## Selected Topic: {selected_topic_content}
#     ## Frozen Claims: {frozen_claims_content}
#     ## Must include: 1) System/Study Model 2) Main method 3) Evaluation design
#     4) Uncertainty/statistical reporting 5) Claim-to-Evidence map
#     ## YAML Front-Matter with doc_type: "02_Full_Proposal"
#     """
#     return prompt


# v7 SOP 6.10 [S5b] Data / Simulation Spec — ChatGPT
def render_step_2_2_prompt(full_proposal_content: str) -> str:
    """
    渲染 Step 2.2 Prompt: Data/Simulation Spec (ChatGPT)
    v7 SOP 6.10 — PI / Data Architect role, 5 required sections

    Args:
        full_proposal_content: Full Proposal 内容

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI / Data Architect.

## Task
Translate the proposal into an engineering-grade Data/Simulation Spec.

## Input
- `02_Full_Proposal.md` + any data dictionary available — attached below.

## Full Proposal:
{full_proposal_content}

## Must Include (all five sections)

### 1. Table(s) / Parameter Schema

### 2. Field Definitions
For each field: definition, unit, range, missingness rule, cleaning rule.

### 3. Derived Variables
Formulas + edge cases.

### 4. Alignment Rules
Join keys, timepoint matching, multi-source merging.

### 5. QC Rules
Outlier detection & exclusion criteria (reproducible).

## Output Format
File: `02_Data_or_Sim_Spec.md`

Begin with YAML front-matter:
```yaml
---
doc_type: DataOrSimSpec
version: "0.1"
status: draft
created_by: ChatGPT
gate_relevance: Gate2
---
```

Then provide all 5 sections above.
"""

    return prompt


# ============================================================
# LEGACY: Step 2.2 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_2_2_prompt_v4_legacy(full_proposal_content):
#     prompt = f"""Translate the proposal into an engineering-grade Data/Simulation Spec.
#     ## Full Proposal: {full_proposal_content}
#     ## Include: 1) Table(s)/parameter schema 2) Field definitions 3) Derived variables
#     4) Alignment rules 5) QC rules
#     ## YAML Front-Matter with doc_type: "02_Data_or_Sim_Spec"
#     """
#     return prompt


# v7 SOP 6.11 [S5c] Engineering Spec + TestPlan — ChatGPT
def render_step_2_3_prompt(full_proposal_content: str, data_spec_content: str = "") -> str:
    """
    渲染 Step 2.3 Prompt: Engineering Spec + TestPlan (ChatGPT)
    v7 SOP 6.11 — PI / Systems Architect role

    Args:
        full_proposal_content: Full Proposal 内容
        data_spec_content: Data/Sim Spec 内容（可选）

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI / Systems Architect.

## Task
Decompose the proposal into independent engineering modules (for Claude to implement in Step 3).

## Input
- `02_Full_Proposal.md` — attached below.
- `02_Data_or_Sim_Spec.md` — attached below.

## Full Proposal:
{full_proposal_content}

"""

    if data_spec_content:
        prompt += f"""## Data/Simulation Spec:
{data_spec_content}

"""

    prompt += """## Engineering Spec Must Include

### 1. Global Parameters
Defaults + sweep ranges + random seeds policy.

### 2. Ordered Module Breakdown
For each module:
- Module ID + purpose
- Inputs (shape/type/unit)
- Outputs (shape/type/unit)
- Verification logic (unit tests + invariants)

### 3. End-to-End Sanity Checks
Minimum 5 sanity checks.

### 4. Reproducibility
- Directory layout
- Run commands
- Artifact paths (figures/tables/logs)

## TestPlan Must Include
For each test:
- Test ID
- What it verifies
- Expected PASS criteria
- Dependencies (which module must pass first)

## Output Format
Two files with YAML front-matter (gate_relevance: Gate2):

---DOCUMENT_1: 03_Engineering_Spec.md---
```yaml
---
doc_type: EngineeringSpec
version: "0.1"
status: draft
created_by: ChatGPT
gate_relevance: Gate2
---
```
[Engineering Spec content with sections 1-4]
---END_DOCUMENT_1---

---DOCUMENT_2: 03_TestPlan.md---
```yaml
---
doc_type: TestPlan
version: "0.1"
status: draft
created_by: ChatGPT
gate_relevance: Gate2
---
```
[TestPlan content with test list]
---END_DOCUMENT_2---

Each document should be complete and standalone.
"""

    return prompt


# ============================================================
# LEGACY: Step 2.3 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_2_3_prompt_v4_legacy(full_proposal_content, data_spec_content=""):
#     prompt = f"""Decompose the proposal into independent engineering modules (for Claude to implement).
#     ## Full Proposal: {full_proposal_content}
#     ## Data/Simulation Spec: {data_spec_content}
#     ## Output TWO documents: 03_Engineering_Spec.md (global params, module breakdown,
#     ##   sanity checks, reproducibility) + 03_TestPlan.md (test list with ID/purpose/PASS/FAIL)
#     """
#     return prompt


# v7 SOP 6.12 [S6] Red Team Review — Gemini
# Agentic Wrapper is handled by wrapper_mode parameter, NOT inlined in prompt.
def render_step_2_4_prompt(full_proposal_content: str, engineering_spec_content: str,
                           target_venue: str, frozen_claims_content: str = "",
                           mvs_content: str = "", test_plan_content: str = "",
                           killer_prior_content: str = "") -> str:
    """
    渲染 Step 2.4 Prompt: Red Team Review (Gemini)
    v7 SOP 6.12 — Reviewer #2 (Hostile but Constructive) role, 3 actions

    Args:
        full_proposal_content: Full Proposal 内容
        engineering_spec_content: Engineering Spec 内容
        target_venue: 目标期刊
        frozen_claims_content: Frozen Claims 内容（v7 必须）
        mvs_content: Minimal Verification Set 内容（v7 必须）
        test_plan_content: Test Plan 内容（v7 必须）
        killer_prior_content: Killer Prior Check 内容（v7 必须）

    Returns:
        str: 渲染后的 prompt
    """
    # 构建可选输入段
    claims_section = ""
    if frozen_claims_content:
        claims_section = f"""
## Frozen Claims and NonClaims:
{frozen_claims_content}

"""

    mvs_section = ""
    if mvs_content:
        mvs_section = f"""
## Minimal Verification Set:
{mvs_content}

"""

    test_plan_section = ""
    if test_plan_content:
        test_plan_section = f"""
## Test Plan:
{test_plan_content}

"""

    killer_prior_section = ""
    if killer_prior_content:
        killer_prior_section = f"""
## Killer Prior Check (Top 5 Prior):
{killer_prior_content}

"""

    prompt = f"""You are Reviewer #2 (Hostile but Constructive).

## Task
Find fatal weaknesses. Output must be ACTIONABLE patches, not vague criticism.

## Input (Review Packet — all must be read before responding)
- `01_Claims_and_NonClaims.md` (frozen claims)
- `01_Minimal_Verification_Set.md`
- `02_Full_Proposal.md`
- `03_Engineering_Spec.md`
- `03_TestPlan.md`
- `01_Killer_Prior_Check.md` (Top 5 prior)

Target venue: {target_venue}

{claims_section}{mvs_section}## Full Proposal:
{full_proposal_content}

## Engineering Spec:
{engineering_spec_content}
{test_plan_section}{killer_prior_section}
## Actions (complete all three)

### 1. Fatal Issues (Ranked)
List up to 20 most fatal issues (ranked by severity). For each:
- Why fatal (cite specific claim/figure/test)
- Whether already addressed in the spec
- What minimal fix is needed

### 2. Minimal Patch Set
Provide a minimal patch set (Top-Journal: <=5, Fast-Track: <=3). Each patch must specify:
- Which artifact to modify (file path)
- What to add/change (specific figure/table/definition/robustness check)
- Verifiable DoD for the patch

### 3. Observations
Issues without actionable patches are logged as "observations" — they do NOT block the gate.

## Output Format
File: `03_RedTeam_Reviewer2.md`

Begin with YAML front-matter:
```yaml
---
doc_type: RedTeamReviewer2
version: "0.1"
status: draft
created_by: Gemini
target_venue: "{target_venue}"
gate_relevance: Gate2
---
```

Then provide all 3 sections above.
"""

    return prompt


# ============================================================
# LEGACY: Step 2.4 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_2_4_prompt_v4_legacy(full_proposal_content, engineering_spec_content,
#                            target_venue, frozen_claims_content="", mvs_content="",
#                            test_plan_content="", killer_prior_content=""):
#     prompt = f"""You are Reviewer #2 (strict). Review the complete Review Packet.
#     **CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**
#     1) 先列 Plan ... 2) Evidence ... 3) 不允许占位符 ... 4) 结构化 ... 5) Risk list + Confidence
#     ROLE: Reviewer #2 (Hostile but Constructive)
#     TASK: Find fatal weaknesses. Output ACTIONABLE patches.
#     ## Output: sections 0-6 (Plan, Actions, Evidence, Deliverables with Fatal Issues
#     ##   + Minimal Patch Set, Risks, Verification, Confidence)
#     """
#     return prompt


# v7 SOP 6.14 [S7] Plan Freeze — ChatGPT
def render_step_2_5_prompt(full_proposal_content: str, engineering_spec_content: str,
                           redteam_content: str, frozen_claims_content: str) -> str:
    """
    渲染 Step 2.5 Prompt: Plan Freeze Package (ChatGPT)
    v7 SOP 6.14 — PI role, 5 actions

    Args:
        full_proposal_content: Full Proposal 内容
        engineering_spec_content: Engineering Spec 内容
        redteam_content: Red Team Review 内容
        frozen_claims_content: Frozen Claims 内容

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI.

## Task
Create the Plan Freeze package. This is the final deliverable of Step 0-2.

## Input
All artifacts from S0-S6, especially post-patch versions — attached below.

## Frozen Claims:
{frozen_claims_content}

## Full Proposal:
{full_proposal_content}

## Engineering Spec:
{engineering_spec_content}

## Red Team Review:
{redteam_content}

## Actions (complete all five)

### 1. Compile the Final Frozen Plan
- Frozen claims + non-claims
- Figure/table list (each mapped to claim + reviewer attack)
- Method + evaluation + robustness + ablation plan
- Baselines

### 2. Add Stop/Pivot Checkpoints (>=3)
- After which key deliverables we decide go / pivot / stop
- Concrete thresholds for each decision

### 3. Add Execution Order
- Which modules to build first (highest-risk or most-validating first)

### 4. Add Versioning Rules
- Execution cannot add new modules unless the plan version increments and re-passes Gate 2.

### 5. Reference All Gate Results
- Gate 0/1/1.5/1.6/2 PASS evidence
- Killer Prior Check differentiation summary (MANDATORY for Gate 2)

## Output Format
Three files (status: frozen), each with YAML front-matter:

---DOCUMENT_1: 04_Research_Plan_FROZEN.md---
```yaml
---
doc_type: ResearchPlanFrozen
version: "1.0"
status: frozen
created_by: ChatGPT
gate_relevance: Gate2
killer_prior_status: PASS
---
```
[Frozen plan with sections 1, 4, 5]
---END_DOCUMENT_1---

---DOCUMENT_2: 04_Execution_Order.md---
```yaml
---
doc_type: ExecutionOrder
version: "1.0"
status: frozen
created_by: ChatGPT
gate_relevance: Gate2
---
```
[Execution order from section 3]
---END_DOCUMENT_2---

---DOCUMENT_3: 04_Stop_or_Pivot_Checkpoints.md---
```yaml
---
doc_type: StopOrPivotCheckpoints
version: "1.0"
status: frozen
created_by: ChatGPT
gate_relevance: Gate2
---
```
[Stop/pivot checkpoints from section 2]
---END_DOCUMENT_3---

Each document should be complete and standalone.

THIS REQUIRES HUMAN SIGN-OFF (Gate 2 final confirmation) BEFORE PROCEEDING TO STEP 3.
"""

    return prompt


# ============================================================
# LEGACY: Step 2.5 Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_2_5_prompt_v4_legacy(full_proposal_content, engineering_spec_content,
#                            redteam_content, frozen_claims_content):
#     prompt = f"""Create the Plan Freeze package.
#     ## Frozen Claims: {frozen_claims_content}
#     ## Full Proposal: {full_proposal_content}
#     ## Engineering Spec: {engineering_spec_content}
#     ## Red Team Review: {redteam_content}
#     ## Tasks: 1) Compile frozen plan 2) Stop/Pivot checkpoints 3) Versioning rules
#     4) Reference Killer Prior Check
#     ## Output: THREE documents with YAML front-matter and delimiters
#     """
#     return prompt


# Step 2.0: Figure/Table List — ChatGPT (v4.0 addition, retained in v7)
def render_step_2_0_prompt(frozen_claims_content: str, target_venue: str) -> str:
    """
    渲染 Step 2.0 Prompt: Figure/Table List (ChatGPT)
    Not a separate v7 SOP step, but useful pre-proposal planning.

    Args:
        frozen_claims_content: Frozen Claims 内容
        target_venue: 目标期刊

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the PI.

## Task
Before writing the full proposal, create a comprehensive Figure/Table List.

## Input
- `01_Claims_and_NonClaims.md` (frozen) — attached below.
- Target Venue: {target_venue}

## Frozen Claims and NonClaims:
{frozen_claims_content}

## Actions (complete all four)

### 1. Figure/Table List (<=8 total)
For each figure/table:
- ID (e.g., Fig1, Table1)
- Title/Caption (draft)
- Purpose: Which claim(s) does it support?
- Content: What will be shown? (axes, metrics, comparisons)
- Acceptance criteria: What pattern/result would make this figure "successful"?

### 2. Claim-to-Evidence Map
For each claim, list which figure(s)/table(s) provide evidence.
Ensure every claim has at least one figure/table.

### 3. Priority
- CRITICAL (must-have for main claims)
- SUPPORTING (nice-to-have for robustness)

### 4. Venue-Specific Guidance
- Figure style {target_venue} prefers
- Caption detail level
- Specific requirements (error bars, statistical tests, etc.)

## Output Format
File: `02_Figure_Table_List.md`

Begin with YAML front-matter:
```yaml
---
doc_type: FigureTableList
version: "0.1"
status: draft
created_by: ChatGPT
target_venue: "{target_venue}"
gate_relevance: Gate2
---
```

Then provide sections A) Figure/Table List, B) Claim-to-Evidence Map, C) Venue-Specific Notes.
"""

    return prompt


# v7 SOP 6.13 [S6b] Patch Review — ChatGPT
def render_step_2_4b_prompt(redteam_content: str, full_proposal_content: str,
                            engineering_spec_content: str) -> str:
    """
    渲染 Step 2.4b Prompt: Patch Review (ChatGPT)
    v7 SOP 6.13 — Architect / Planner role

    Args:
        redteam_content: Red Team Review 内容
        full_proposal_content: Full Proposal 内容
        engineering_spec_content: Engineering Spec 内容

    Returns:
        str: 渲染后的 prompt
    """
    prompt = f"""You are the Architect / Planner.

## Task
Review Red Team patches. Accept or reject each one.

## Input
- `03_RedTeam_Reviewer2.md` — attached below.

## Red Team Review (with minimal patch set):
{redteam_content}

## Current Full Proposal:
{full_proposal_content}

## Current Engineering Spec:
{engineering_spec_content}

## Actions

### For Each Fatal Issue + Patch:
- Verdict: ACCEPT / REJECT
- Reason (1-2 sentences)
- If ACCEPT: what evidence is needed to verify the patch was applied correctly

### For Each Accepted Patch:
- Write the specific change to be made to the target artifact
- Note if the change introduces new assumptions or new baselines (triggers Gate 2 re-run)

## Output Format
Two files:

---DOCUMENT_1: 03_Patch_Review.md---
```yaml
---
doc_type: PatchReview
version: "0.1"
status: draft
created_by: ChatGPT
gate_relevance: Gate2
---
```
[Accept/Reject verdicts for each patch with reasons]
---END_DOCUMENT_1---

---DOCUMENT_2: 03_Patch_Diff.md---
```yaml
---
doc_type: PatchDiff
version: "0.1"
status: draft
created_by: ChatGPT
gate_relevance: Gate2
---
```
[Only accepted patches, in diff format — specific changes to proposal and engineering spec]
---END_DOCUMENT_2---
"""

    return prompt


# ============================================================
# LEGACY: Step 2.4b Prompt (SOP v4.0) — 保留用于对比
# ============================================================
# def render_step_2_4b_prompt_v4_legacy(redteam_content, full_proposal_content,
#                             engineering_spec_content):
#     prompt = f"""You are the PI. Apply the Red Team patches to the proposal and engineering spec.
#     ## Red Team Review: {redteam_content}
#     ## Current Full Proposal: {full_proposal_content}
#     ## Current Engineering Spec: {engineering_spec_content}
#     ## Tasks: 1) Extract Patch Items 2) Apply Patches 3) Verify Coverage 4) Update Checklist
#     ## Output: 03_Patch_Diff.md with YAML front-matter
#     """
#     return prompt

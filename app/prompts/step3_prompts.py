"""
Step 3 Prompt 模板
Research Execution 阶段的 AI 提示词

Step 3 使用 WP-based DAG 执行引擎，每个 WP 包含多个 subtask。
"""


def render_wp_init_prompt(plan_frozen_content: str, execution_order_content: str = "") -> str:
    """
    E0: 解析 PlanFrozen → WP DAG

    Args:
        plan_frozen_content: 04_Research_Plan_FROZEN.md 内容
        execution_order_content: 04_Execution_Order.md 内容（可选）

    Returns:
        str: prompt
    """
    context = f"""
## Execution Order (if available)
{execution_order_content if execution_order_content else "Not available - derive from Plan Frozen."}
"""

    return f"""You are a Research Project Manager (PI role). Your task is to decompose the frozen research plan into executable Work Packages (WPs) with a dependency DAG.

## Input: Frozen Research Plan
{plan_frozen_content}

{context}

## Task
Analyze the frozen research plan and produce a structured WP Registry in the following YAML format:

```yaml
work_packages:
  - wp_id: "wp1"
    name: "<descriptive name>"
    owner: "chatgpt"  # or "gemini"
    reviewer: "gemini"  # or "chatgpt" (must differ from owner)
    depends_on: []  # list of wp_ids this WP depends on
    gate_criteria:
      - "<criterion 1>"
      - "<criterion 2>"
    subtasks:
      - subtask_id: "wp1_st1"
        objective: "<what this subtask should accomplish>"
        inputs: ["<input artifact paths>"]
        outputs: ["<output artifact paths>"]
        acceptance_criteria:
          - "<criterion>"
        allowed_paths: ["<glob patterns for allowed file modifications>"]
        forbidden_paths: ["<glob patterns for forbidden modifications>"]
```

## Guidelines
1. Each WP should represent a coherent unit of work (e.g., one experiment, one analysis, one component)
2. WP dependencies should form a DAG (no cycles)
3. Owner and reviewer should be different AI models
4. Subtasks within a WP are executed sequentially
5. Gate criteria should be specific and verifiable
6. Keep WP count between 3-8 for manageability
7. Map claims to WPs - each claim should be covered by at least one WP
8. Include allowed_paths and forbidden_paths for artifact boundary control

## Output
Return ONLY the YAML content (no markdown code fences), starting with `work_packages:`.
"""


def render_execute_prompt(
    wp_spec_yaml: str,
    subtask_spec_yaml: str,
    context_artifacts: str = "",
    previous_results: str = "",
    memory_lessons: str = "",
    wp_id: str = "",
    subtask_id: str = "",
    owner_model: str = "",
    token_budget_hint: str = "",
) -> str:
    """
    E1→E2: 执行单个 subtask (v1.2 §6.2 EXECUTE)

    Args:
        wp_spec_yaml: WP 规格 YAML
        subtask_spec_yaml: Subtask 规格 YAML
        context_artifacts: 上下文 artifact 内容
        previous_results: 同 WP 中之前 subtask 的结果
        memory_lessons: MEMORY.md 相关教训 (v1.2 §6.2)
        wp_id: WP ID (v1.2 §6.2)
        subtask_id: Subtask ID (v1.2 §6.2)
        owner_model: 执行模型名称 (v1.2 §6.2)
        token_budget_hint: Token 预算提示 (v1.2 §6.2)

    Returns:
        str: prompt
    """
    memory_section = ""
    if memory_lessons:
        memory_section = f"""
## MEMORY.md 相关教训
{memory_lessons}
"""

    token_budget_section = ""
    if token_budget_hint:
        token_budget_section = f"""
## Token Budget Hint
{token_budget_hint}
"""

    return f"""# Task: {wp_id} / {subtask_id}
# Model: {owner_model}

You are a Research Execution Agent. Execute the following subtask precisely.

## Work Package Context
{wp_spec_yaml}

## Current Subtask
{subtask_spec_yaml}

## Context Artifacts
{context_artifacts if context_artifacts else "No additional context."}

## Previous Subtask Results (same WP)
{previous_results if previous_results else "This is the first subtask."}
{memory_section}
## Acceptance Criteria
- [ ] Execute the subtask objective completely
- [ ] Produce all specified outputs
- [ ] Stay within allowed_paths — do NOT modify files outside the boundary
- [ ] Report what changed, metrics, and any open issues
- [ ] All artifacts written to correct paths
- [ ] Session log updated with key decisions

## Constraints
- **allowed_paths**: Only modify files matching the subtask's allowed_paths globs
- **forbidden_paths**: Do NOT touch any files matching the subtask's forbidden_paths globs
- **越界警告**: Any write outside allowed_paths will trigger a boundary violation and FAIL the subtask
- **session log**: Log key decisions and rationale to the session log for auditability
{token_budget_section}
## Output Format
Produce your response in the following structure:

### Summary
<Brief summary of what was accomplished>

### Output Content
<The actual deliverable content for this subtask>

### Metrics
<Key metrics, measurements, or results>

### Open Issues
<Any unresolved issues or concerns, or "None">

### Artifacts Written
<List of artifact paths that were created/modified>
"""


def render_review_acceptance_prompt(
    wp_spec_yaml: str,
    subtask_results_summary: str,
    gate_criteria: str
) -> str:
    """
    E3: WP 验收 review

    Args:
        wp_spec_yaml: WP 规格 YAML
        subtask_results_summary: 所有 subtask 结果摘要
        gate_criteria: WP 验收标准

    Returns:
        str: prompt
    """
    return f"""You are a Research Reviewer (Reviewer #2 role). Review the completed Work Package and determine if it meets the acceptance criteria.

## Work Package Specification
{wp_spec_yaml}

## Subtask Results
{subtask_results_summary}

## Gate Criteria
{gate_criteria}

## Review Instructions
1. Check each gate criterion against the subtask results
2. Verify completeness and quality of outputs
3. Identify any gaps, errors, or concerns
4. Provide a clear PASS/FAIL verdict

## Output Format
Return ONLY valid JSON matching this schema:
```json
{{
  "verdict": "PASS or FAIL",
  "criteria": [
    {{
      "id": "gc1",
      "name": "<criterion text>",
      "result": "PASS or FAIL",
      "evidence": "<specific evidence from subtask results>"
    }}
  ],
  "critical_issues": [
    {{
      "issue": "<description>",
      "file": "<affected file path>",
      "line": "<line number or range, if applicable>",
      "suggested_fix": "<concrete fix suggestion>"
    }}
  ]
}}
```

## 禁止事项
- 不要给建议改进 — 只判断是否满足验收标准
- 不要评论代码风格或格式偏好
- 不要提出新的要求（超出 Gate Criteria 范围的）
- PASS 时不要附加"但是…"或"建议…"
- critical_issues 最多 3 个 — 聚焦最关键的问题
- 没有"部分通过" — 只有 PASS 或 FAIL

Return ONLY the JSON content (no markdown code fences).
"""


def render_review_fix_prompt(
    wp_spec_yaml: str,
    review_issues: str,
    allowed_paths: str,
    previous_output: str,
    memory_lessons: str = "",
    wp_id: str = "",
    iteration_count: int = 1,
    forbidden_paths: str = "",
) -> str:
    """
    E4: Review-Fix 循环 — 修复 reviewer 指出的问题 (v1.2 §6.4)

    Args:
        wp_spec_yaml: WP 规格 YAML
        review_issues: Reviewer 指出的问题
        allowed_paths: 允许修改的路径
        previous_output: 之前的输出内容
        memory_lessons: MEMORY.md 相关教训 (v1.2 §6.2)
        wp_id: WP ID (v1.2 §6.4)
        iteration_count: 当前迭代次数 (v1.2 §6.4)
        forbidden_paths: 禁止修改的路径 (v1.2 §6.4)

    Returns:
        str: prompt
    """
    memory_section = ""
    if memory_lessons:
        memory_section = f"""
## MEMORY.md 相关教训
{memory_lessons}
"""

    forbidden_section = ""
    if forbidden_paths:
        forbidden_section = f"\n- **forbidden_paths**: {forbidden_paths}"

    return f"""# Fix: {wp_id} — Iteration {iteration_count}/2

You are a Research Execution Agent. The reviewer has identified issues with your previous work. Fix them.

## Work Package
{wp_spec_yaml}

## Reviewer Issues
{review_issues}

## Constraints
- **allowed_paths**: {allowed_paths}{forbidden_section}

## Previous Output
{previous_output}
{memory_section}
## Instructions
1. Address each reviewer issue
2. Stay within allowed paths
3. Explain what was changed and why

## 禁止事项
- 不要重构 — 只修复 reviewer 列出的问题
- 不要修复未列出的问题 — 即使你发现了其他 bug
- 如果不同意 reviewer 的 suggested_fix，必须说明理由并提供替代方案

## Output Format
### Fixes Applied
<Description of each fix>

### Updated Content
<The corrected deliverable content>

### Remaining Issues
<Any issues that could not be resolved, or "None">
"""


def render_diagnose_prompt(
    wp_spec_yaml: str,
    iteration_history: str,
    gate_failures: str,
    agents_md_dynamic: str = "",
    memory_lessons: str = "",
) -> str:
    """
    E5: 升级链诊断 — Gemini 分析反复失败的原因 (v1.2 §6.5 DIAGNOSE)

    Args:
        wp_spec_yaml: WP 规格 YAML
        iteration_history: 迭代历史
        gate_failures: Gate 失败记录
        agents_md_dynamic: AGENTS.md 动态 section (v1.2 §6.5)
        memory_lessons: MEMORY.md 相关教训 (v1.2 §6.5)

    Returns:
        str: prompt
    """
    agents_section = ""
    if agents_md_dynamic:
        agents_section = f"""
## AGENTS.md Dynamic Section
{agents_md_dynamic}
"""

    memory_section = ""
    if memory_lessons:
        memory_section = f"""
## MEMORY.md 相关教训
{memory_lessons}
"""

    return f"""You are a Senior Research Advisor (Intelligence Officer role). A Work Package has failed multiple review iterations. Diagnose the root cause and recommend next steps.

## Work Package
{wp_spec_yaml}

## Iteration History
{iteration_history}

## Gate Failures
{gate_failures}
{agents_section}{memory_section}
## Diagnosis Instructions
1. Identify the root cause of repeated failures
2. Determine if the issue is:
   a) Technical (fixable with different approach)
   b) Scope (WP spec needs revision)
   c) Fundamental (requires human intervention)
3. Recommend specific next steps

## Output Format
Return ONLY valid JSON matching this schema:
```json
{{
  "hypotheses": [
    {{
      "description": "<root cause hypothesis>",
      "confidence": 0.8,
      "verification_steps": ["<step to verify this hypothesis>"],
      "expected_outcome_if_correct": "<what we'd see if this is the cause>"
    }}
  ],
  "recommended_action": "<specific next action to take>",
  "files_to_examine": ["<file paths that need inspection>"]
}}
```

## 禁止事项
- 不要猜测 — 每个假设必须有可验证的 verification_steps
- 不要建议"从头重做" — 聚焦增量修复
- 不要忽略 MEMORY.md 中的历史教训 — 避免重复犯错
- 不要同时给出超过 3 个假设 — 聚焦最可能的原因

Return ONLY the JSON content (no markdown code fences).
"""


def render_session_resume_prompt(
    project_summary: str = "",
    agents_md_dynamic: str = "",
    memory_lessons: str = "",
    last_subtask_result: str = "",
    last_wrapup: str = "",
    current_subtask_yaml: str = "",
) -> str:
    """
    v1.2 §8.3: Session Resume prompt — 断点续跑时替代普通 execute prompt

    Args:
        project_summary: 项目状态摘要 (from state.json)
        agents_md_dynamic: AGENTS.md 动态 section
        memory_lessons: MEMORY.md 相关条目
        last_subtask_result: 上一个 subtask 的 what_changed + metrics + open_issues
        last_wrapup: 上一个 session 的 wrap-up
        current_subtask_yaml: 当前 subtask 目标 + allowed_paths/forbidden_paths

    Returns:
        str: prompt
    """
    return f"""You are a Research Execution Agent resuming a previously interrupted session.

## Project Status Summary
{project_summary if project_summary else "No project summary available."}

## AGENTS.md Dynamic Section
{agents_md_dynamic if agents_md_dynamic else "No AGENTS.md dynamic section available."}

## MEMORY.md Lessons
{memory_lessons if memory_lessons else "No lessons recorded yet."}

## Last Subtask Result
{last_subtask_result if last_subtask_result else "No previous subtask result."}

## Previous Session Wrap-up
{last_wrapup if last_wrapup else "No previous session wrap-up."}

## Current Subtask to Execute
{current_subtask_yaml if current_subtask_yaml else "No subtask specified."}

## Instructions
1. Review the project context and previous session state
2. Continue from where the last session left off
3. Execute the current subtask objective completely
4. Stay within allowed_paths - do NOT modify files outside the boundary
5. Address any open issues from the previous session if relevant

## Output Format
### Summary
<Brief summary of what was accomplished>

### Output Content
<The actual deliverable content for this subtask>

### Metrics
<Key metrics, measurements, or results>

### Open Issues
<Any unresolved issues or concerns, or "None">

### Artifacts Written
<List of artifact paths that were created/modified>
"""


# v7.1 S2-1: Pre-flight parameter declaration prompt
PREFLIGHT_PARAMETER_DECLARATION_PROMPT = """You are a parameter auditor for a research execution subtask.

## Subtask Specification
{subtask_spec}

## Context
{context}

## Task
Extract ALL parameters (hyperparameters, thresholds, dataset sizes, model configs, etc.) used in this subtask.

For each parameter, declare:
- name: parameter name
- value: the value being used
- source: one of [from_spec, from_reference, default, computed]
  - from_spec: value comes from the frozen research plan / engineering spec
  - from_reference: value comes from a cited paper
  - default: using a default value (library default, common practice, etc.)
  - computed: value is computed from other parameters or data
- justification: why this value is appropriate (1 sentence)

## Output Format (one per line)
- param_name = value (source: source_type, justification: reason)

Example:
- learning_rate = 0.001 (source: from_reference, justification: Following Smith et al. 2023 baseline)
- batch_size = 64 (source: default, justification: Standard default for this model size)
- num_epochs = 100 (source: from_spec, justification: Specified in Engineering Spec §3.2)

List ALL parameters. Do not omit any.
"""


# v7.1 S2-3: Enhanced RA Assessment Prompt
RA_ASSESSMENT_PROMPT = """# Readiness Assessment: {wp_id}
# Model: ChatGPT (PI / Strategic Reviewer)

## 你的角色
你是 ChatGPT，担任战略层审批官。Gate（机械验证）已通过。你现在判断：
1. 物理上对吗？覆盖了关键 case 吗？
2. 对北极星的推进够吗？有没有遗漏？
3. 下一个 WP 是否可以安全开始？

## WP 信息
- WP ID: {wp_id}
- WP Name: {wp_name}
- Owner: {wp_owner}
- Subtasks completed: {subtasks_completed}

## Gate 结果摘要
{gate_results}

## Artifacts 摘要
{artifacts_summary}

## 项目教训（来自 MEMORY.md）
{memory_lessons}

## 你的输出格式（必须严格遵守）
```json
{{
  "verdict": "ADVANCE | POLISH | BLOCK",
  "reasoning": "简述判断依据（<= 200 words）",
  "north_star_alignment": "当前产出对北极星的贡献（1-2 句）",
  "missing_pieces": ["如果 BLOCK，列出缺什么"],
  "polish_suggestions": ["如果 POLISH，列出可改进点（不阻断推进）"],
  "next_wp_readiness": "下一个 WP 是否可以开始？依赖是否满足？"
}}
```

## 判断标准
- **ADVANCE**：物理正确、覆盖充分、可安全推进
- **POLISH**：物理正确但有改进空间，可推进但标记 TODO
- **BLOCK**：存在物理错误/关键遗漏/北极星偏离，需要返工

## 禁止事项
- 不要给打分（我们用 binary 判断）
- 不要重复 Gate 已检查的机械项
- 聚焦战略层面：物理正确性、覆盖度、北极星对齐
"""

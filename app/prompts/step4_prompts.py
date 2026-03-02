"""
Step 4 Prompt 模板
Convergence & Delivery 阶段的 AI 提示词
"""


def render_collect_prompt(frozen_artifacts_summary: str, wp_registry: str) -> str:
    """
    D0: 收集冻结 artifacts → delivery manifest

    Args:
        frozen_artifacts_summary: 冻结 artifact 摘要
        wp_registry: WP 注册表内容

    Returns:
        str: prompt
    """
    return f"""You are a Research Delivery Manager. Collect all frozen artifacts from completed Work Packages and create a delivery manifest.

## Frozen Artifacts
{frozen_artifacts_summary}

## WP Registry
{wp_registry}

## Task
Create a Delivery Manifest that:
1. Lists all frozen artifacts organized by WP
2. Maps each artifact to the claims it supports
3. Identifies the claim-evidence chain
4. Notes any gaps or missing deliverables

## Output Format
# Delivery Manifest

## Artifact Inventory
| WP | Artifact | Type | Claims Supported | Status |
|----|----------|------|-----------------|--------|
| ... | ... | ... | ... | Frozen |

## Claim-Evidence Map
- Claim 1: [artifact1, artifact2]
- Claim 2: [artifact3]

## Gaps & Missing Items
- <any gaps or missing deliverables>

## Delivery Readiness
- Total artifacts: N
- All claims covered: Yes/No
- Ready for assembly: Yes/No
"""


def render_assembly_kit_prompt(
    delivery_manifest: str,
    frozen_artifacts: str,
    claim_evidence_map: str = "",
    iteration_history: str = "",
) -> str:
    """
    D2: 生成 Assembly Kit (v1.2 §6.7 ASSEMBLY_KIT)

    Args:
        delivery_manifest: 交付清单
        frozen_artifacts: 冻结 artifact 内容
        claim_evidence_map: Claim-Evidence 映射
        iteration_history: 过程日志 (v1.2 §6.7)

    Returns:
        str: prompt
    """
    process_log_section = ""
    if iteration_history:
        process_log_section = f"""
## Process Logs
{iteration_history}
"""

    return f"""You are a Research Paper Assembly Specialist. Create an Assembly Kit that organizes all research outputs for paper writing.

## Delivery Manifest
{delivery_manifest}

## Frozen Artifacts
{frozen_artifacts}

## Claim-Evidence Map
{claim_evidence_map if claim_evidence_map else "Derive from manifest."}
{process_log_section}
## Task
Create an Assembly Kit that produces the following 6 required output files:

## Required Outputs
1. `assembly_kit/outline.md` — Paper structure outline with section→artifact mapping
2. `assembly_kit/figure_table_plan.md` — Figure/table placement plan with descriptions and source WPs
3. `assembly_kit/citation_map.md` — Reference integration points and citation key mapping
4. `assembly_kit/claim_evidence_matrix.md` — Claim-to-evidence traceability matrix
5. `assembly_kit/writing_guide.md` — Per-section writing guidance and notes
6. `assembly_kit/refs.bib` — Consolidated BibTeX reference file

## 你不做什么
- 不产生新结论 — 只整理已有 frozen artifacts 中的内容
- 不引入新引用 — 只使用 frozen artifacts 中已有的 references
- 不添加新数据 — 所有数据必须可追溯到 frozen artifacts

## 约束
- 所有 citation key 必须存在于 refs.bib 中
- 每个 claim 必须映射到至少一个 frozen artifact
- Figure/table 编号必须与 frozen artifacts 中的编号一致
- outline.md 中的每个 section 必须标注对应的 artifact 来源

## Output Format
Produce all 6 files listed above. For each file, use the following delimiter:

--- FILE: <path> ---
<content>
--- END FILE ---
"""


def render_figure_gen_prompt(
    figure_id: str,
    journal_spec: str = "",
    figure_spec: str = "",
    data_file_path: str = "",
    acceptance_criteria: str = "",
) -> str:
    """
    D1.5: Figure Generation (v1.2 §6.6 FIGURE_GEN)

    Args:
        figure_id: 图表 ID (e.g. "fig1", "fig2a")
        journal_spec: 期刊格式要求 (DPI/字体/尺寸/格式)
        figure_spec: 图表规格描述 (类型、数据、标注等)
        data_file_path: 数据文件路径
        acceptance_criteria: 验收标准

    Returns:
        str: prompt
    """
    journal_section = ""
    if journal_spec:
        journal_section = f"""
## Journal Format Requirements
{journal_spec}
"""
    else:
        journal_section = """
## Journal Format Requirements
- DPI: >= 300 (print), >= 150 (web)
- Font: Arial or Helvetica, >= 8pt
- Size: single column (3.3 in / 84 mm) or double column (6.7 in / 170 mm)
- Format: PDF (vector) or TIFF (raster)
- Color: CMYK for print, RGB for web
"""

    criteria_section = ""
    if acceptance_criteria:
        criteria_section = f"""
## Acceptance Criteria
{acceptance_criteria}
"""
    else:
        criteria_section = """
## Acceptance Criteria
- [ ] Figure matches the specification description
- [ ] All data points are accurately represented
- [ ] Axes labels, legends, and titles are clear and complete
- [ ] Meets journal DPI/font/size requirements
- [ ] Color scheme is accessible (colorblind-friendly)
- [ ] Generation code is reproducible (no random seeds without fixing)
"""

    return f"""# Figure Generation: {figure_id}

You are a Scientific Figure Generation Specialist. Generate a publication-quality figure.

## Figure ID
{figure_id}

## Figure Specification
{figure_spec if figure_spec else "No specification provided — use best judgment based on data."}

## Data Source
{data_file_path if data_file_path else "Data will be provided inline or is already available in the project."}
{journal_section}{criteria_section}
## Required Outputs
1. The figure file: `figures/{figure_id}.pdf` (vector) or `figures/{figure_id}.tiff` (raster)
2. The generation code: `figures/code/{figure_id}_gen.py`

## Output Format
Produce the generation code that, when executed, creates the figure file.

### Generation Code
```python
# figures/code/{figure_id}_gen.py
<complete, self-contained Python script that generates the figure>
```

### Figure Description
<Brief description of what the figure shows, suitable for a figure caption>

### Verification Notes
<How to verify the figure meets acceptance criteria>
"""


def render_citation_qa_prompt(assembly_content: str, evidence_refs: str) -> str:
    """
    D3: 引用完整性检查

    Args:
        assembly_content: Assembly Kit 内容
        evidence_refs: 证据引用列表

    Returns:
        str: prompt
    """
    return f"""You are a Citation Quality Assurance Specialist. Check the citation integrity of the assembly kit.

## Assembly Kit Content
{assembly_content}

## Evidence References
{evidence_refs}

## Task
Perform a citation QA check:
1. Verify every claim has supporting evidence cited
2. Check for orphan references (cited but not in evidence)
3. Check for uncited evidence (in evidence but not cited)
4. Verify citation format consistency
5. Flag any potential self-plagiarism or attribution issues

## Output Format
# Citation QA Report

## Summary
- Total claims: N
- Claims with citations: N
- Orphan references: N
- Uncited evidence: N

## Issues Found
| # | Type | Description | Severity | Location |
|---|------|-------------|----------|----------|

## Recommendations
- [specific fixes needed]

## Verdict
- Citation QA: PASS/FAIL
- Confidence: 0.X
"""


def render_repro_check_prompt(manifest_summary: str, verification_results: str) -> str:
    """
    D4: Reproducibility Check — artifact 完整性验证 (v1.2 §4.3)

    Args:
        manifest_summary: FROZEN_MANIFEST 摘要
        verification_results: SHA256 验证结果

    Returns:
        str: prompt
    """
    return f"""You are a Reproducibility Verification Specialist. Verify the integrity of all frozen artifacts.

## FROZEN_MANIFEST Summary
{manifest_summary}

## Verification Results (SHA256 checks)
{verification_results}

## Task
Analyze the verification results and produce a reproducibility report:
1. Summarize which artifacts passed/failed integrity checks
2. Identify any missing or corrupted artifacts
3. Assess overall reproducibility readiness
4. Recommend fixes for any failures

## Output Format
# Reproducibility Check Report

## Summary
- Total artifacts checked: N
- Passed: N
- Failed: N

## Verification Details
| Artifact | WP | SHA256 Match | Status |
|----------|-----|-------------|--------|

## Issues Found
- [list any integrity failures or missing files]

## Verdict
- Reproducibility Check: PASS/FAIL
- Confidence: 0.X

## Recommendations
- [specific fixes if any failures found]
"""


def render_package_prompt(manifest: str, assembly_kit: str, citation_report: str) -> str:
    """
    D5: 按 delivery_profile 打包

    Args:
        manifest: 交付清单
        assembly_kit: Assembly Kit 内容
        citation_report: Citation QA 报告

    Returns:
        str: prompt
    """
    return f"""You are a Research Delivery Packager. Create the final delivery package.

## Delivery Manifest
{manifest}

## Assembly Kit
{assembly_kit}

## Citation QA Report
{citation_report}

## Task
Create a final delivery package summary:
1. Verify all components are present
2. Create a table of contents
3. Generate a delivery checklist
4. Provide final quality assessment

## Output Format
# Delivery Package

## Table of Contents
1. [list all deliverables]

## Delivery Checklist
- [ ] All WP artifacts frozen
- [ ] Assembly kit complete
- [ ] Citation QA passed
- [ ] All claims supported
- [ ] Figures/tables ready

## Quality Assessment
- Overall readiness: X/10
- Key strengths: [list]
- Remaining risks: [list]

## Next Steps
- [recommended actions for paper writing]
"""


def render_paper_draft_prompt(
    delivery_manifest: str,
    frozen_artifacts: str,
    claim_evidence_map: str = ""
) -> str:
    """
    D2 (internal_draft): 生成论文初稿

    Args:
        delivery_manifest: 交付清单
        frozen_artifacts: 冻结 artifact 内容
        claim_evidence_map: Claim-Evidence 映射

    Returns:
        str: prompt
    """
    return f"""You are a Research Paper Draft Writer. Create an internal paper draft from the frozen artifacts.

NOTE: This is an internal draft for author review — NOT a submission-ready manuscript.
All sections must be marked "需作者复核" (requires author review).

## Delivery Manifest
{delivery_manifest}

## Frozen Artifacts
{frozen_artifacts}

## Claim-Evidence Map
{claim_evidence_map if claim_evidence_map else "Derive from manifest."}

## Task
Create a paper draft that:
1. Organizes content into standard paper sections
2. Integrates evidence from frozen artifacts
3. Marks every section with "需作者复核"
4. Leaves placeholders for author-specific content

## Output Format
# Paper Draft (Internal — 需作者复核)

## Abstract
[Draft abstract — 需作者复核]

## 1. Introduction
[Draft introduction — 需作者复核]

## 2. Methods
[Draft methods — 需作者复核]

## 3. Results
[Draft results with figure/table references — 需作者复核]

## 4. Discussion
[Draft discussion — 需作者复核]

## 5. Conclusion
[Draft conclusion — 需作者复核]

## References
[Reference list — 需作者复核]
"""

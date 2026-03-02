"""
Gate Rules Exporter — exports gate checklist definitions as YAML files
to gates/rules/ for audit and documentation (SOP v7 Appendix B).
"""
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.models.gate import (
    GateType,
    Gate0Checklist,
    Gate1Checklist,
    Gate1_5Checklist,
    Gate1_25Checklist,
    Gate1_6Checklist,
    Gate2Checklist,
    WPGateChecklist,
    FreezeGateChecklist,
    DeliveryGateChecklist,
)

logger = logging.getLogger(__name__)

# Gate metadata: description + check items extracted from Checklist field definitions
GATE_DEFINITIONS = {
    GateType.GATE_0: {
        "description": "Project intake ready — venue, DoD, and hard constraints defined",
        "checklist_class": Gate0Checklist,
        "check_items": [
            {"name": "venue_specified", "description": "目标期刊是否指定", "threshold": "True"},
            {"name": "dod_count", "description": "Definition of Done 至少 3 项", "threshold": ">= 3"},
            {"name": "hard_constraints_count", "description": "硬约束至少 3 项", "threshold": ">= 3"},
        ],
    },
    GateType.GATE_1: {
        "description": "Topic candidate selected — top-1 topic, backup, draft claims, non-claims, minimal figure set",
        "checklist_class": Gate1Checklist,
        "check_items": [
            {"name": "top1_selected", "description": "Top-1 选题已选定", "threshold": "True"},
            {"name": "backup_defined", "description": "备选方案已定义", "threshold": "True"},
            {"name": "draft_claims_exist", "description": "Draft Claims 已存在", "threshold": "True"},
            {"name": "non_claims_exist", "description": "Non-Claims 已存在", "threshold": "True"},
            {"name": "figure_count", "description": "最小图表集不超过 4 个", "threshold": "1-4"},
        ],
    },
    GateType.GATE_1_25: {
        "description": "Topic Alignment Check — validates topic alignment with venue and constraints",
        "checklist_class": Gate1_25Checklist,
        "check_items": [
            {"name": "north_star_covered", "description": "选题覆盖北极星问题", "threshold": "True"},
            {"name": "core_keywords_present", "description": "核心关键词出现 3-5 个", "threshold": "3-5"},
            {"name": "scope_boundaries_clear", "description": "范围边界在 Non-Claims 中明确", "threshold": "True"},
            {"name": "keyword_match_score", "description": "关键词匹配分数", "threshold": ">= 0.7"},
        ],
    },
    GateType.GATE_1_5: {
        "description": "Killer Prior Check — MANDATORY, prevents wasted effort on already-published topics",
        "checklist_class": Gate1_5Checklist,
        "check_items": [
            {"name": "verdict_is_pass", "description": "Killer Prior Check 判定为 PASS", "threshold": "True"},
            {"name": "direct_collision_count", "description": "无直接冲突的文献", "threshold": "== 0"},
            {"name": "differentiator_clear", "description": "差异化点清晰可辩护", "threshold": "True"},
        ],
    },
    GateType.GATE_1_6: {
        "description": "Reference QA Check — validates DOI quality and literature completeness",
        "checklist_class": Gate1_6Checklist,
        "check_items": [
            {"name": "literature_count", "description": "文献矩阵至少 20 篇 (Required)", "threshold": ">= 20"},
            {"name": "doi_parseability", "description": "DOI 可解析率", "threshold": ">= 0.80"},
            {"name": "top5_manually_verified", "description": "Top 5 手动验证 (Optional)", "threshold": "True (optional)"},
            {"name": "duplicate_count", "description": "无重复文献 (Required)", "threshold": "== 0"},
            {"name": "invalid_doi_count", "description": "无效 DOI 数量", "threshold": "<= 3"},
        ],
        "rigor_notes": "Required items must all pass + at least 1 core item must pass",
    },
    GateType.GATE_2: {
        "description": "Plan freeze — proposal, engineering spec, evaluation plan complete with consistency validation",
        "checklist_class": Gate2Checklist,
        "check_items": [
            {"name": "claims_mapped", "description": "每个 Claim 映射到 figure/table/test", "threshold": "True"},
            {"name": "modules_have_io", "description": "Engineering spec modules 有 I/O + verification", "threshold": "True"},
            {"name": "baseline_frozen", "description": "Baseline 已冻结", "threshold": "True"},
            {"name": "ablation_frozen", "description": "Ablation 已冻结", "threshold": "True"},
            {"name": "robustness_frozen", "description": "Robustness 已冻结", "threshold": "True"},
            {"name": "pivot_checkpoints_exist", "description": "Stop/Pivot checkpoints 已存在", "threshold": "True"},
            {"name": "killer_prior_referenced", "description": "Killer Prior PASS 已被引用", "threshold": "True"},
        ],
    },
    GateType.GATE_WP: {
        "description": "WP acceptance gate — all subtasks completed, criteria met, boundary check, review approved",
        "checklist_class": WPGateChecklist,
        "check_items": [
            {"name": "all_subtasks_completed", "description": "所有 subtask 已完成", "threshold": "True"},
            {"name": "gate_criteria_met", "description": "WP 验收标准已满足", "threshold": "True"},
            {"name": "boundary_check_passed", "description": "Artifact 边界检查通过", "threshold": "True"},
            {"name": "review_approved", "description": "Reviewer 已批准", "threshold": "True"},
        ],
    },
    GateType.GATE_FREEZE: {
        "description": "WP freeze gate — WP gate passed, artifacts committed, no open issues",
        "checklist_class": FreezeGateChecklist,
        "check_items": [
            {"name": "wp_gate_passed", "description": "WP 验收门禁已通过", "threshold": "True"},
            {"name": "artifacts_committed", "description": "Artifacts 已提交到 Git", "threshold": "True"},
            {"name": "no_open_issues", "description": "无未解决问题", "threshold": "True"},
        ],
    },
    GateType.GATE_DELIVERY: {
        "description": "Delivery gate — v1.2 §9.3 D1-D8",
        "checklist_class": DeliveryGateChecklist,
        "check_items": [
            {"name": "all_wps_frozen", "description": "D1: 所有 WP status=frozen", "threshold": "True"},
            {"name": "all_figures_approved", "description": "D2: 图表 human_approved + 生成代码可运行", "threshold": "True"},
            {"name": "assembly_complete", "description": "D3: 按 delivery_profile 应有文件齐全", "threshold": "True"},
            {"name": "repro_check_pass", "description": "D4: repro_check.json verdict=PASS", "threshold": "True"},
            {"name": "deliverables_complete", "description": "D5: manifest vs PlanFrozen match", "threshold": "True"},
            {"name": "checksums_valid", "description": "D6: checksum 验证通过", "threshold": "True"},
            {"name": "citations_verified", "description": "D7: citation_report.json PASS + missing_keys=[]", "threshold": "True"},
            {"name": "no_forbidden_output", "description": "D8: 无违规输出", "threshold": "True"},
        ],
    },
}


def export_gate_rules(project_id: str, file_manager) -> list[str]:
    """
    Export all gate rule definitions as YAML files to gates/rules/.

    Args:
        project_id: Project ID
        file_manager: FileManager instance

    Returns:
        List of written file paths (relative)
    """
    gates_path = file_manager.get_gates_path(project_id) / "rules"
    gates_path.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    for gate_type, definition in GATE_DEFINITIONS.items():
        gate_data = {
            "gate_type": gate_type.value,
            "description": definition["description"],
            "check_items": definition["check_items"],
        }
        if "rigor_notes" in definition:
            gate_data["rigor_notes"] = definition["rigor_notes"]

        filename = f"{gate_type.value}.yaml"
        filepath = gates_path / filename

        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(gate_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        written.append(str(filepath))

    logger.info(f"Exported {len(written)} gate rule files for project {project_id}")
    return written

"""
Rigor Profile 数据模型

定义研究强度档位和对应的 Gate 阈值调整规则

v6.0 NEW: Rigor Profile 系统
- Top-Journal: 严格模式，所有 gates 必须通过，高标准
- Fast-Track: 快速模式，部分 gates 可以跳过或降低标准
"""
from pydantic import BaseModel, Field
from typing import Dict, Optional, List
from enum import Enum


class RigorLevel(str, Enum):
    """研究强度档位"""
    TOP_JOURNAL = "top_journal"
    FAST_TRACK = "fast_track"
    # v7.1 NEW
    CLINICAL_HIGH_VALUE = "clinical_high_value"
    STRUCTURAL_IO = "structural_io"


class GateThreshold(BaseModel):
    """Gate 阈值配置"""
    required: bool = Field(..., description="是否必须通过")
    min_pass_rate: float = Field(..., description="最低通过率（0-1）")
    allow_partial_pass: bool = Field(default=False, description="是否允许部分通过")
    skippable: bool = Field(default=False, description="是否可跳过")
    description: str = Field(..., description="阈值说明")


class RigorProfileConfig(BaseModel):
    """
    Rigor Profile 配置

    定义不同强度档位下的 Gate 阈值和要求
    """
    level: RigorLevel = Field(..., description="强度档位")
    name: str = Field(..., description="档位名称")
    description: str = Field(..., description="档位描述")

    # Gate 阈值配置（key 为 gate_type，如 "gate_0", "gate_1_5"）
    gate_thresholds: Dict[str, GateThreshold] = Field(..., description="Gate 阈值配置")

    # 额外要求
    require_manual_verification: bool = Field(default=True, description="是否要求手动验证")
    require_red_team: bool = Field(default=True, description="是否要求红队审查")
    min_literature_count: int = Field(default=20, description="最低文献数量")
    min_doi_parseability: float = Field(default=0.80, description="最低 DOI 可解析率")
    # v7.0 NEW: Gate-specific rigor-aware thresholds
    min_similar_works: int = Field(default=15, description="Gate 1.5: 最低 similar works 数量")
    min_robustness_checks: int = Field(default=6, description="Gate 2: 最低 robustness checks 数量")
    min_top_n_manual_verify: int = Field(default=5, description="Gate 1.6: Top-N 人工核验数量")


# 预定义的 Rigor Profile 配置
TOP_JOURNAL_PROFILE = RigorProfileConfig(
    level=RigorLevel.TOP_JOURNAL,
    name="Top-Journal Mode",
    description="严格模式，适用于顶级期刊投稿。所有 gates 必须通过，高标准验证。",
    gate_thresholds={
        "gate_0": GateThreshold(
            required=True,
            min_pass_rate=1.0,
            allow_partial_pass=False,
            skippable=False,
            description="Project Intake 必须完整（venue + constraints + DoD）"
        ),
        "gate_1": GateThreshold(
            required=True,
            min_pass_rate=1.0,
            allow_partial_pass=False,
            skippable=False,
            description="Topic 必须完整选定（top-1 + backup + claims + Topic Alignment）"
        ),
        "gate_1_5": GateThreshold(
            required=True,
            min_pass_rate=1.0,
            allow_partial_pass=False,
            skippable=False,
            description="Killer Prior Check 必须 PASS（无直接冲突）"
        ),
        "gate_1_6": GateThreshold(
            required=True,
            min_pass_rate=0.8,  # 允许 4/5 通过
            allow_partial_pass=True,
            skippable=False,
            description="Reference QA 至少 4/5 检查项通过（DOI >= 80%）"
        ),
        "gate_2": GateThreshold(
            required=True,
            min_pass_rate=1.0,
            allow_partial_pass=False,
            skippable=False,
            description="Plan Freeze 必须完整（所有 claims 映射 + baseline/ablation/robustness 冻结）"
        ),
    },
    require_manual_verification=True,
    require_red_team=True,
    min_literature_count=25,  # v7: 顶级期刊要求 >= 25
    min_doi_parseability=0.95,  # v7: 顶级期刊要求 >= 95%
    min_similar_works=15,  # v7: Gate 1.5 similar works >= 15
    min_robustness_checks=6,  # v7: Gate 2 robustness >= 6
    min_top_n_manual_verify=5,  # v7: Gate 1.6 Top-5 人工核验
)


FAST_TRACK_PROFILE = RigorProfileConfig(
    level=RigorLevel.FAST_TRACK,
    name="Fast-Track Mode",
    description="快速模式，适用于快速验证想法或会议投稿。部分 gates 可以跳过或降低标准。",
    gate_thresholds={
        "gate_0": GateThreshold(
            required=True,
            min_pass_rate=0.67,  # 3 项中至少 2 项通过
            allow_partial_pass=True,
            skippable=False,
            description="Project Intake 至少 2/3 检查项通过"
        ),
        "gate_1": GateThreshold(
            required=True,
            min_pass_rate=0.6,  # 8 项中至少 5 项通过（含 alignment）
            allow_partial_pass=True,
            skippable=False,
            description="Topic 至少 5/8 检查项通过（含 Topic Alignment，可无 backup）"
        ),
        "gate_1_5": GateThreshold(
            required=True,
            min_pass_rate=0.67,  # 3 项中至少 2 项通过
            allow_partial_pass=True,
            skippable=False,
            description="Killer Prior Check 至少 2/3 检查项通过（允许部分重叠）"
        ),
        "gate_1_6": GateThreshold(
            required=False,
            min_pass_rate=0.6,  # 5 项中至少 3 项通过
            allow_partial_pass=True,
            skippable=True,
            description="Reference QA 可选（建议但不强制）"
        ),
        "gate_2": GateThreshold(
            required=True,
            min_pass_rate=0.71,  # 7 项中至少 5 项通过
            allow_partial_pass=True,
            skippable=False,
            description="Plan Freeze 至少 5/7 检查项通过（可无 robustness）"
        ),
    },
    require_manual_verification=False,  # 快速模式不强制手动验证
    require_red_team=False,  # 快速模式不强制红队审查
    min_literature_count=15,  # v7: 快速模式 >= 15
    min_doi_parseability=0.85,  # v7: 快速模式 >= 85%
    min_similar_works=10,  # v7: Gate 1.5 similar works >= 10
    min_robustness_checks=3,  # v7: Gate 2 robustness >= 3
    min_top_n_manual_verify=3,  # v7: Gate 1.6 Top-3 人工核验
)


# v7.1 NEW: Clinical High-Value Profile
CLINICAL_HIGH_VALUE_PROFILE = RigorProfileConfig(
    level=RigorLevel.CLINICAL_HIGH_VALUE,
    name="Clinical High-Value Mode",
    description="临床高价值模式，适用于临床研究或高影响力医学期刊。最严格的验证标准。",
    gate_thresholds={
        "gate_0": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Project Intake 必须完整（含 IRB/伦理审查信息）"
        ),
        "gate_1": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Topic 必须完整选定（含临床意义声明 + Topic Alignment）"
        ),
        "gate_1_5": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Killer Prior Check 必须 PASS（无直接冲突）"
        ),
        "gate_1_6": GateThreshold(
            required=True, min_pass_rate=0.9, allow_partial_pass=False, skippable=False,
            description="Reference QA 至少 90% 检查项通过"
        ),
        "gate_2": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Plan Freeze 必须完整（含统计功效分析）"
        ),
    },
    require_manual_verification=True,
    require_red_team=True,
    min_literature_count=50,
    min_doi_parseability=0.95,
    min_similar_works=20,  # v7: 临床模式更严格
    min_robustness_checks=8,  # v7: 临床模式更严格
    min_top_n_manual_verify=5,
)


# v7.1 NEW: Structural IO Profile
STRUCTURAL_IO_PROFILE = RigorProfileConfig(
    level=RigorLevel.STRUCTURAL_IO,
    name="Structural IO Mode",
    description="结构化 IO 模式，适用于因果推断/工具变量/制度分析研究。含额外 IO 识别验证。",
    gate_thresholds={
        "gate_0": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Project Intake 必须完整（含 IO 策略声明）"
        ),
        "gate_1": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Topic 必须完整选定（含因果识别策略 + Topic Alignment）"
        ),
        "gate_1_5": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Killer Prior Check 必须 PASS"
        ),
        "gate_1_6": GateThreshold(
            required=True, min_pass_rate=0.85, allow_partial_pass=True, skippable=False,
            description="Reference QA 至少 85% 检查项通过"
        ),
        "gate_2": GateThreshold(
            required=True, min_pass_rate=1.0, allow_partial_pass=False, skippable=False,
            description="Plan Freeze 必须完整（含 IO 识别计划和制度测量合理性检查）"
        ),
    },
    require_manual_verification=True,
    require_red_team=True,
    min_literature_count=40,
    min_doi_parseability=0.90,
    min_similar_works=15,  # v7: 结构化 IO 模式
    min_robustness_checks=6,  # v7: 结构化 IO 模式
    min_top_n_manual_verify=5,
)
# Extra artifacts required for STRUCTURAL_IO profile
STRUCTURAL_IO_EXTRA_ARTIFACTS = [
    "IO_Identification_Plan",
    "IO_Institution_Measurement_Sanity",
]


# Rigor Profile 注册表
RIGOR_PROFILES: Dict[RigorLevel, RigorProfileConfig] = {
    RigorLevel.TOP_JOURNAL: TOP_JOURNAL_PROFILE,
    RigorLevel.FAST_TRACK: FAST_TRACK_PROFILE,
    RigorLevel.CLINICAL_HIGH_VALUE: CLINICAL_HIGH_VALUE_PROFILE,
    RigorLevel.STRUCTURAL_IO: STRUCTURAL_IO_PROFILE,
}


def get_rigor_profile(level: RigorLevel) -> RigorProfileConfig:
    """
    获取 Rigor Profile 配置

    Args:
        level: 强度档位

    Returns:
        RigorProfileConfig: 配置对象

    Raises:
        ValueError: 如果档位不存在
    """
    if level not in RIGOR_PROFILES:
        raise ValueError(f"Unknown rigor level: {level}")
    return RIGOR_PROFILES[level]


def get_gate_threshold(level: RigorLevel, gate_type: str) -> GateThreshold:
    """
    获取指定 Gate 的阈值配置

    Args:
        level: 强度档位
        gate_type: Gate 类型（如 "gate_0", "gate_1_5"）

    Returns:
        GateThreshold: 阈值配置

    Raises:
        ValueError: 如果档位或 Gate 类型不存在
    """
    profile = get_rigor_profile(level)
    if gate_type not in profile.gate_thresholds:
        raise ValueError(f"Unknown gate type: {gate_type} for level {level}")
    return profile.gate_thresholds[gate_type]


def is_gate_required(level: RigorLevel, gate_type: str) -> bool:
    """
    检查指定 Gate 是否必须通过

    Args:
        level: 强度档位
        gate_type: Gate 类型

    Returns:
        bool: 是否必须通过
    """
    try:
        threshold = get_gate_threshold(level, gate_type)
        return threshold.required
    except ValueError:
        # 如果 Gate 类型不存在，默认为必须
        return True


def calculate_gate_verdict(
    level: RigorLevel,
    gate_type: str,
    passed_count: int,
    total_count: int
) -> bool:
    """
    根据 Rigor Profile 计算 Gate 是否通过

    Args:
        level: 强度档位
        gate_type: Gate 类型
        passed_count: 通过的检查项数量
        total_count: 总检查项数量

    Returns:
        bool: 是否通过
    """
    if total_count == 0:
        return False

    threshold = get_gate_threshold(level, gate_type)

    # 计算通过率
    pass_rate = passed_count / total_count

    # 使用小的 epsilon 来处理浮点数比较
    epsilon = 1e-9
    return pass_rate >= (threshold.min_pass_rate - epsilon)


class RigorProfileSummary(BaseModel):
    """Rigor Profile 摘要（用于 API 响应）"""
    level: RigorLevel
    name: str
    description: str
    require_manual_verification: bool
    require_red_team: bool
    min_literature_count: int
    min_doi_parseability: float
    min_similar_works: int
    min_robustness_checks: int
    min_top_n_manual_verify: int
    gate_requirements: Dict[str, str]  # gate_type -> description


def get_rigor_profile_summary(level: RigorLevel) -> RigorProfileSummary:
    """
    获取 Rigor Profile 摘要

    Args:
        level: 强度档位

    Returns:
        RigorProfileSummary: 摘要对象
    """
    profile = get_rigor_profile(level)

    gate_requirements = {
        gate_type: threshold.description
        for gate_type, threshold in profile.gate_thresholds.items()
    }

    return RigorProfileSummary(
        level=profile.level,
        name=profile.name,
        description=profile.description,
        require_manual_verification=profile.require_manual_verification,
        require_red_team=profile.require_red_team,
        min_literature_count=profile.min_literature_count,
        min_doi_parseability=profile.min_doi_parseability,
        min_similar_works=profile.min_similar_works,
        min_robustness_checks=profile.min_robustness_checks,
        min_top_n_manual_verify=profile.min_top_n_manual_verify,
        gate_requirements=gate_requirements
    )

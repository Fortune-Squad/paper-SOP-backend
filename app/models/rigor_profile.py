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
            description="Topic 必须完整选定（top-1 + backup + claims）"
        ),
        "gate_1_25": GateThreshold(
            required=True,
            min_pass_rate=1.0,
            allow_partial_pass=False,
            skippable=False,
            description="Topic Alignment 必须通过（关键词匹配 >= 0.7）"
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
    min_literature_count=30,  # 顶级期刊要求更多文献
    min_doi_parseability=0.90  # 顶级期刊要求更高的 DOI 质量
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
            min_pass_rate=0.6,  # 5 项中至少 3 项通过
            allow_partial_pass=True,
            skippable=False,
            description="Topic 至少 3/5 检查项通过（可无 backup）"
        ),
        "gate_1_25": GateThreshold(
            required=False,
            min_pass_rate=0.5,  # 4 项中至少 2 项通过
            allow_partial_pass=True,
            skippable=True,
            description="Topic Alignment 可选（建议但不强制）"
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
    min_literature_count=15,  # 快速模式要求较少文献
    min_doi_parseability=0.70  # 快速模式降低 DOI 质量要求
)


# Rigor Profile 注册表
RIGOR_PROFILES: Dict[RigorLevel, RigorProfileConfig] = {
    RigorLevel.TOP_JOURNAL: TOP_JOURNAL_PROFILE,
    RigorLevel.FAST_TRACK: FAST_TRACK_PROFILE,
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
        gate_requirements=gate_requirements
    )

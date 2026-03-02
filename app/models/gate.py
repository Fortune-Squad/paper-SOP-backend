"""
Gate 检查数据模型
定义 Gate 检查的结构和结果
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class GateType(str, Enum):
    """Gate 类型枚举 (v4.0 - 6 gates)"""
    GATE_0 = "gate_0"
    GATE_1 = "gate_1"
    GATE_1_25 = "gate_1_25"  # NEW v4.0 - Topic Alignment Check
    GATE_1_5 = "gate_1_5"
    GATE_1_6 = "gate_1_6"  # NEW v4.0 - Reference QA Check
    GATE_2 = "gate_2"


class GateVerdict(str, Enum):
    """Gate 判定结果"""
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


class CheckItem(BaseModel):
    """检查项"""
    item_name: str = Field(..., description="检查项名称")
    description: str = Field(..., description="检查项描述")
    passed: bool = Field(..., description="是否通过")
    details: Optional[str] = Field(default=None, description="详细信息")


class GateResult(BaseModel):
    """Gate 检查结果"""
    gate_type: GateType = Field(..., description="Gate 类型")
    verdict: GateVerdict = Field(..., description="判定结果")
    check_items: List[CheckItem] = Field(..., description="检查项列表")
    passed_count: int = Field(..., description="通过的检查项数量")
    total_count: int = Field(..., description="总检查项数量")
    suggestions: List[str] = Field(default_factory=list, description="改进建议")
    checked_at: datetime = Field(default_factory=datetime.now, description="检查时间")
    project_id: str = Field(..., description="项目 ID")

    @property
    def pass_rate(self) -> float:
        """通过率"""
        return (self.passed_count / self.total_count * 100) if self.total_count > 0 else 0

    def is_passed(self) -> bool:
        """是否通过"""
        return self.verdict == GateVerdict.PASS


class Gate0Checklist(BaseModel):
    """Gate 0 检查清单"""
    venue_specified: bool = Field(default=False, description="目标期刊是否指定")
    dod_count: int = Field(default=0, description="DoD 数量")
    hard_constraints_count: int = Field(default=0, description="硬约束数量")

    def validate(self) -> GateResult:
        """验证 Gate 0"""
        check_items = [
            CheckItem(
                item_name="Venue Specified",
                description="目标期刊是否指定",
                passed=self.venue_specified,
                details="目标期刊已指定" if self.venue_specified else "缺少目标期刊"
            ),
            CheckItem(
                item_name="DoD >= 3",
                description="Definition of Done 至少 3 项",
                passed=self.dod_count >= 3,
                details=f"DoD 数量: {self.dod_count}"
            ),
            CheckItem(
                item_name="Hard Constraints >= 3",
                description="硬约束至少 3 项",
                passed=self.hard_constraints_count >= 3,
                details=f"硬约束数量: {self.hard_constraints_count}"
            )
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.venue_specified:
            suggestions.append("请指定目标期刊")
        if self.dod_count < 3:
            suggestions.append(f"请添加至少 {3 - self.dod_count} 项 DoD")
        if self.hard_constraints_count < 3:
            suggestions.append(f"请添加至少 {3 - self.hard_constraints_count} 项硬约束")

        return GateResult(
            gate_type=GateType.GATE_0,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""  # 将在调用时设置
        )


class Gate1Checklist(BaseModel):
    """Gate 1 检查清单"""
    top1_selected: bool = Field(default=False, description="Top-1 选题是否选定")
    backup_defined: bool = Field(default=False, description="备选方案是否定义")
    draft_claims_exist: bool = Field(default=False, description="Draft Claims 是否存在")
    non_claims_exist: bool = Field(default=False, description="Non-Claims 是否存在")
    figure_count: int = Field(default=0, description="最小图表集数量")

    def validate(self) -> GateResult:
        """验证 Gate 1"""
        check_items = [
            CheckItem(
                item_name="Top-1 Selected",
                description="Top-1 选题已选定",
                passed=self.top1_selected,
                details="Top-1 选题已选定" if self.top1_selected else "缺少 Top-1 选题"
            ),
            CheckItem(
                item_name="Backup Defined",
                description="备选方案已定义",
                passed=self.backup_defined,
                details="备选方案已定义" if self.backup_defined else "缺少备选方案"
            ),
            CheckItem(
                item_name="Draft Claims Exist",
                description="Draft Claims 已存在",
                passed=self.draft_claims_exist,
                details="Draft Claims 已存在" if self.draft_claims_exist else "缺少 Draft Claims"
            ),
            CheckItem(
                item_name="Non-Claims Exist",
                description="Non-Claims 已存在",
                passed=self.non_claims_exist,
                details="Non-Claims 已存在" if self.non_claims_exist else "缺少 Non-Claims"
            ),
            CheckItem(
                item_name="Minimal Figure Set <= 4",
                description="最小图表集不超过 4 个",
                passed=0 < self.figure_count <= 4,
                details=f"图表数量: {self.figure_count}"
            )
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.top1_selected:
            suggestions.append("请选定 Top-1 选题")
        if not self.backup_defined:
            suggestions.append("请定义备选方案")
        if not self.draft_claims_exist:
            suggestions.append("请撰写 Draft Claims")
        if not self.non_claims_exist:
            suggestions.append("请撰写 Non-Claims")
        if self.figure_count == 0:
            suggestions.append("请定义最小图表集")
        elif self.figure_count > 4:
            suggestions.append(f"图表数量过多（{self.figure_count}），请精简至 4 个以内")

        return GateResult(
            gate_type=GateType.GATE_1,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class Gate1_5Checklist(BaseModel):
    """Gate 1.5 检查清单（Killer Prior Check）"""
    verdict_is_pass: bool = Field(default=False, description="Killer Prior Check 判定是否为 PASS")
    direct_collision_count: int = Field(default=0, description="直接冲突的文献数量")
    partial_overlap_count: int = Field(default=0, description="部分重叠的文献数量")
    differentiator_clear: bool = Field(default=False, description="差异化点是否清晰")

    def validate(self) -> GateResult:
        """验证 Gate 1.5"""
        check_items = [
            CheckItem(
                item_name="Verdict is PASS",
                description="Killer Prior Check 判定为 PASS",
                passed=self.verdict_is_pass,
                details="判定为 PASS" if self.verdict_is_pass else "判定为 FAIL"
            ),
            CheckItem(
                item_name="No Direct Collision",
                description="无直接冲突的文献",
                passed=self.direct_collision_count == 0,
                details=f"直接冲突文献数量: {self.direct_collision_count}"
            ),
            CheckItem(
                item_name="Differentiator Clear",
                description="差异化点清晰可辩护",
                passed=self.differentiator_clear,
                details="差异化点清晰" if self.differentiator_clear else "差异化点不清晰"
            )
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.verdict_is_pass:
            suggestions.append("Killer Prior Check 未通过，需要修订 Claims")
        if self.direct_collision_count > 0:
            suggestions.append(f"发现 {self.direct_collision_count} 篇直接冲突的文献，需要调整研究方向或 Claims")
        if self.partial_overlap_count > 0:
            suggestions.append(f"发现 {self.partial_overlap_count} 篇部分重叠的文献，需要明确差异化")
        if not self.differentiator_clear:
            suggestions.append("请明确并强化差异化点")

        return GateResult(
            gate_type=GateType.GATE_1_5,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class Gate2Checklist(BaseModel):
    """Gate 2 检查清单"""
    claims_mapped: bool = Field(default=False, description="每个 Claim 是否映射到 figure/table/test")
    modules_have_io: bool = Field(default=False, description="Engineering spec modules 是否都有 I/O + verification")
    baseline_frozen: bool = Field(default=False, description="Baseline 是否冻结")
    ablation_frozen: bool = Field(default=False, description="Ablation 是否冻结")
    robustness_frozen: bool = Field(default=False, description="Robustness 是否冻结")
    pivot_checkpoints_exist: bool = Field(default=False, description="Stop/Pivot checkpoints 是否存在")
    killer_prior_referenced: bool = Field(default=False, description="Killer Prior PASS 是否被引用")

    def validate(self) -> GateResult:
        """验证 Gate 2"""
        check_items = [
            CheckItem(
                item_name="Claims Mapped",
                description="每个 Claim 映射到至少一个 figure/table/test",
                passed=self.claims_mapped,
                details="Claims 已映射" if self.claims_mapped else "Claims 未完全映射"
            ),
            CheckItem(
                item_name="Modules Have I/O",
                description="Engineering spec modules 都有 I/O + verification",
                passed=self.modules_have_io,
                details="Modules 完整" if self.modules_have_io else "Modules 缺少 I/O 或 verification"
            ),
            CheckItem(
                item_name="Baseline Frozen",
                description="Baseline 已冻结",
                passed=self.baseline_frozen,
                details="Baseline 已冻结" if self.baseline_frozen else "Baseline 未冻结"
            ),
            CheckItem(
                item_name="Ablation Frozen",
                description="Ablation 已冻结",
                passed=self.ablation_frozen,
                details="Ablation 已冻结" if self.ablation_frozen else "Ablation 未冻结"
            ),
            CheckItem(
                item_name="Robustness Frozen",
                description="Robustness 已冻结",
                passed=self.robustness_frozen,
                details="Robustness 已冻结" if self.robustness_frozen else "Robustness 未冻结"
            ),
            CheckItem(
                item_name="Pivot Checkpoints Exist",
                description="Stop/Pivot checkpoints 已存在",
                passed=self.pivot_checkpoints_exist,
                details="Checkpoints 已定义" if self.pivot_checkpoints_exist else "缺少 Checkpoints"
            ),
            CheckItem(
                item_name="Killer Prior Referenced",
                description="Killer Prior PASS 已被引用",
                passed=self.killer_prior_referenced,
                details="已引用 Killer Prior" if self.killer_prior_referenced else "未引用 Killer Prior"
            )
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.claims_mapped:
            suggestions.append("请确保每个 Claim 都映射到具体的 figure/table/test")
        if not self.modules_have_io:
            suggestions.append("请完善 Engineering spec modules 的 I/O 和 verification")
        if not self.baseline_frozen:
            suggestions.append("请冻结 Baseline")
        if not self.ablation_frozen:
            suggestions.append("请冻结 Ablation")
        if not self.robustness_frozen:
            suggestions.append("请冻结 Robustness")
        if not self.pivot_checkpoints_exist:
            suggestions.append("请定义 Stop/Pivot checkpoints")
        if not self.killer_prior_referenced:
            suggestions.append("请在计划中引用 Killer Prior PASS 结果")

        return GateResult(
            gate_type=GateType.GATE_2,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class Gate1_25Checklist(BaseModel):
    """Gate 1.25 检查清单（Topic Alignment Check）- v4.0 NEW"""
    north_star_covered: bool = Field(default=False, description="选题是否覆盖北极星问题")
    core_keywords_present: int = Field(default=0, description="核心关键词出现数量（来自 Intake）")
    scope_boundaries_clear: bool = Field(default=False, description="范围边界是否在 Non-Claims 中明确")
    keyword_match_score: float = Field(default=0.0, description="关键词匹配分数（0-1）")

    def validate(self) -> GateResult:
        """验证 Gate 1.25"""
        check_items = [
            CheckItem(
                item_name="North-Star Question Covered",
                description="选题覆盖北极星问题",
                passed=self.north_star_covered,
                details="选题覆盖北极星问题" if self.north_star_covered else "选题未覆盖北极星问题"
            ),
            CheckItem(
                item_name="Core Keywords Present (3-5)",
                description="核心关键词出现 3-5 个",
                passed=3 <= self.core_keywords_present <= 5,
                details=f"核心关键词数量: {self.core_keywords_present}"
            ),
            CheckItem(
                item_name="Scope Boundaries Clear",
                description="范围边界在 Non-Claims 中明确",
                passed=self.scope_boundaries_clear,
                details="范围边界明确" if self.scope_boundaries_clear else "范围边界不明确"
            ),
            CheckItem(
                item_name="Keyword Match Score >= 0.7",
                description="关键词匹配分数 >= 0.7",
                passed=self.keyword_match_score >= 0.7,
                details=f"匹配分数: {self.keyword_match_score:.2f}"
            )
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.north_star_covered:
            suggestions.append("请确保选题覆盖 Intake Card 中的北极星问题")
        if self.core_keywords_present < 3:
            suggestions.append(f"请在选题中包含更多核心关键词（当前 {self.core_keywords_present}，需要 3-5 个）")
        elif self.core_keywords_present > 5:
            suggestions.append(f"核心关键词过多（{self.core_keywords_present}），请聚焦到 3-5 个")
        if not self.scope_boundaries_clear:
            suggestions.append("请在 Non-Claims 中明确定义研究范围边界")
        if self.keyword_match_score < 0.7:
            suggestions.append(f"关键词匹配度较低（{self.keyword_match_score:.2f}），请调整选题以更好地对齐 Intake")

        return GateResult(
            gate_type=GateType.GATE_1_25,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class Gate1_6Checklist(BaseModel):
    """Gate 1.6 检查清单（Reference QA Check）- v4.0 NEW"""
    literature_count: int = Field(default=0, description="文献矩阵中的文献数量")
    doi_parseability: float = Field(default=0.0, description="DOI 可解析率（0-1）")
    top5_manually_verified: bool = Field(default=False, description="Top 5 相似文献是否手动验证")
    duplicate_count: int = Field(default=0, description="重复文献数量")
    invalid_doi_count: int = Field(default=0, description="无效 DOI 数量")

    def validate(self) -> GateResult:
        """
        验证 Gate 1.6

        Sprint 3 调整：
        - 必须项：文献数量>=20、无重复文献
        - 核心项：DOI可解析率>=80%、无效DOI<=3
        - 可选项：Top 5手动验证（不影响PASS/FAIL）
        - 通过标准：必须项全过 + 核心项至少1项通过
        """
        check_items = [
            CheckItem(
                item_name="Literature Count >= 20 (Required)",
                description="文献矩阵至少 20 篇文献（必须项）",
                passed=self.literature_count >= 20,
                details=f"文献数量: {self.literature_count}"
            ),
            CheckItem(
                item_name="DOI Parseability >= 80%",
                description="DOI 可解析率 >= 80%",
                passed=self.doi_parseability >= 0.80,
                details=f"DOI 可解析率: {self.doi_parseability * 100:.1f}%"
            ),
            CheckItem(
                item_name="Top 5 Manually Verified (Optional)",
                description="Top 5 相似文献已手动验证（可选项，不影响通过）",
                passed=self.top5_manually_verified,
                details="Top 5 已验证" if self.top5_manually_verified else "Top 5 未验证（可选）"
            ),
            CheckItem(
                item_name="No Duplicates (Required)",
                description="无重复文献（必须项）",
                passed=self.duplicate_count == 0,
                details=f"重复文献数量: {self.duplicate_count}"
            ),
            CheckItem(
                item_name="Invalid DOI Count <= 3",
                description="无效 DOI 不超过 3 个",
                passed=self.invalid_doi_count <= 3,
                details=f"无效 DOI 数量: {self.invalid_doi_count}"
            )
        ]

        # 必须项检查（索引0和3）
        required_items = [check_items[0], check_items[3]]
        required_passed = all(item.passed for item in required_items)

        # 核心项检查（索引1和4）
        core_items = [check_items[1], check_items[4]]
        core_passed_count = sum(1 for item in core_items if item.passed)

        # 总通过数
        total_passed_count = sum(1 for item in check_items if item.passed)

        # 通过标准：必须项全过 + 核心项至少1项通过
        verdict = GateVerdict.PASS if (required_passed and core_passed_count >= 1) else GateVerdict.FAIL

        suggestions = []
        if self.literature_count < 20:
            suggestions.append(f"❌ 必须项：请补充文献至至少 20 篇（当前 {self.literature_count} 篇）")
        if self.duplicate_count > 0:
            suggestions.append(f"❌ 必须项：发现 {self.duplicate_count} 篇重复文献，请去重")
        if self.doi_parseability < 0.80:
            suggestions.append(f"⚠️ DOI 可解析率过低（{self.doi_parseability * 100:.1f}%），请修复无效的 DOI 或添加有效链接")
        if self.invalid_doi_count > 3:
            suggestions.append(f"⚠️ 发现 {self.invalid_doi_count} 个无效 DOI，请修复或替换")
        if not self.top5_manually_verified:
            suggestions.append("💡 建议手动验证 Top 5 最相似的文献，确认无 Killer Prior（可选，不影响通过）")

        return GateResult(
            gate_type=GateType.GATE_1_6,
            verdict=verdict,
            check_items=check_items,
            passed_count=total_passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )

"""
Gate 检查数据模型
定义 Gate 检查的结构和结果
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class GateType(str, Enum):
    """Gate 类型枚举 (v4.0 - 6 gates + Step 3-4 gates)"""
    GATE_0 = "gate_0"
    GATE_1 = "gate_1"
    GATE_1_25 = "gate_1_25"  # DEPRECATED v7.0 - merged into GATE_1. Kept for backward compat with old data.
    GATE_1_5 = "gate_1_5"
    GATE_1_6 = "gate_1_6"  # NEW v4.0 - Reference QA Check
    GATE_2 = "gate_2"
    # Step 3-4 Gates
    GATE_WP = "gate_wp"  # WP 验收门禁
    GATE_SUBTASK = "gate_subtask"  # Subtask 验收门禁 (§2.2.3)
    GATE_FREEZE = "gate_freeze"  # WP 冻结门禁
    GATE_DELIVERY = "gate_delivery"  # 交付门禁


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
    """Gate 0 检查清单 (v7.0: 5 项 AND)"""
    venue_specified: bool = Field(default=False, description="目标期刊是否指定")
    hard_constraints_count: int = Field(default=0, description="硬约束数量")
    dod_count: int = Field(default=0, description="DoD 数量")
    north_star_exists: bool = Field(default=False, description="North-Star Question 是否存在")
    frontmatter_valid: bool = Field(default=False, description="Front-matter 是否完整")

    def validate(self) -> GateResult:
        """验证 Gate 0"""
        check_items = [
            CheckItem(
                item_name="Target Venue Specified",
                description="目标期刊/会议已指定",
                passed=self.venue_specified,
                details="目标期刊已指定" if self.venue_specified else "缺少目标期刊"
            ),
            CheckItem(
                item_name="Hard Constraints >= 3",
                description="硬约束至少 3 项",
                passed=self.hard_constraints_count >= 3,
                details=f"硬约束数量: {self.hard_constraints_count}"
            ),
            CheckItem(
                item_name="DoD >= 3",
                description="Definition of Done 至少 3 项",
                passed=self.dod_count >= 3,
                details=f"DoD 数量: {self.dod_count}"
            ),
            CheckItem(
                item_name="North-Star Question Exists",
                description="North-Star Question 已定义（单句）",
                passed=self.north_star_exists,
                details="North-Star Question 已定义" if self.north_star_exists else "缺少 North-Star Question"
            ),
            CheckItem(
                item_name="Front-Matter Valid",
                description="Front-matter 完整（doc_type, status, version）",
                passed=self.frontmatter_valid,
                details="Front-matter 完整" if self.frontmatter_valid else "Front-matter 不完整"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.venue_specified:
            suggestions.append("请指定目标期刊/会议")
        if self.hard_constraints_count < 3:
            suggestions.append(f"请添加至少 {3 - self.hard_constraints_count} 项硬约束")
        if self.dod_count < 3:
            suggestions.append(f"请添加至少 {3 - self.dod_count} 项 DoD")
        if not self.north_star_exists:
            suggestions.append("请在 Intake Card 中定义 North-Star Question（单句研究问题）")
        if not self.frontmatter_valid:
            suggestions.append("请确保文档 front-matter 包含 doc_type, status, version 字段")

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
    """Gate 1 检查清单 (v7.0: 8 项 AND，含原 Gate 1.25 Topic Alignment 检查项)"""
    top1_selected: bool = Field(default=False, description="Top-1 选题是否选定")
    backup_defined: bool = Field(default=False, description="备选方案是否定义")
    draft_claims_count: int = Field(default=0, description="Draft Claims 数量")
    non_claims_count: int = Field(default=0, description="Non-Claims 数量")
    figure_table_count: int = Field(default=0, description="最小图表集数量")
    # v7.0: Topic Alignment 检查项（原 Gate 1.25）
    north_star_covered: bool = Field(default=False, description="Selected Topic 回答 North-Star Question")
    core_keywords_present: int = Field(default=0, description="核心术语覆盖数量（需 >= 3）")
    scope_in_nonclaims: bool = Field(default=False, description="超出 scope 的内容写进 non-claims")

    def validate(self) -> GateResult:
        """验证 Gate 1"""
        check_items = [
            CheckItem(
                item_name="Top-1 Topic Selected",
                description="Top-1 选题已选定",
                passed=self.top1_selected,
                details="Top-1 选题已选定" if self.top1_selected else "缺少 Top-1 选题"
            ),
            CheckItem(
                item_name="Top-2 Backup Defined",
                description="备选方案已定义",
                passed=self.backup_defined,
                details="备选方案已定义" if self.backup_defined else "缺少备选方案"
            ),
            CheckItem(
                item_name="Draft Claims >= 6",
                description="Draft Claims 至少 6 个",
                passed=self.draft_claims_count >= 6,
                details=f"Draft Claims 数量: {self.draft_claims_count}"
            ),
            CheckItem(
                item_name="Non-Claims >= 6",
                description="Non-Claims 至少 6 个",
                passed=self.non_claims_count >= 6,
                details=f"Non-Claims 数量: {self.non_claims_count}"
            ),
            CheckItem(
                item_name="Minimal Figure/Table Set <= 4",
                description="最小图表集 1-4 个",
                passed=0 < self.figure_table_count <= 4,
                details=f"图表数量: {self.figure_table_count}"
            ),
            # v7.0: Topic Alignment 检查项（原 Gate 1.25）
            CheckItem(
                item_name="North-Star Question Covered",
                description="选题覆盖北极星问题",
                passed=self.north_star_covered,
                details="选题覆盖北极星问题" if self.north_star_covered else "选题未覆盖北极星问题"
            ),
            CheckItem(
                item_name="Core Keywords Present >= 3",
                description="核心术语覆盖 >= 3 个",
                passed=self.core_keywords_present >= 3,
                details=f"核心术语数量: {self.core_keywords_present}"
            ),
            CheckItem(
                item_name="Scope Boundaries in Non-Claims",
                description="超出 scope 的内容写进 non-claims",
                passed=self.scope_in_nonclaims,
                details="范围边界明确" if self.scope_in_nonclaims else "范围边界不明确"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.top1_selected:
            suggestions.append("请选定 Top-1 选题")
        if not self.backup_defined:
            suggestions.append("请定义备选方案（Top-2）")
        if self.draft_claims_count < 6:
            suggestions.append(f"请补充 Draft Claims 至至少 6 个（当前 {self.draft_claims_count}）")
        if self.non_claims_count < 6:
            suggestions.append(f"请补充 Non-Claims 至至少 6 个（当前 {self.non_claims_count}）")
        if self.figure_table_count == 0:
            suggestions.append("请定义最小图表集")
        elif self.figure_table_count > 4:
            suggestions.append(f"图表数量过多（{self.figure_table_count}），请精简至 4 个以内")
        if not self.north_star_covered:
            suggestions.append("请确保选题覆盖 Intake Card 中的北极星问题")
        if self.core_keywords_present < 3:
            suggestions.append(f"请在选题中包含更多核心关键词（当前 {self.core_keywords_present}，需要 >= 3 个）")
        if not self.scope_in_nonclaims:
            suggestions.append("请在 Non-Claims 中明确定义研究范围边界")

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
    """Gate 1.5 检查清单（Killer Prior Check）- v7.0: 5 项 AND, rigor-aware"""
    similar_works_count: int = Field(default=0, description="Similar works 数量")
    min_similar_works: int = Field(default=15, description="最低 similar works 数量（rigor-aware）")
    refs_verifiable: bool = Field(default=False, description="文献是否可核验（DOI/arXiv）")
    collision_map_exists: bool = Field(default=False, description="Collision map 是否存在")
    required_edits_count: int = Field(default=0, description="Required edits 数量")
    verdict_is_pass: bool = Field(default=False, description="Killer Prior Check 判定是否为 PASS")

    def validate(self) -> GateResult:
        """验证 Gate 1.5"""
        check_items = [
            CheckItem(
                item_name=f"Similar Works >= {self.min_similar_works}",
                description=f"相似工作至少 {self.min_similar_works} 篇（rigor-aware）",
                passed=self.similar_works_count >= self.min_similar_works,
                details=f"Similar works 数量: {self.similar_works_count}"
            ),
            CheckItem(
                item_name="References Verifiable",
                description="每条文献可核验（DOI/arXiv）",
                passed=self.refs_verifiable,
                details="文献可核验" if self.refs_verifiable else "部分文献不可核验"
            ),
            CheckItem(
                item_name="Collision Map Exists",
                description="Collision map 存在（prior → claim 映射）",
                passed=self.collision_map_exists,
                details="Collision map 存在" if self.collision_map_exists else "缺少 Collision map"
            ),
            CheckItem(
                item_name="Required Edits <= 5",
                description="Required edits 不超过 5 项",
                passed=self.required_edits_count <= 5,
                details=f"Required edits 数量: {self.required_edits_count}"
            ),
            CheckItem(
                item_name="Verdict is PASS",
                description="Killer Prior Check 判定为 PASS",
                passed=self.verdict_is_pass,
                details="判定为 PASS" if self.verdict_is_pass else "判定为 FAIL"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if self.similar_works_count < self.min_similar_works:
            suggestions.append(f"Similar works 不足（{self.similar_works_count}/{self.min_similar_works}），请补充文献调研")
        if not self.refs_verifiable:
            suggestions.append("部分文献缺少 DOI/arXiv 链接，请补充可核验引用")
        if not self.collision_map_exists:
            suggestions.append("请添加 Collision map（prior → claim 映射）")
        if self.required_edits_count > 5:
            suggestions.append(f"Required edits 过多（{self.required_edits_count}），请精简或修订 claims")
        if not self.verdict_is_pass:
            suggestions.append("Killer Prior Check 未通过，需要修订 Claims")

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
    """Gate 2 检查清单 (v7.0: 7 项 AND, 部分 rigor-aware)"""
    claims_mapped: bool = Field(default=False, description="每个 Claim 是否映射到 figure/table/test")
    consistency_lint_passed: bool = Field(default=False, description="Consistency Lint 是否通过")
    baselines_count: int = Field(default=0, description="Baselines 数量")
    robustness_count: int = Field(default=0, description="Robustness checks 数量")
    min_robustness: int = Field(default=6, description="最低 robustness checks 数量（rigor-aware）")
    pivot_checkpoints_count: int = Field(default=0, description="Stop/Pivot checkpoints 数量")
    killer_prior_referenced: bool = Field(default=False, description="Killer Prior PASS 是否被引用")
    modules_have_io: bool = Field(default=False, description="Engineering spec modules 是否都有 I/O + verification")

    def validate(self) -> GateResult:
        """验证 Gate 2"""
        check_items = [
            CheckItem(
                item_name="Claims Mapped to Evidence",
                description="每个 Claim 映射到至少一个 figure/table/test",
                passed=self.claims_mapped,
                details="Claims 已映射" if self.claims_mapped else "Claims 未完全映射"
            ),
            CheckItem(
                item_name="Consistency Lint Passed",
                description="跨文档一致性检查通过",
                passed=self.consistency_lint_passed,
                details="Consistency Lint 通过" if self.consistency_lint_passed else "Consistency Lint 未通过"
            ),
            CheckItem(
                item_name="Baselines >= 2",
                description="Baselines 至少 2 个",
                passed=self.baselines_count >= 2,
                details=f"Baselines 数量: {self.baselines_count}"
            ),
            CheckItem(
                item_name=f"Robustness Checks >= {self.min_robustness}",
                description=f"Robustness checks 至少 {self.min_robustness} 个（rigor-aware）",
                passed=self.robustness_count >= self.min_robustness,
                details=f"Robustness checks 数量: {self.robustness_count}"
            ),
            CheckItem(
                item_name="Stop/Pivot Checkpoints >= 3",
                description="Stop/Pivot checkpoints 至少 3 个",
                passed=self.pivot_checkpoints_count >= 3,
                details=f"Checkpoints 数量: {self.pivot_checkpoints_count}"
            ),
            CheckItem(
                item_name="Killer Prior PASS Referenced",
                description="Killer Prior PASS 结果被引用",
                passed=self.killer_prior_referenced,
                details="已引用" if self.killer_prior_referenced else "未引用 Killer Prior PASS"
            ),
            CheckItem(
                item_name="Modules Have I/O + Verification",
                description="Engineering spec modules 都有 I/O + verification",
                passed=self.modules_have_io,
                details="Modules 完整" if self.modules_have_io else "Modules 缺少 I/O 或 verification"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.claims_mapped:
            suggestions.append("请确保每个 Claim 映射到至少一个 figure/table/test")
        if not self.consistency_lint_passed:
            suggestions.append("跨文档一致性检查未通过，请修复矛盾")
        if self.baselines_count < 2:
            suggestions.append(f"请添加至少 {2 - self.baselines_count} 个 Baseline")
        if self.robustness_count < self.min_robustness:
            suggestions.append(f"请添加至少 {self.min_robustness - self.robustness_count} 个 Robustness check")
        if self.pivot_checkpoints_count < 3:
            suggestions.append(f"请添加至少 {3 - self.pivot_checkpoints_count} 个 Stop/Pivot checkpoint")
        if not self.killer_prior_referenced:
            suggestions.append("请在计划中引用 Killer Prior PASS 结果")
        if not self.modules_have_io:
            suggestions.append("请完善 Engineering spec modules 的 I/O 和 verification")

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
    """DEPRECATED v7.0 - Gate 1.25 merged into Gate 1. Kept for backward compat."""
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
    """Gate 1.6 检查清单（Reference QA Check）- v7.0: 4 项 AND, rigor-aware"""
    literature_count: int = Field(default=0, description="文献矩阵中的文献数量")
    min_literature: int = Field(default=25, description="最低文献数量（rigor-aware）")
    doi_parseability: float = Field(default=0.0, description="DOI 可解析率（0-1）")
    min_doi_parseability: float = Field(default=0.95, description="最低 DOI 可解析率（rigor-aware）")
    unparseable_refs_not_critical: bool = Field(default=False, description="不可解析文献不用于关键论证")
    top_n_manually_verified: bool = Field(default=False, description="Top-N 相似文献是否手动验证")
    top_n: int = Field(default=5, description="Top-N 人工核验数量（rigor-aware）")

    def validate(self) -> GateResult:
        """
        验证 Gate 1.6 (v7.0: rigor-aware)

        v7 SOP 要求 (4 项 AND):
        1. Literature Matrix >= N (rigor-aware)
        2. DOI 可解析率 >= N% (rigor-aware)
        3. 不可解析文献不得用于关键论证
        4. Top-N 最相似 prior 人工核验
        """
        check_items = [
            CheckItem(
                item_name=f"Literature Matrix >= {self.min_literature}",
                description=f"文献矩阵至少 {self.min_literature} 篇（rigor-aware）",
                passed=self.literature_count >= self.min_literature,
                details=f"文献数量: {self.literature_count}"
            ),
            CheckItem(
                item_name=f"DOI Parseability >= {self.min_doi_parseability * 100:.0f}%",
                description=f"DOI 可解析率 >= {self.min_doi_parseability * 100:.0f}%（rigor-aware）",
                passed=self.doi_parseability >= self.min_doi_parseability,
                details=f"DOI 可解析率: {self.doi_parseability * 100:.1f}%"
            ),
            CheckItem(
                item_name="Unparseable Refs Not Critical",
                description="不可解析文献不用于关键论证",
                passed=self.unparseable_refs_not_critical,
                details="不可解析文献已排除关键论证" if self.unparseable_refs_not_critical else "需确认不可解析文献未用于关键论证"
            ),
            CheckItem(
                item_name=f"Top-{self.top_n} Manual Verification",
                description=f"Top-{self.top_n} 最相似 prior 人工核验",
                passed=self.top_n_manually_verified,
                details=f"Top-{self.top_n} 已核验" if self.top_n_manually_verified else f"Top-{self.top_n} 未核验（需人工确认）"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if self.literature_count < self.min_literature:
            suggestions.append(f"请补充文献至至少 {self.min_literature} 篇（当前 {self.literature_count} 篇）")
        if self.doi_parseability < self.min_doi_parseability:
            suggestions.append(f"DOI 可解析率过低（{self.doi_parseability * 100:.1f}%），需 >= {self.min_doi_parseability * 100:.0f}%")
        if not self.unparseable_refs_not_critical:
            suggestions.append("请确认不可解析的文献未用于关键论证")
        if not self.top_n_manually_verified:
            suggestions.append(f"请人工核验 Top-{self.top_n} 最相似的 prior（点开确认存在）")

        return GateResult(
            gate_type=GateType.GATE_1_6,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class SubtaskGateChecklist(BaseModel):
    """Subtask 验收门禁 (§2.2.3)"""
    status_completed: bool = Field(default=False, description="subtask 状态为 completed")
    boundary_check_passed: bool = Field(default=False, description="artifact 边界检查通过")
    acceptance_criteria_met: bool = Field(default=False, description="acceptance_criteria 全部满足")
    no_critical_issues: bool = Field(default=False, description="无 severity=high 的 open_issues")

    def validate(self, subtask_id: str = "") -> GateResult:
        """验证 Subtask Gate"""
        check_items = [
            CheckItem(
                item_name="Status Completed",
                description="subtask 状态为 completed",
                passed=self.status_completed,
                details="已完成" if self.status_completed else "未完成"
            ),
            CheckItem(
                item_name="Boundary Check Passed",
                description="artifact 边界检查通过",
                passed=self.boundary_check_passed,
                details="边界检查通过" if self.boundary_check_passed else "存在越界修改"
            ),
            CheckItem(
                item_name="Acceptance Criteria Met",
                description="acceptance_criteria 全部满足",
                passed=self.acceptance_criteria_met,
                details="验收标准已满足" if self.acceptance_criteria_met else "验收标准未满足"
            ),
            CheckItem(
                item_name="No Critical Issues",
                description="无 severity=high 的 open_issues",
                passed=self.no_critical_issues,
                details="无严重问题" if self.no_critical_issues else "存在严重问题"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.status_completed:
            suggestions.append("请完成 subtask 执行")
        if not self.boundary_check_passed:
            suggestions.append("存在越界修改，请检查 artifact 边界")
        if not self.acceptance_criteria_met:
            suggestions.append("请确保满足所有验收标准")
        if not self.no_critical_issues:
            suggestions.append("请解决所有严重问题 (severity=high)")

        return GateResult(
            gate_type=GateType.GATE_SUBTASK,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class WPGateChecklist(BaseModel):
    """WP 验收门禁检查清单 (Step 3)"""
    all_subtasks_completed: bool = Field(default=False, description="所有 subtask 是否完成")
    gate_criteria_met: bool = Field(default=False, description="WP gate 标准是否满足")
    boundary_check_passed: bool = Field(default=False, description="Artifact 边界检查是否通过")
    review_approved: bool = Field(default=False, description="Reviewer 是否批准")

    def validate(self, wp_id: str = "") -> GateResult:
        """验证 WP Gate"""
        check_items = [
            CheckItem(
                item_name="All Subtasks Completed",
                description="所有 subtask 已完成",
                passed=self.all_subtasks_completed,
                details="所有 subtask 已完成" if self.all_subtasks_completed else "存在未完成的 subtask"
            ),
            CheckItem(
                item_name="Gate Criteria Met",
                description="WP 验收标准已满足",
                passed=self.gate_criteria_met,
                details="验收标准已满足" if self.gate_criteria_met else "验收标准未满足"
            ),
            CheckItem(
                item_name="Boundary Check Passed",
                description="Artifact 边界检查通过",
                passed=self.boundary_check_passed,
                details="边界检查通过" if self.boundary_check_passed else "存在越界修改"
            ),
            CheckItem(
                item_name="Review Approved",
                description="Reviewer 已批准",
                passed=self.review_approved,
                details="已批准" if self.review_approved else "未批准"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.all_subtasks_completed:
            suggestions.append("请完成所有 subtask")
        if not self.gate_criteria_met:
            suggestions.append("请确保满足 WP 验收标准")
        if not self.boundary_check_passed:
            suggestions.append("存在越界修改，请检查 artifact 边界")
        if not self.review_approved:
            suggestions.append("请等待 Reviewer 批准")

        return GateResult(
            gate_type=GateType.GATE_WP,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class FreezeGateChecklist(BaseModel):
    """WP 冻结门禁检查清单 (Step 3) — v1.2: 7 项 (F1-F7)"""
    wp_gate_passed: bool = Field(default=False, description="F1: WP Gate 是否通过")
    artifacts_committed: bool = Field(default=False, description="F2: Artifacts 是否已提交到 Git")
    no_open_issues: bool = Field(default=False, description="F3: 是否无未解决问题")
    # v1.2 DevSpec §9.2: F4-F7
    version_tagged: bool = Field(default=False, description="F4: Git tag 已创建")
    no_uncommitted_changes: bool = Field(default=False, description="F5: 无未提交更改")
    manifest_complete: bool = Field(default=False, description="F6: FROZEN_MANIFEST 完整")
    agents_memory_updated: bool = Field(default=False, description="F7: AGENTS.md/MEMORY.md 已更新")

    def validate(self, wp_id: str = "") -> GateResult:
        """验证 Freeze Gate (v1.2: 7 项)"""
        check_items = [
            CheckItem(
                item_name="F1: WP Gate Passed",
                description="WP 验收门禁已通过",
                passed=self.wp_gate_passed,
                details="WP Gate 已通过" if self.wp_gate_passed else "WP Gate 未通过"
            ),
            CheckItem(
                item_name="F2: Artifacts Committed",
                description="所有 artifacts 已提交到 Git",
                passed=self.artifacts_committed,
                details="已提交" if self.artifacts_committed else "未提交"
            ),
            CheckItem(
                item_name="F3: No Open Issues",
                description="无未解决问题",
                passed=self.no_open_issues,
                details="无未解决问题" if self.no_open_issues else "存在未解决问题"
            ),
            CheckItem(
                item_name="F4: Version Tagged",
                description="Git tag 已创建",
                passed=self.version_tagged,
                details="已创建 tag" if self.version_tagged else "未创建 tag"
            ),
            CheckItem(
                item_name="F5: No Uncommitted Changes",
                description="无未提交更改",
                passed=self.no_uncommitted_changes,
                details="无未提交更改" if self.no_uncommitted_changes else "存在未提交更改"
            ),
            CheckItem(
                item_name="F6: Manifest Complete",
                description="FROZEN_MANIFEST 完整",
                passed=self.manifest_complete,
                details="FROZEN_MANIFEST 完整" if self.manifest_complete else "FROZEN_MANIFEST 不完整或不存在"
            ),
            CheckItem(
                item_name="F7: AGENTS/MEMORY Updated",
                description="AGENTS.md 和 MEMORY.md 已更新",
                passed=self.agents_memory_updated,
                details="已更新" if self.agents_memory_updated else "未更新"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.wp_gate_passed:
            suggestions.append("WP Gate 未通过，请先完成 WP 验收")
        if not self.artifacts_committed:
            suggestions.append("请提交所有 artifacts 到 Git")
        if not self.no_open_issues:
            suggestions.append("请解决所有未解决问题")
        if not self.version_tagged:
            suggestions.append("请创建 Git tag")
        if not self.no_uncommitted_changes:
            suggestions.append("请提交所有未提交更改")
        if not self.manifest_complete:
            suggestions.append("请生成 FROZEN_MANIFEST")
        if not self.agents_memory_updated:
            suggestions.append("请更新 AGENTS.md 和 MEMORY.md")

        return GateResult(
            gate_type=GateType.GATE_FREEZE,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )


class DeliveryGateChecklist(BaseModel):
    """交付门禁检查清单 (Step 4) — v1.2 §9.3: 8 项 (D1-D8)"""
    all_wps_frozen: bool = Field(default=False, description="D1: 所有 WP status=frozen")
    all_figures_approved: bool = Field(default=False, description="D2: 所有图表 human_approved=true AND 生成代码可运行")
    assembly_complete: bool = Field(default=False, description="D3: 按 delivery_profile 检查应有文件全部存在")
    repro_check_pass: bool = Field(default=False, description="D4: repro_check.json verdict=PASS")
    deliverables_complete: bool = Field(default=False, description="D5: manifest vs PlanFrozen deliverables = match")
    checksums_valid: bool = Field(default=False, description="D6: all file checksums match manifest")
    citations_verified: bool = Field(default=False, description="D7: citation_report.json verdict=PASS AND missing_keys=[]")
    no_forbidden_output: bool = Field(default=False, description="D8: if external_assembly_kit: draft.tex/draft.md must NOT exist")

    def validate(self) -> GateResult:
        """验证 Delivery Gate (v1.2 §9.3: 8 项)"""
        check_items = [
            CheckItem(
                item_name="D1: All WPs Frozen",
                description="所有 Work Package 已冻结",
                passed=self.all_wps_frozen,
                details="所有 WP 已冻结" if self.all_wps_frozen else "存在未冻结的 WP"
            ),
            CheckItem(
                item_name="D2: All Figures Approved",
                description="所有图表 human_approved=true AND 生成代码可运行",
                passed=self.all_figures_approved,
                details="图表已审批且代码可运行" if self.all_figures_approved else "图表未审批或代码不可运行"
            ),
            CheckItem(
                item_name="D3: Assembly Complete",
                description="按 delivery_profile 检查应有文件全部存在",
                passed=self.assembly_complete,
                details="Assembly 文件齐全" if self.assembly_complete else "Assembly 文件不完整"
            ),
            CheckItem(
                item_name="D4: Repro Check Pass",
                description="repro_check.json verdict=PASS",
                passed=self.repro_check_pass,
                details="可复现性验证通过" if self.repro_check_pass else "可复现性验证未通过"
            ),
            CheckItem(
                item_name="D5: Deliverables Complete",
                description="manifest vs PlanFrozen deliverables = match",
                passed=self.deliverables_complete,
                details="交付物与 PlanFrozen 匹配" if self.deliverables_complete else "交付物与 PlanFrozen 不匹配"
            ),
            CheckItem(
                item_name="D6: Checksums Valid",
                description="FROZEN_MANIFEST checksum 验证通过",
                passed=self.checksums_valid,
                details="Checksum 验证通过" if self.checksums_valid else "Checksum 验证失败"
            ),
            CheckItem(
                item_name="D7: Citations Verified",
                description="citation_report.json verdict=PASS AND missing_keys=[]",
                passed=self.citations_verified,
                details="引用验证通过" if self.citations_verified else "引用验证未通过"
            ),
            CheckItem(
                item_name="D8: No Forbidden Output",
                description="无违规输出（符合 delivery_profile）",
                passed=self.no_forbidden_output,
                details="无违规输出" if self.no_forbidden_output else "存在违规输出"
            ),
        ]

        passed_count = sum(1 for item in check_items if item.passed)
        verdict = GateVerdict.PASS if passed_count == len(check_items) else GateVerdict.FAIL

        suggestions = []
        if not self.all_wps_frozen:
            suggestions.append("请确保所有 WP 已冻结")
        if not self.all_figures_approved:
            suggestions.append("请确认所有图表已审批且生成代码可运行")
        if not self.assembly_complete:
            suggestions.append("请检查 delivery_profile 要求的文件是否齐全")
        if not self.repro_check_pass:
            suggestions.append("请确保 repro_check.json verdict=PASS")
        if not self.deliverables_complete:
            suggestions.append("请确保 manifest 与 PlanFrozen deliverables 匹配")
        if not self.checksums_valid:
            suggestions.append("请验证 FROZEN_MANIFEST checksum")
        if not self.citations_verified:
            suggestions.append("请确保 citation_report.json verdict=PASS 且 missing_keys 为空")
        if not self.no_forbidden_output:
            suggestions.append("请检查 delivery_profile 合规性")

        return GateResult(
            gate_type=GateType.GATE_DELIVERY,
            verdict=verdict,
            check_items=check_items,
            passed_count=passed_count,
            total_count=len(check_items),
            suggestions=suggestions,
            project_id=""
        )

"""
项目数据模型
定义项目的结构和状态管理

v6.0 Enhancement: 添加 Rigor Profile 支持
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from app.config import settings


class ProjectStatus(str, Enum):
    """项目状态枚举"""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class StepStatus(str, Enum):
    """步骤状态枚举"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ResearchType(str, Enum):
    """研究类型枚举"""
    OBSERVATIONAL = "observational"
    CAUSAL = "causal"
    SIMULATION = "simulation"
    THEORY = "theory"
    SYSTEM = "system"
    ML = "ml"


class DataStatus(str, Enum):
    """数据状态枚举"""
    AVAILABLE = "available"
    PARTIAL = "partial"
    NEED_COLLECTION = "need-collection"


class StepInfo(BaseModel):
    """步骤信息"""
    step_id: str = Field(..., description="步骤 ID，如 step_0_1")
    step_name: str = Field(..., description="步骤名称")
    status: StepStatus = Field(default=StepStatus.PENDING, description="步骤状态")
    ai_model: Optional[str] = Field(default=None, description="使用的 AI 模型（ChatGPT/Gemini）")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    output_documents: List[str] = Field(default_factory=list, description="输出文档列表")
    retry_count: int = Field(default=0, description="当前重试次数")
    max_retries: int = Field(default=2, description="最大重试次数")


class LoopHistoryEntry(BaseModel):
    """Loop 回退历史记录条目"""
    loop_id: str = Field(..., description="Loop ID，如 loop_a ~ loop_e")
    gate_name: str = Field(..., description="触发 Gate 名称，如 gate_1, gate_1_5")
    target_step: str = Field(..., description="回退目标步骤 ID")
    retry_number: int = Field(..., description="当前重试次数")
    action: str = Field(..., description="动作: rollback | exhausted")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")


class ProjectConfig(BaseModel):
    """项目配置"""
    topic: str = Field(..., description="研究主题")
    target_venue: str = Field(..., description="目标期刊")
    research_type: ResearchType = Field(..., description="研究类型")
    data_status: DataStatus = Field(..., description="数据状态")
    hard_constraints: List[str] = Field(..., description="硬约束（红线）")
    time_budget: Optional[str] = Field(default=None, description="时间预算")
    keywords: List[str] = Field(..., description="关键词")
    project_context: Optional[str] = Field(default=None, description="项目背景")
    rigor_profile: Optional[str] = Field(default="top_journal", description="研究强度档位（top_journal/fast_track）")
    # v7.1 NEW
    enable_idea_lab: bool = Field(default=False, description="是否启用 Idea-Lab 发散生成")
    # v7.2 NEW: Resource Card 用户表单数据
    resource_card_input: Optional[Dict[str, Any]] = Field(default=None, description="用户填写的 Resource Card 表单数据")


class Project(BaseModel):
    """
    项目模型

    v6.0 Enhancement: 添加 rigor_profile 字段
    v6.1 Enhancement: 添加用户所有权字段（owner_id, owner_username）
    """
    project_id: str = Field(..., description="项目 ID（唯一标识）")
    project_name: str = Field(..., description="项目名称")
    config: ProjectConfig = Field(..., description="项目配置")
    status: ProjectStatus = Field(default=ProjectStatus.CREATED, description="项目状态")
    current_step: str = Field(default="step_s_1", description="当前步骤")  # v6.0: Start from Bootloader
    steps: Dict[str, StepInfo] = Field(default_factory=dict, description="步骤信息字典")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    # v6.0 NEW: Rigor Profile
    rigor_profile: Optional[str] = Field(default="top_journal", description="研究强度档位（top_journal/fast_track）")

    # v6.1 NEW: User Ownership
    owner_id: Optional[str] = Field(default=None, description="项目所有者 ID")
    owner_username: Optional[str] = Field(default=None, description="项目所有者用户名")

    # Gate 状态 (v4.0 - 6 gates)
    gate_0_passed: bool = Field(default=False, description="Gate 0 是否通过")
    gate_1_passed: bool = Field(default=False, description="Gate 1 是否通过")
    gate_1_25_passed: bool = Field(default=True, description="DEPRECATED v7.0 - merged into Gate 1. Always True for new projects.")
    gate_1_5_passed: bool = Field(default=False, description="Gate 1.5 是否通过（Killer Prior）")
    gate_1_6_passed: bool = Field(default=False, description="Gate 1.6 是否通过（Reference QA）")
    gate_2_passed: bool = Field(default=False, description="Gate 2 是否通过")

    # Step 3-4 Gate 状态
    gate_wp_results: Dict[str, Any] = Field(default_factory=dict, description="WP Gate 检查结果 (wp_id -> result)")
    gate_delivery_passed: bool = Field(default=False, description="Delivery Gate 是否通过")

    # Step 3-4 高层标志
    execution_state_ref: Optional[str] = Field(default=None, description="state.json 路径引用")
    delivery_profile: Optional[str] = Field(default=None, description="交付档案类型 (internal_draft/external_assembly_kit)")
    step3_started: bool = Field(default=False, description="Step 3 是否已开始")
    step3_completed: bool = Field(default=False, description="Step 3 是否已完成")
    step4_started: bool = Field(default=False, description="Step 4 是否已开始")
    step4_completed: bool = Field(default=False, description="Step 4 是否已完成")

    # Gate 检查结果 (v4.0 - 存储完整的检查结果)
    gate_results: Dict[str, Any] = Field(default_factory=dict, description="Gate 检查结果字典")

    # v7.0 NEW: Loop 回退历史
    loop_history: List[LoopHistoryEntry] = Field(default_factory=list, description="Loop 回退历史")

    # v6.0 Phase 3: Metadata for clarity score and bootloader decision
    metadata: Dict[str, Any] = Field(default_factory=dict, description="项目元数据（clarity_score, bootloader_decision等）")

    # v6 → v7 step ID migration mapping
    _V6_TO_V7_STEP_MAP: Dict[str, str] = {
        "step_s0": "step_0_1",
        "step_s0b": "step_0_2",
        "step_s1a": "step_1_1a",      # Search Plan
        "step_s1b": "step_1_1b",      # The Hunt
        "step_s1c": "step_1_1c",      # Literature Synthesis
        "step_s2": "step_1_2",
        "step_s3": "step_1_3",
        "step_s3b": "step_1_3b",
        "step_s4": "step_1_4",
        "step_s4_story": "step_1_5",
        "step_s5_figlist": "step_2_0",
        "step_s5a": "step_2_1",
        "step_s5b": "step_2_2",
        "step_s5c": "step_2_3",
        "step_s6": "step_2_4",
        "step_s6b": "step_2_4b",
        "step_s7": "step_2_5",
    }

    # v6 → v7 current_step mapping
    _V6_TO_V7_CURRENT_STEP_MAP: Dict[str, str] = {
        "step_s0": "step_0_1",
        "step_s0b": "step_0_2",
        "step_s1a": "step_1_1a",
        "step_s1b": "step_1_1b",
        "step_s1c": "step_1_1c",
        "step_s2": "step_1_2",
        "step_s3": "step_1_3",
        "step_s3b": "step_1_3b",
        "step_s4": "step_1_4",
        "step_s4_story": "step_1_5",
        "step_s5_figlist": "step_2_0",
        "step_s5a": "step_2_1",
        "step_s5b": "step_2_2",
        "step_s5c": "step_2_3",
        "step_s6": "step_2_4",
        "step_s6b": "step_2_4b",
        "step_s7": "step_2_5",
    }

    def __init__(self, **data):
        super().__init__(**data)
        # 迁移 v6 步骤 ID 到 v7
        self._migrate_v6_steps()
        # 初始化/合并步骤：确保新增的步骤定义被添加到旧项目中
        self._initialize_steps()

    def _migrate_v6_steps(self):
        """将 v6 旧步骤 ID (step_s*) 迁移到 v7 新 ID (step_0_*, step_1_*, ...)"""
        has_v6_steps = any(k.startswith("step_s") and k != "step_s_1" for k in self.steps)
        if not has_v6_steps:
            return

        migrated_steps: Dict[str, StepInfo] = {}
        for old_id, step_info in self.steps.items():
            new_id = self._V6_TO_V7_STEP_MAP.get(old_id)
            if new_id:
                # 如果多个 v6 步骤映射到同一个 v7 步骤，取最"完成"的状态
                if new_id in migrated_steps:
                    existing = migrated_steps[new_id]
                    if step_info.status == StepStatus.COMPLETED:
                        existing.status = StepStatus.COMPLETED
                        existing.completed_at = step_info.completed_at or existing.completed_at
                else:
                    migrated_steps[new_id] = StepInfo(
                        step_id=new_id,
                        step_name=step_info.step_name,
                        status=step_info.status,
                        ai_model=step_info.ai_model,
                        started_at=step_info.started_at,
                        completed_at=step_info.completed_at,
                        error_message=step_info.error_message,
                        output_documents=step_info.output_documents,
                    )
            elif old_id == "step_s_1":
                # Bootloader 保持不变
                migrated_steps[old_id] = step_info
            # 其他未映射的旧步骤丢弃

        # 替换 steps
        self.steps = migrated_steps

        # 迁移 current_step
        if self.current_step and self.current_step in self._V6_TO_V7_CURRENT_STEP_MAP:
            self.current_step = self._V6_TO_V7_CURRENT_STEP_MAP[self.current_step]

    def _initialize_steps(self):
        """初始化所有步骤，仅添加缺失的步骤（保留已有步骤状态）"""
        # ── v4/v5 → v7 step migration ──
        # step_1_1 (monolithic Deep Research) → step_1_1a/b/c (all inherit completed)
        if "step_1_1" in self.steps and "step_1_1a" not in self.steps:
            old = self.steps["step_1_1"]
            if old.status == StepStatus.COMPLETED:
                for new_id in ("step_1_1a", "step_1_1b", "step_1_1c"):
                    self.steps[new_id] = StepInfo(
                        step_id=new_id, step_name=old.step_name,
                        status=StepStatus.COMPLETED, ai_model=old.ai_model,
                        started_at=old.started_at, completed_at=old.completed_at,
                    )
        # step_1_1b (old Reference QA) → step_1_3b
        if "step_1_1b" in self.steps and "step_1_3b" not in self.steps:
            old_ref = self.steps["step_1_1b"]
            # Only migrate if this is the old Reference QA (not the new Hunt step)
            if old_ref.step_name and "hunt" not in old_ref.step_name.lower():
                self.steps["step_1_3b"] = StepInfo(
                    step_id="step_1_3b", step_name="Reference QA",
                    status=old_ref.status, ai_model=old_ref.ai_model,
                    started_at=old_ref.started_at, completed_at=old_ref.completed_at,
                    error_message=old_ref.error_message,
                )
        # Remove obsolete step IDs
        for obsolete in ("step_1_1", "step_1_2b"):
            self.steps.pop(obsolete, None)
        # Fix current_step if pointing to removed/renamed step
        _CURRENT_STEP_FIX = {
            "step_1_1": "step_1_1a",
            "step_1_2b": "step_1_3",
        }
        if self.current_step in _CURRENT_STEP_FIX:
            self.current_step = _CURRENT_STEP_FIX[self.current_step]

        # ── Status recovery: if downstream steps are completed, upstream must be too ──
        # This handles cases where step statuses were lost during partial migrations
        step_1_ids = ["step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3",
                      "step_1_3b", "step_1_4", "step_1_5"]
        step_2_ids = ["step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4",
                      "step_2_4b", "step_2_5"]

        # Helper: find earliest completed_at from a list of step IDs
        def _earliest_completed_at(sids):
            times = []
            for sid in sids:
                s = self.steps.get(sid)
                if s and s.status == StepStatus.COMPLETED and s.completed_at:
                    times.append(s.completed_at)
            return min(times) if times else datetime.now()

        # If any step_2 is completed, all step_1 must have been completed
        any_step2_completed = any(
            sid in self.steps and self.steps[sid].status == StepStatus.COMPLETED
            for sid in step_2_ids
        )
        if any_step2_completed:
            ref_time = _earliest_completed_at(step_2_ids)
            for sid in step_1_ids:
                if sid in self.steps and self.steps[sid].status == StepStatus.PENDING:
                    self.steps[sid].status = StepStatus.COMPLETED
                    if not self.steps[sid].completed_at:
                        self.steps[sid].completed_at = ref_time
        # If any step_1 after step_1_1c is completed, step_1_1a/b/c must be completed
        later_step1 = ["step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5"]
        any_later_completed = any(
            sid in self.steps and self.steps[sid].status == StepStatus.COMPLETED
            for sid in later_step1
        )
        if any_later_completed:
            ref_time = _earliest_completed_at(later_step1)
            for sid in ["step_1_1a", "step_1_1b", "step_1_1c"]:
                if sid in self.steps and self.steps[sid].status == StepStatus.PENDING:
                    self.steps[sid].status = StepStatus.COMPLETED
                    if not self.steps[sid].completed_at:
                        self.steps[sid].completed_at = ref_time

        # Ensure all completed steps have completed_at set
        for sid, step in self.steps.items():
            if step.status == StepStatus.COMPLETED and not step.completed_at:
                step.completed_at = _earliest_completed_at(step_2_ids + step_1_ids)

        # Fix current_step: find the first pending step in sequence
        full_sequence = [
            "step_s_1", "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3",
            "step_1_3b", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4",
            "step_2_4b", "step_2_5",
            "step_3_init", "step_3_exec",
            "step_4_collect", "step_4_figure_polish", "step_4_assembly",
            "step_4_citation_qa", "step_4_repro", "step_4_package",
        ]
        if self.current_step:
            cur = self.steps.get(self.current_step)
            if cur and cur.status == StepStatus.COMPLETED:
                # current_step is already completed, advance to first pending
                for sid in full_sequence:
                    s = self.steps.get(sid)
                    if s and s.status == StepStatus.PENDING:
                        self.current_step = sid
                        break

        # 从配置中获取实际使用的模型名称
        openai_model = settings.openai_model
        gemini_model = settings.gemini_model
        claude_model = settings.claude_model

        step_definitions = [
            # S-1 Bootloader (NEW v6.0)
            ("step_s_1", "Fuzzy Bootloader", gemini_model),
            # Step 0 - Project Bootstrapping
            ("step_0_1", "Project Intake Card", openai_model),
            ("step_0_2", "Venue Taste Primer", gemini_model),
            # Step 1 - Deep Research & Topic Freeze
            ("step_1_1a", "Search Plan", openai_model),
            ("step_1_1b", "The Hunt", gemini_model),
            ("step_1_1c", "Literature Synthesis", openai_model),
            ("step_1_2", "Topic Decision & Draft Claim Set", openai_model),
            ("step_1_3", "Killer Prior Check", gemini_model),
            ("step_1_3b", "Reference QA", gemini_model),
            ("step_1_4", "Claims Freeze", openai_model),
            ("step_1_5", "Paper Identity & Figure-First Story", gemini_model),
            # Step 2 - Blueprint & Engineering
            ("step_2_0", "Figure/Table List", openai_model),  # NEW v4.0
            ("step_2_1", "Full Proposal", openai_model),
            ("step_2_2", "Data/Simulation Spec", openai_model),
            ("step_2_3", "Engineering Decomposition", openai_model),
            ("step_2_4", "Reviewer #2 Red-Team", gemini_model),
            ("step_2_4b", "Patch Propagation", openai_model),  # NEW v4.0
            ("step_2_5", "Plan Freeze Package", openai_model),
            # Step 3 - Research Execution (v1.2: Claude as executor)
            ("step_3_init", "WP DAG Initialization", claude_model),
            ("step_3_exec", "WP Execution Engine", claude_model),
            # Step 4 - Convergence & Delivery (v1.2: Claude as executor)
            ("step_4_collect", "Collect Frozen Artifacts", claude_model),
            ("step_4_figure_polish", "Figure Polish", claude_model),
            ("step_4_assembly", "Assembly Kit Generation", claude_model),
            ("step_4_citation_qa", "Citation QA Check", claude_model),
            ("step_4_repro", "Reproducibility Check", claude_model),
            ("step_4_package", "Delivery Packaging", claude_model),
        ]

        for step_id, step_name, ai_model in step_definitions:
            if step_id not in self.steps:
                self.steps[step_id] = StepInfo(
                    step_id=step_id,
                    step_name=step_name,
                    ai_model=ai_model
                )

    def update_step_status(self, step_id: str, status: StepStatus,
                          error_message: Optional[str] = None,
                          output_documents: Optional[List[str]] = None):
        """更新步骤状态"""
        if step_id not in self.steps:
            raise ValueError(f"Step {step_id} not found")

        step = self.steps[step_id]
        step.status = status

        if status == StepStatus.IN_PROGRESS:
            step.started_at = datetime.now()
        elif status in [StepStatus.COMPLETED, StepStatus.FAILED]:
            step.completed_at = datetime.now()

        if error_message:
            step.error_message = error_message

        if output_documents:
            step.output_documents = output_documents

        self.updated_at = datetime.now()

    def get_next_step(self) -> Optional[str]:
        """获取下一个待执行的步骤 (v7.0 - 25 steps including Step 3-4)"""
        step_order = [
            "step_s_1",  # NEW v6.0
            "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
            "step_3_init", "step_3_exec",
            "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
        ]

        for step_id in step_order:
            if self.steps[step_id].status == StepStatus.PENDING:
                return step_id
        return None

    def get_progress(self) -> float:
        """获取项目进度（0-100）"""
        total_steps = len(self.steps)
        completed_steps = sum(
            1 for step in self.steps.values()
            if step.status == StepStatus.COMPLETED
        )
        return (completed_steps / total_steps) * 100 if total_steps > 0 else 0

    def is_step_0_completed(self) -> bool:
        """检查 Step 0 是否完成"""
        return all(
            self.steps[step_id].status == StepStatus.COMPLETED
            for step_id in ["step_0_1", "step_0_2"]
        )

    def is_step_1_completed(self) -> bool:
        """检查 Step 1 是否完成 (v7 - split into S1a/S1b/S1c + renamed S3b)"""
        return all(
            self.steps[step_id].status == StepStatus.COMPLETED
            for step_id in ["step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5"]
        )

    def is_step_2_completed(self) -> bool:
        """检查 Step 2 是否完成 (v4.0 - includes 2.0 and 2.4b)"""
        return all(
            self.steps[step_id].status == StepStatus.COMPLETED
            for step_id in ["step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5"]
        )

    def can_proceed_to_step_2(self) -> bool:
        """检查是否可以进入 Step 2（Gate 1.5 必须通过）"""
        return self.gate_1_5_passed

    def can_proceed_to_step_3(self) -> bool:
        """检查是否可以进入 Step 3（Gate 2 必须通过）"""
        return self.gate_2_passed

    def is_step_3_completed(self) -> bool:
        """检查 Step 3 是否完成"""
        return all(
            self.steps[step_id].status == StepStatus.COMPLETED
            for step_id in ["step_3_init", "step_3_exec"]
            if step_id in self.steps
        )

    def is_step_4_completed(self) -> bool:
        """检查 Step 4 是否完成"""
        return all(
            self.steps[step_id].status == StepStatus.COMPLETED
            for step_id in ["step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package"]
            if step_id in self.steps
        )


class ProjectCreate(BaseModel):
    """创建项目的请求模型"""
    project_name: str = Field(..., description="项目名称")
    topic: str = Field(..., description="研究主题")
    target_venue: str = Field(..., description="目标期刊")
    research_type: ResearchType = Field(..., description="研究类型")
    data_status: DataStatus = Field(..., description="数据状态")
    hard_constraints: List[str] = Field(..., description="硬约束")
    time_budget: Optional[str] = Field(default=None, description="时间预算")
    keywords: List[str] = Field(..., description="关键词")
    project_context: Optional[str] = Field(default=None, description="项目背景")
    rigor_profile: Optional[str] = Field(default="top_journal", description="研究强度档位（top_journal/fast_track）")


class ProjectUpdate(BaseModel):
    """更新项目的请求模型"""
    project_name: Optional[str] = None
    status: Optional[ProjectStatus] = None
    current_step: Optional[str] = None


class ProjectResponse(BaseModel):
    """项目响应模型"""
    project: Project
    progress: float
    next_step: Optional[str]

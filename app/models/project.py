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
    gate_1_25_passed: bool = Field(default=False, description="Gate 1.25 是否通过（Topic Alignment）")
    gate_1_5_passed: bool = Field(default=False, description="Gate 1.5 是否通过（Killer Prior）")
    gate_1_6_passed: bool = Field(default=False, description="Gate 1.6 是否通过（Reference QA）")
    gate_2_passed: bool = Field(default=False, description="Gate 2 是否通过")

    # Gate 检查结果 (v4.0 - 存储完整的检查结果)
    gate_results: Dict[str, Any] = Field(default_factory=dict, description="Gate 检查结果字典")

    # v6.0 Phase 3: Metadata for clarity score and bootloader decision
    metadata: Dict[str, Any] = Field(default_factory=dict, description="项目元数据（clarity_score, bootloader_decision等）")

    def __init__(self, **data):
        super().__init__(**data)
        # 初始化所有步骤
        if not self.steps:
            self._initialize_steps()

    def _initialize_steps(self):
        """初始化所有步骤 (v6.0 - 17 steps)"""
        # 从配置中获取实际使用的模型名称
        openai_model = settings.openai_model
        gemini_model = settings.gemini_model

        step_definitions = [
            # S-1 Bootloader (NEW v6.0)
            ("step_s_1", "Fuzzy Bootloader", gemini_model),
            # Step 0 - Project Bootstrapping
            ("step_0_1", "Project Intake Card", openai_model),
            ("step_0_2", "Venue Taste Primer", gemini_model),
            # Step 1 - Deep Research & Topic Freeze
            ("step_1_1", "Broad Deep Research", gemini_model),
            ("step_1_1b", "Reference QA", gemini_model),  # NEW v4.0
            ("step_1_2", "Topic Decision & Draft Claim Set", openai_model),
            ("step_1_2b", "Topic Alignment Check", openai_model),  # NEW v4.0
            ("step_1_3", "Killer Prior Check", gemini_model),
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
        ]

        for step_id, step_name, ai_model in step_definitions:
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
        """获取下一个待执行的步骤 (v6.0 - 17 steps)"""
        step_order = [
            "step_s_1",  # NEW v6.0
            "step_0_1", "step_0_2",
            "step_1_1", "step_1_1b", "step_1_2", "step_1_2b", "step_1_3", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5"
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
        """检查 Step 1 是否完成 (v4.0 - includes 1.1b and 1.2b)"""
        return all(
            self.steps[step_id].status == StepStatus.COMPLETED
            for step_id in ["step_1_1", "step_1_1b", "step_1_2", "step_1_2b", "step_1_3", "step_1_4", "step_1_5"]
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

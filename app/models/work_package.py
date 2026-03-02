"""
Work Package 数据模型
Step 3 (Research Execution) 的核心数据结构

WP-based DAG 执行引擎的状态模型
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class WPStatus(str, Enum):
    """Work Package 状态枚举"""
    INIT = "init"
    READY = "ready"
    EXECUTING = "executing"
    REVIEW = "review"
    ITERATING = "iterating"
    SECONDARY_REVIEW = "secondary_review"  # §2.2.4: Secondary Reviewer 审查
    ESCALATED = "escalated"
    RA_PENDING = "ra_pending"
    FROZEN = "frozen"
    FAILED = "failed"


class DeliveryStatus(str, Enum):
    """交付状态枚举 (Step 4)"""
    NOT_STARTED = "not_started"
    COLLECTING = "collecting"
    FIGURES = "figures"
    ASSEMBLING = "assembling"
    CITATION_QA = "citation_qa"
    REPRO_CHECK = "repro_check"
    PACKAGING = "packaging"
    DELIVERED = "delivered"


class DeliveryProfile(str, Enum):
    """交付档案类型"""
    INTERNAL_DRAFT = "internal_draft"
    EXTERNAL_ASSEMBLY_KIT = "external_assembly_kit"


class SubtaskSpec(BaseModel):
    """Subtask 规格定义"""
    subtask_id: str = Field(..., description="Subtask ID (e.g., wp1_st1)")
    wp_id: str = Field(..., description="所属 WP ID")
    objective: str = Field(..., description="Subtask 目标")
    inputs: List[str] = Field(default_factory=list, description="输入 artifact 列表")
    outputs: List[str] = Field(default_factory=list, description="输出 artifact 列表")
    acceptance_criteria: List[str] = Field(default_factory=list, description="验收标准")
    allowed_paths: List[str] = Field(default_factory=list, description="允许修改的路径")
    forbidden_paths: List[str] = Field(default_factory=list, description="禁止修改的路径")


class SubtaskResult(BaseModel):
    """Subtask 执行结果

    v1.2 §5.3: 四件套字段改为 List[Any] 以同时接受旧版 str 和新版 Dict 格式。
    新代码应使用 Dict 格式:
      what_changed: [{"path": "...", "change_type": "...", "notes": "..."}]
      commands_ran: [{"cmd": "...", "exit_code": 0, "time_sec": 1.2}]
      open_issues: [{"id": "...", "severity": "...", "desc": "...", "evidence_path": "...", "suggested_next": "..."}]
      artifacts_written: [{"path": "...", "sha256": "..."}]
    """
    subtask_id: str = Field(..., description="Subtask ID")
    status: str = Field(default="pending", description="执行状态 (pending/running/completed/failed/BLOCKED_PREFLIGHT)")
    summary: str = Field(default="", description="执行摘要")
    what_changed: List[Any] = Field(default_factory=list, description="变更列表 (str 或 {path, change_type, notes})")
    commands_ran: List[Any] = Field(default_factory=list, description="命令列表 (str 或 {cmd, exit_code, time_sec})")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="指标数据")
    open_issues: List[Any] = Field(default_factory=list, description="问题列表 (str 或 {id, severity, desc, evidence_path, suggested_next})")
    artifacts_written: List[Any] = Field(default_factory=list, description="产物列表 (str 或 {path, sha256})")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    preflight_result: Optional[Dict[str, Any]] = Field(default=None, description="Pre-flight 检查结果")
    # v1.2 DevSpec §8: token 追踪
    token_usage: Optional[Dict[str, int]] = Field(default=None, description="Token 使用量 (prompt_tokens, completion_tokens, total_tokens)")


class WPSpec(BaseModel):
    """Work Package 规格定义"""
    wp_id: str = Field(..., description="WP ID (e.g., wp1)")
    name: str = Field(..., description="WP 名称")
    owner: str = Field(default="chatgpt", description="执行者 (chatgpt/claude/gemini/human)")
    reviewer: str = Field(default="gemini", description="审查者 (chatgpt/claude/gemini)")
    depends_on: List[str] = Field(default_factory=list, description="依赖的 WP ID 列表")
    gate_criteria: List[str] = Field(default_factory=list, description="WP 验收门禁标准")
    subtasks: List[SubtaskSpec] = Field(default_factory=list, description="Subtask 列表")
    max_iterations: int = Field(default=2, description="最大迭代次数 (v1.2 §7.2: 2 轮 review-fix 循环)")
    # v1.2 DevSpec §10 扩展字段
    subtask_decomposition: Optional[str] = Field(default="manual", description="Subtask 分解模式 (manual|auto)")
    escalation_policy: Optional[str] = Field(default="default", description="升级策略 (default|skip_gemini)")
    ra_required: Optional[bool] = Field(default=True, description="是否需要 RA 评估")
    max_subtask_tokens: Optional[int] = Field(default=None, description="单个 subtask 最大 token 数")


class WPState(BaseModel):
    """Work Package 运行时状态"""
    wp_id: str = Field(..., description="WP ID")
    status: WPStatus = Field(default=WPStatus.INIT, description="WP 状态")
    owner: str = Field(default="chatgpt", description="执行者")
    reviewer: str = Field(default="gemini", description="审查者")
    iteration_count: int = Field(default=0, description="当前迭代次数")
    subtask_results: Dict[str, SubtaskResult] = Field(default_factory=dict, description="Subtask 结果")
    gate_result: Optional[Dict[str, Any]] = Field(default=None, description="WP Gate 检查结果")
    escalation_history: List[Dict[str, Any]] = Field(default_factory=list, description="升级历史")
    frozen_at: Optional[datetime] = Field(default=None, description="冻结时间")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    error_message: Optional[str] = Field(default=None, description="错误信息")
    # v1.2 §5.2 补齐字段
    frozen_artifacts: List[str] = Field(default_factory=list, description="冻结后的产物路径列表")
    ra_result: Optional[str] = Field(default=None, description="RA 结果 (ADVANCE/POLISH/BLOCK/PENDING)")
    ra_polish_todos: List[str] = Field(default_factory=list, description="POLISH 时的待办列表")
    current_subtask: Optional[str] = Field(default=None, description="当前执行的 subtask ID")

    @property
    def subtasks_completed(self) -> int:
        return sum(1 for r in self.subtask_results.values() if r.status == "completed")

    @property
    def subtasks_remaining(self) -> int:
        return sum(1 for r in self.subtask_results.values() if r.status != "completed")


class DeliveryState(BaseModel):
    """Step 4 交付状态

    v1.2 §5.2: delivery_profile 为 spec 规定字段名，profile 保留向后兼容。
    """
    status: DeliveryStatus = Field(default=DeliveryStatus.NOT_STARTED, description="交付状态")
    profile: DeliveryProfile = Field(default=DeliveryProfile.EXTERNAL_ASSEMBLY_KIT, description="交付档案类型")
    manifest: List[str] = Field(default_factory=list, description="交付清单")
    citation_issues: List[str] = Field(default_factory=list, description="引用问题")
    package_path: Optional[str] = Field(default=None, description="打包路径")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    # v1.2 §5.2 补齐字段
    missing_deliverables: List[str] = Field(default_factory=list, description="缺失的交付物列表")

    @property
    def delivery_profile(self) -> DeliveryProfile:
        """§5.2 spec 字段名别名，读取 profile"""
        return self.profile

    @delivery_profile.setter
    def delivery_profile(self, value: DeliveryProfile):
        """§5.2 spec 字段名别名，写入 profile"""
        self.profile = value


class ExecutionState(BaseModel):
    """Step 3 执行状态（state.json 的根模型）"""
    project_id: str = Field(..., description="项目 ID")
    state_version: int = Field(default=1, description="状态版本号（乐观锁）")
    wp_specs: Dict[str, WPSpec] = Field(default_factory=dict, description="WP 规格定义")
    wp_states: Dict[str, WPState] = Field(default_factory=dict, description="WP 运行时状态")
    wp_dag: Dict[str, List[str]] = Field(default_factory=dict, description="WP 依赖 DAG (wp_id -> depends_on)")
    delivery_state: DeliveryState = Field(default_factory=DeliveryState, description="交付状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    # v1.2 §5.2 补齐字段
    last_writer: Optional[Dict[str, Any]] = Field(default=None, description="最后写入者 (host/pid/worker_id)")
    current_phase: str = Field(default="step3_execution", description="当前阶段 (step3_execution/step4_delivery)")
    plan_frozen_ref: Optional[str] = Field(default=None, description="冻结计划引用路径")

    def get_ready_wps(self) -> List[str]:
        """获取依赖已满足、可以执行的 WP 列表"""
        ready = []
        for wp_id, wp_state in self.wp_states.items():
            if wp_state.status not in (WPStatus.INIT, WPStatus.READY):
                continue
            deps = self.wp_dag.get(wp_id, [])
            all_deps_frozen = all(
                self.wp_states.get(dep, WPState(wp_id=dep)).status == WPStatus.FROZEN
                for dep in deps
            )
            if all_deps_frozen:
                ready.append(wp_id)
        return ready

    def all_wps_frozen(self) -> bool:
        """检查是否所有 WP 都已冻结"""
        return all(
            ws.status == WPStatus.FROZEN
            for ws in self.wp_states.values()
        )

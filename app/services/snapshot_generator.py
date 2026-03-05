"""
Snapshot Generator
v1.2 DevSpec §12.3 - AGENTS.md 动态 section 生成 + 自动更新
v7.1: AgentsMdConfig + rigor_profile/north_star/red_lines/role_assignments

生成 AGENTS.md 的动态 section（< 2000 tokens），在状态转移时自动更新。
触发时机: E0完成 / subtask完成 / WP冻结 / WP升级 / RA完成
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AgentsMdConfig(BaseModel):
    """v7.1 AGENTS.md 初始化配置"""
    project_overview: str = Field(default="SignalPass 多模型科研 SOP 项目", description="项目概述")
    rigor_profile: str = Field(default="top_journal", description="研究强度档位")
    north_star: str = Field(default="", description="北极星问题")
    red_lines: List[str] = Field(default_factory=lambda: [
        "不做学术不端/代写代交付",
        "不绕过限额/不轮询多 Key",
        "不把闭源模型输出作为可售训练集",
    ], description="红线列表")
    role_assignments: Dict[str, str] = Field(default_factory=lambda: {
        "ChatGPT": "PI / Architect — formalization, risk control, gates",
        "Gemini": "Intelligence Officer / Editor — deep research, red-team",
        "Claude": "Executor — code generation, subtask execution",
    }, description="角色分权表")
AGENTS_MD_TEMPLATE = """# AGENTS.md — SignalPass Project Rules
## Project Overview
{project_overview}
## Red Lines
1. 不做学术不端/代写代交付
2. 不绕过限额/不轮询多 Key
3. 不把闭源模型输出作为可售训练集
## Role Boundaries
- **executor**: 写代码、跑测试、生成 artifacts（详见 sop/agents/executor.md）
- **reviewer**: 只读审阅，输出 PASS/FAIL + issues（详见 sop/agents/reviewer.md）
- **boundary-checker**: 只读 git diff，输出 violations（详见 sop/agents/boundary-checker.md）
- **snapshot-writer**: 只写 AGENTS.md 动态 section（详见 sop/agents/snapshot-writer.md）
- **assembly-builder**: 读 frozen/，写 delivery/（详见 sop/agents/assembly-builder.md）
- **diagnostician**: Gemini 专用，escalation 诊断（详见 sop/agents/diagnostician.md）
## Available Commands
- `init-wp` → 初始化 WP（sop/commands/init-wp.md）
- `execute-subtask` → 执行子任务（sop/commands/execute-subtask.md）
- `self-test` → subtask 完成后自检（sop/commands/self-test.md）
- `submit-review` → 提交 review（sop/commands/submit-review.md）
- `fix-issues` → 修复 review 问题（sop/commands/fix-issues.md）
- `freeze-wp` → 冻结 WP（sop/commands/freeze-wp.md）
- `assemble-delivery` → 组装交付包（sop/commands/assemble-delivery.md）
## Quality Standards
- Gate = binary PASS/FAIL
- 验证器通过 + 代码能跑 + 维度对 + 趋势对 + 文件齐
- 不允许"作弊修复"：删断言/跳测试/硬编码答案
## Output Format
所有模型输出必须是 SubtaskResult JSON（schema 见 DevSpec §5.3），不是自由文本。
## Frozen Files
以下路径不可修改（hook 自动检查）：
- `artifacts/04_frozen/` 下所有文件
- 任何 `FROZEN_MANIFEST.json` 中列出的文件
## Key Rules
- 详见 `sop/rules/` 目录
- MEMORY.md 中的 [LEARN:tag] 条目必须在相关任务中遵守
<!-- AUTO-GENERATED: Do not edit below this line. Updated by Orchestra snapshot_generator -->
## Current Status
{dynamic_section}
<!-- END AUTO-GENERATED -->
"""

AGENTS_MD_V71_TEMPLATE = """# AGENTS.md — SignalPass Project Rules (v7.1)

## Project Overview
{project_overview}

## Rigor Profile
- **Level**: {rigor_profile}

## North Star
{north_star}

## Red Lines
{red_lines}

## Role Assignments
{role_assignments}

## Quality Standards
- Gate = binary PASS/FAIL
- 不允许"作弊修复"：删断言/跳测试/硬编码答案
- MEMORY.md 中的 [LEARN:tag] 条目必须在相关任务中遵守

<!-- AUTO-GENERATED: Do not edit below this line. Updated by Orchestra snapshot_generator -->
## Current Status
{dynamic_section}
<!-- END AUTO-GENERATED -->
"""
DYNAMIC_SECTION_EMPTY = """- **Phase**: Not started
- **Active WPs**: None
- **Last completed**: None
- **Blockers**: None
- **Next action**: Initialize project
- **Cross-model need**: None
- **RA pending**: None"""


class SnapshotGenerator:
    """
    AGENTS.md 动态 section 生成器
    功能:
    - 从 state.json + 最新 subtask results 生成动态 section
    - 替换 AGENTS.md 中 AUTO-GENERATED 区间
    - 控制动态 section < 2000 tokens
    """
    def __init__(self, project_path: str, *, slots: list = None, trajectory_store=None):
        self.project_path = Path(project_path)
        self.agents_md_path = self.project_path / "AGENTS.md"
        self.slots = slots or []
        self.trajectory_store = trajectory_store
    def initialize_agents_md(self, project_overview: str = "SignalPass 多模型科研 SOP 项目") -> None:
        """
        首次创建 AGENTS.md
        Args:
            project_overview: 项目概述（一句话）
        """
        if self.agents_md_path.exists():
            logger.info(f"AGENTS.md already exists at {self.agents_md_path}")
            return
        content = AGENTS_MD_TEMPLATE.format(
            project_overview=project_overview,
            dynamic_section=DYNAMIC_SECTION_EMPTY
        )
        self.agents_md_path.write_text(content, encoding="utf-8")
        logger.info(f"Initialized AGENTS.md at {self.agents_md_path}")

    def initialize_agents_md_v71(self, config: Optional[AgentsMdConfig] = None) -> None:
        """
        v7.1: 创建 AGENTS.md（含 rigor_profile, north_star, red_lines, role_assignments）

        Args:
            config: AgentsMdConfig 配置，None 则使用默认值
        """
        if self.agents_md_path.exists():
            logger.info(f"AGENTS.md already exists at {self.agents_md_path}")
            return

        config = config or AgentsMdConfig()

        # Format red lines as numbered list
        red_lines_text = "\n".join(
            f"{i+1}. {line}" for i, line in enumerate(config.red_lines)
        )

        # Format role assignments as table
        role_lines = ["| Model | Role |", "|-------|------|"]
        for model, role in config.role_assignments.items():
            role_lines.append(f"| {model} | {role} |")
        role_assignments_text = "\n".join(role_lines)

        north_star_text = config.north_star if config.north_star else "(未设定 — 将在 Step 0.1 后填充)"

        content = AGENTS_MD_V71_TEMPLATE.format(
            project_overview=config.project_overview,
            rigor_profile=config.rigor_profile,
            north_star=north_star_text,
            red_lines=red_lines_text,
            role_assignments=role_assignments_text,
            dynamic_section=DYNAMIC_SECTION_EMPTY,
        )
        self.agents_md_path.write_text(content, encoding="utf-8")
        logger.info(f"Initialized AGENTS.md (v7.1) at {self.agents_md_path}")

    def generate_agents_md_dynamic_section(
        self,
        state: Dict[str, Any],
        active_wp_results: Optional[List[Dict]] = None,
        next_task: Optional[Dict] = None,
        ra_pending: Optional[Dict] = None
    ) -> str:
        """
        生成 AGENTS.md 的动态 section
        约束: < 2000 tokens (约 6000 chars)

        v1.2 DevSpec §12.3 标准函数名

        Args:
            state: state.json 的完整内容
            active_wp_results: 活跃 WP 的最新 subtask results
            next_task: 下一个待执行的任务
            ra_pending: 等待 RA 的 WP 信息
        Returns:
            动态 section 的 Markdown 文本
        """
        lines = []
        # Phase
        phase = state.get("current_phase", "unknown")
        lines.append(f"- **Phase**: {phase}")
        # Active WPs
        wp_states = state.get("wp_states", {})
        active_wps = []
        frozen_wps = []
        blocked_wps = []
        last_frozen = None
        last_frozen_time = None
        for wp_id, wp_state in wp_states.items():
            status = wp_state.get("status", "unknown")
            if status in ("executing", "review", "iterating", "ra_pending"):
                active_wps.append(f"{wp_id} ({status.upper()})")
            elif status == "frozen":
                frozen_wps.append(wp_id)
                frozen_at = wp_state.get("frozen_at")
                if frozen_at and (last_frozen_time is None or frozen_at > last_frozen_time):
                    last_frozen = wp_id
                    last_frozen_time = frozen_at
            elif status in ("escalated", "failed", "blocked"):
                blocked_wps.append(f"{wp_id} ({status.upper()})")
        lines.append(f"- **Active WPs**: {', '.join(active_wps) if active_wps else 'None'}")
        # Last completed
        if last_frozen:
            time_str = last_frozen_time[:10] if last_frozen_time else "unknown"
            lines.append(f"- **Last completed**: {last_frozen} FROZEN ({time_str})")
        else:
            lines.append(f"- **Last completed**: None")
        # Blockers
        if blocked_wps:
            lines.append(f"- **Blockers**: {', '.join(blocked_wps)}")
        else:
            lines.append(f"- **Blockers**: None")
        # Next action
        if next_task:
            wp_id = next_task.get("wp_id", "unknown")
            subtask = next_task.get("subtask_id", "")
            desc = next_task.get("description", "")
            lines.append(f"- **Next action**: Execute {wp_id} {subtask} ({desc})")
        else:
            lines.append(f"- **Next action**: Waiting for task assignment")
        # Cross-model need
        cross_model_needs = []
        for wp_id, wp_state in wp_states.items():
            reviewer = wp_state.get("reviewer", "")
            status = wp_state.get("status", "")
            if status == "review" and reviewer:
                cross_model_needs.append(f"{reviewer} review of {wp_id}")
        if cross_model_needs:
            lines.append(f"- **Cross-model need**: {'; '.join(cross_model_needs)}")
        else:
            lines.append(f"- **Cross-model need**: None")
        # RA pending
        ra_pending_wps = [
            wp_id for wp_id, ws in wp_states.items()
            if ws.get("status") == "ra_pending"
        ]
        if ra_pending_wps:
            lines.append(f"- **RA pending**: {', '.join(ra_pending_wps)}")
        else:
            lines.append(f"- **RA pending**: None")
        # Active WP details (brief)
        if active_wp_results:
            lines.append("")
            lines.append("### Active WP Details")
            for result in active_wp_results[:3]:  # Max 3 to control tokens
                wp_id = result.get("wp_id", "unknown")
                summary = result.get("summary", "")[:200]
                metrics = result.get("metrics", {})
                open_issues = result.get("open_issues", [])
                lines.append(f"- **{wp_id}**: {summary}")
                if metrics:
                    metric_strs = [f"{k}={v.get('value', '?')}" for k, v in list(metrics.items())[:3]]
                    lines.append(f"  - Metrics: {', '.join(metric_strs)}")
                if open_issues:
                    lines.append(f"  - Open issues: {len(open_issues)}")
        # Delivery state (if in Step 4)
        delivery = state.get("delivery_state", {})
        if delivery.get("status") and delivery["status"] != "not_started":
            lines.append("")
            lines.append("### Delivery Status")
            lines.append(f"- Status: {delivery['status']}")
            lines.append(f"- Profile: {delivery.get('delivery_profile', 'unknown')}")
            missing = delivery.get("missing_deliverables", [])
            if missing:
                lines.append(f"- Missing: {', '.join(missing[:5])}")
        # ── Slot status (Phase 3) ──
        if self.slots:
            lines.append("")
            lines.append("### Slot Status")
            for slot_obj in self.slots:
                try:
                    st = slot_obj.get_status()
                    slot_name = st.get("slot", "unknown")
                    slot_status = st.get("status", "unknown")
                    detail_parts = [
                        f"{k}={v}" for k, v in st.items()
                        if k not in ("slot", "status") and v is not None
                    ]
                    detail = ", ".join(detail_parts[:4]) if detail_parts else ""
                    lines.append(f"- **{slot_name}** [{slot_status}]: {detail}")
                except Exception:
                    logger.debug("Slot get_status() failed (non-blocking)")
        # ── Trajectory summary (Phase 3) ──
        if self.trajectory_store:
            try:
                stats = self.trajectory_store.get_stats()
                total = stats.get("total_records", 0)
                if total > 0:
                    lines.append("")
                    lines.append("### Trajectory Summary")
                    lines.append(f"- Total records: {total}")
                    by_outcome = stats.get("by_outcome", {})
                    resolved = by_outcome.get("resolved", 0) + by_outcome.get("workaround", 0)
                    rate = f"{resolved/total*100:.0f}%" if total else "N/A"
                    lines.append(f"- Resolution rate: {rate}")
                    by_cat = stats.get("by_category", {})
                    if by_cat:
                        top = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:3]
                        top_str = ", ".join(f"{k}({v})" for k, v in top)
                        lines.append(f"- Top issues: {top_str}")
            except Exception:
                logger.debug("Trajectory get_stats() failed (non-blocking)")
        section = "\n".join(lines)
        # Token budget check (< 2000 tokens ≈ 6000 chars)
        if len(section) > 6000:
            section = section[:5900] + "\n- **[truncated for token budget]**"
            logger.warning("Dynamic section truncated to fit token budget")
        return section

    def generate_dynamic_section(
        self,
        state: Dict[str, Any],
        active_wp_results: Optional[List[Dict]] = None,
        next_task: Optional[Dict] = None,
        ra_pending: Optional[Dict] = None
    ) -> str:
        """
        Backward compatibility alias for generate_agents_md_dynamic_section

        Deprecated: Use generate_agents_md_dynamic_section instead
        """
        return self.generate_agents_md_dynamic_section(
            state=state,
            active_wp_results=active_wp_results,
            next_task=next_task,
            ra_pending=ra_pending
        )
    
    def update_agents_md(self, dynamic_section: str) -> None:
        """
        替换 AGENTS.md 中 AUTO-GENERATED 区间的内容
        Args:
            dynamic_section: 新的动态 section 内容
        """
        if not self.agents_md_path.exists():
            logger.warning("AGENTS.md not found, initializing first")
            self.initialize_agents_md()
        content = self.agents_md_path.read_text(encoding="utf-8")
        start_marker = "<!-- AUTO-GENERATED: Do not edit below this line. Updated by Orchestra snapshot_generator -->"
        end_marker = "<!-- END AUTO-GENERATED -->"
        if start_marker in content and end_marker in content:
            start_idx = content.index(start_marker) + len(start_marker)
            end_idx = content.index(end_marker)
            new_content = (
                content[:start_idx] + "\n"
                "## Current Status\n"
                f"{dynamic_section}\n"
                + content[end_idx:]
            )
            self.agents_md_path.write_text(new_content, encoding="utf-8")
            logger.info("Updated AGENTS.md dynamic section")
        else:
            logger.warning("AUTO-GENERATED markers not found in AGENTS.md, appending")
            content += f"\n{start_marker}\n## Current Status\n{dynamic_section}\n{end_marker}\n"
            self.agents_md_path.write_text(content, encoding="utf-8")
    def get_agents_md_content(self) -> str:
        """读取完整 AGENTS.md 内容"""
        if not self.agents_md_path.exists():
            return ""
        return self.agents_md_path.read_text(encoding="utf-8")
    def get_dynamic_section(self) -> str:
        """读取当前动态 section 内容"""
        if not self.agents_md_path.exists():
            return DYNAMIC_SECTION_EMPTY
        content = self.agents_md_path.read_text(encoding="utf-8")
        start_marker = "<!-- AUTO-GENERATED: Do not edit below this line. Updated by Orchestra snapshot_generator -->"
        end_marker = "<!-- END AUTO-GENERATED -->"
        if start_marker in content and end_marker in content:
            start_idx = content.index(start_marker) + len(start_marker)
            end_idx = content.index(end_marker)
            return content[start_idx:end_idx].strip()
        return DYNAMIC_SECTION_EMPTY
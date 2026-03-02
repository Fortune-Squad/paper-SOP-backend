"""
WP Execution Engine
Step 3 的核心执行引擎

管理 WP DAG 的解析、执行、审查和冻结流程。
E0 → E1 → E2 → E3 → (E4 → E3)* → E6
"""
import logging
import yaml
import json
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

from app.models.work_package import (
    ExecutionState, WPSpec, WPState, WPStatus,
    SubtaskSpec, SubtaskResult, DeliveryState
)
from app.models.gate import GateVerdict
from app.services.state_store import StateStore
from app.services.boundary_checker import ArtifactBoundaryChecker
from app.services.wp_gate_checker import WPGateChecker
from app.services.hook_runner import HookRunner
from app.services.ai_client import ChatGPTClient, GeminiClient
from app.prompts.step3_prompts import (
    render_wp_init_prompt,
    render_execute_prompt,
    render_review_acceptance_prompt,
    render_review_fix_prompt,
    render_diagnose_prompt,
    render_session_resume_prompt,
)
from app.utils.conversation_logger import conversation_logger
from app.services.memory_store import MemoryStore
from app.services.session_logger import SessionLogger
from app.services.snapshot_generator import SnapshotGenerator
from app.services.readiness_assessor import ReadinessAssessor, RAVerdict
from app.config import settings

logger = logging.getLogger(__name__)


class WPExecutionEngine:
    """
    WP 执行引擎

    Step 3 的核心组件，管理 WP 的生命周期：
    E0 (Init) → E1 (Execute subtasks) → E2 (Boundary check) →
    E3 (Review) → E4 (Fix, optional) → E6 (Freeze)
    """

    def __init__(
        self,
        project_id: str,
        state_store: Optional[StateStore] = None,
        chatgpt_client: Optional[ChatGPTClient] = None,
        gemini_client: Optional[GeminiClient] = None,
        claude_client=None,
        wp_gate_checker: Optional[WPGateChecker] = None,
    ):
        self.project_id = project_id
        self.state_store = state_store or StateStore()
        self.chatgpt_client = chatgpt_client or ChatGPTClient()
        self.gemini_client = gemini_client or GeminiClient()
        # v1.2: Claude client — prefer injected, else create, else fallback to chatgpt
        if claude_client is not None:
            self.claude_client = claude_client
        else:
            try:
                from app.services.ai_client import create_claude_client
                _claude = create_claude_client()
                self.claude_client = _claude if _claude.client else self.chatgpt_client
            except Exception:
                self.claude_client = self.chatgpt_client
        self.wp_gate_checker = wp_gate_checker or WPGateChecker()

        # v1.2 DevSpec services
        project_path = str(Path(settings.projects_path) / project_id)
        self.memory_store = MemoryStore(project_path)
        self.session_logger = SessionLogger(project_path)
        self.snapshot_generator = SnapshotGenerator(project_path)
        self.readiness_assessor = ReadinessAssessor(project_path)

    def _get_ai_client(self, owner: str):
        """根据 owner 返回对应的 AI 客户端"""
        owner_lower = owner.lower()
        if owner_lower in ("gemini", "gemini-2.0-flash"):
            return self.gemini_client
        elif owner_lower.startswith("claude") or owner_lower in ("claude", "claude-sonnet", "claude-opus", "claude-sonnet-4-6"):
            return self.claude_client
        return self.chatgpt_client

    async def initialize(self, plan_frozen_content: str, execution_order_content: str = "") -> ExecutionState:
        """
        E0: 解析 PlanFrozen → WP DAG → state.json

        Args:
            plan_frozen_content: 04_Research_Plan_FROZEN.md 内容
            execution_order_content: 04_Execution_Order.md 内容

        Returns:
            ExecutionState: 初始化的执行状态
        """
        logger.info(f"E0: Initializing WP DAG for project {self.project_id}")

        # 调用 ChatGPT 解析 PlanFrozen → WP 注册表
        prompt = render_wp_init_prompt(plan_frozen_content, execution_order_content)
        response = await self.chatgpt_client.chat(
            prompt,
            system_prompt="You are a Research Project Manager decomposing a frozen plan into Work Packages.",
        )

        # 记录对话
        conversation_logger.log_conversation(
            project_id=self.project_id,
            step_id="step_3_init",
            model="chatgpt",
            system_prompt="WP DAG initialization",
            user_prompt=prompt[:500] + "...",
            response=response[:1000] + "..."
        )

        # 解析 YAML 响应
        wp_specs, wp_dag = self._parse_wp_registry(response)

        # 构建初始状态
        wp_states = {}
        for wp_id, spec in wp_specs.items():
            wp_states[wp_id] = WPState(
                wp_id=wp_id,
                status=WPStatus.INIT,
                owner=spec.owner,
                reviewer=spec.reviewer,
            )

        state = ExecutionState(
            project_id=self.project_id,
            state_version=1,
            wp_specs=wp_specs,
            wp_states=wp_states,
            wp_dag=wp_dag,
        )

        # 标记无依赖的 WP 为 READY
        for wp_id in state.get_ready_wps():
            state.wp_states[wp_id].status = WPStatus.READY

        # 保存 state.json
        self.state_store.save_atomic(self.project_id, state)
        logger.info(f"E0: Created {len(wp_specs)} WPs with DAG")

        # v1.2: Initialize AGENTS.md + MEMORY.md + session log
        try:
            self.memory_store.initialize()
            from app.services.snapshot_generator import AgentsMdConfig
            self.snapshot_generator.initialize_agents_md_v71(AgentsMdConfig(
                project_overview=f"Project {self.project_id} - {len(wp_specs)} WPs initialized",
            ))
            wp_results = [{"wp_id": wid, "status": ws.status.value} for wid, ws in state.wp_states.items()]
            ready_wps = state.get_ready_wps()
            next_task = {"wp_id": ready_wps[0]} if ready_wps else None
            dynamic = self.snapshot_generator.generate_agents_md_dynamic_section(
                state={"phase": "E0_INIT_COMPLETE", "total_wps": len(wp_specs)},
                active_wp_results=wp_results,
                next_task=next_task,
            )
            self.snapshot_generator.update_agents_md(dynamic)
            self.session_logger.create_session(
                goal=f"E0: Initialize WP DAG ({len(wp_specs)} WPs)",
                approach="Parse PlanFrozen → WP registry → state.json",
            )
            logger.info("v1.2: AGENTS.md, MEMORY.md, session_log initialized")
        except Exception as e:
            logger.warning(f"v1.2 initialization partial failure (non-blocking): {e}")

        # v1.2 §4.4 Exec-Loop1: Checkpoint — 通知确认 WP DAG 和执行顺序
        try:
            from app.services.hil_service import HILService
            from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
            hil = HILService()
            await hil.create_ticket(HILTicketCreate(
                project_id=self.project_id,
                step_id="step_3_init",
                question_type=QuestionType.VALIDATION,
                question=f"请确认 WP DAG 和执行顺序 ({len(wp_specs)} WPs)",
                context={"checkpoint": "Exec-Loop1", "wp_count": len(wp_specs)},
                priority=TicketPriority.MEDIUM,
                blocking=False,
            ))
        except Exception as cp_err:
            logger.debug(f"v1.2: Exec-Loop1 checkpoint HIL failed (non-blocking): {cp_err}")

        return state

    async def get_ready_wps(self) -> List[str]:
        """查找依赖已满足的 WP"""
        state = self.state_store.load(self.project_id)
        return state.get_ready_wps()

    async def execute_wp(self, wp_id: str) -> WPState:
        """
        E1→E2: 执行 WP 的所有 subtask

        Args:
            wp_id: WP ID

        Returns:
            WPState: 更新后的 WP 状态
        """
        state = self.state_store.load(self.project_id)
        wp_spec = state.wp_specs.get(wp_id)
        if not wp_spec:
            raise ValueError(f"WP {wp_id} not found")

        wp_state = state.wp_states[wp_id]
        if wp_state.status not in (WPStatus.INIT, WPStatus.READY, WPStatus.ITERATING):
            raise ValueError(f"WP {wp_id} is in status {wp_state.status}, cannot execute")

        logger.info(f"E1: Executing WP {wp_id} ({wp_spec.name})")

        # 更新状态为 EXECUTING
        def set_executing(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].status = WPStatus.EXECUTING
            s.wp_states[wp_id].started_at = datetime.now()
            return s
        state = self.state_store.update(self.project_id, set_executing, state.state_version)

        # 执行每个 subtask
        previous_results = ""

        # v1.2 §8.3: Session Resume — 检查是否有已完成的 subtask（断点续跑）
        completed_subtasks = {st_id for st_id, r in wp_state.subtask_results.items() if r.status == "completed"}
        is_resume = len(completed_subtasks) > 0
        if is_resume:
            logger.info(f"Session resume: {len(completed_subtasks)} subtasks already completed for WP {wp_id}")
            # v1.2 §8.2 T2: 构建结构化摘要（what_changed + metrics + open_issues），不传完整 summary
            for st_id, r in wp_state.subtask_results.items():
                if r.status == "completed":
                    structured_summary = f"### {st_id}\n"
                    if r.what_changed:
                        structured_summary += f"What changed: {', '.join(r.what_changed[:5])}\n"  # 最多 5 项
                    if r.metrics:
                        structured_summary += f"Metrics: {str(r.metrics)[:200]}\n"  # 最多 200 字符
                    if r.open_issues:
                        structured_summary += f"Open issues: {', '.join(r.open_issues[:3])}\n"  # 最多 3 项
                    previous_results += structured_summary

        for subtask in wp_spec.subtasks:
            # 跳过已完成的 subtask
            if subtask.subtask_id in completed_subtasks:
                continue

            try:
                # v1.2 §8.3: 断点续跑时使用 session resume prompt
                if is_resume and subtask == next((st for st in wp_spec.subtasks if st.subtask_id not in completed_subtasks), None):
                    try:
                        last_result = list(wp_state.subtask_results.values())[-1] if wp_state.subtask_results else None
                        last_result_str = ""
                        if last_result:
                            last_result_str = f"what_changed: {last_result.what_changed}\nmetrics: {last_result.metrics}\nopen_issues: {last_result.open_issues}"
                        resume_prompt = render_session_resume_prompt(
                            project_summary=f"Project {self.project_id}, WP {wp_id} ({wp_spec.name}), {len(completed_subtasks)}/{len(wp_spec.subtasks)} subtasks done",
                            agents_md_dynamic=self.snapshot_generator.get_dynamic_section() if hasattr(self.snapshot_generator, 'get_dynamic_section') else "",
                            memory_lessons=self.memory_store.get_injection_content(max_tokens=500),
                            last_subtask_result=last_result_str,
                            last_wrapup=self.session_logger.get_latest_wrapup() or "",
                            current_subtask_yaml=yaml.dump(subtask.model_dump(), default_flow_style=False),
                        )
                        client = self._get_ai_client(wp_spec.owner)
                        response = await client.chat(
                            resume_prompt,
                            system_prompt=f"You are a Research Execution Agent resuming WP '{wp_spec.name}'.",
                        )
                        result = SubtaskResult(
                            subtask_id=subtask.subtask_id,
                            status="completed",
                            summary=self._extract_section(response, "Summary"),
                            what_changed=self._extract_list(response, "Artifacts Written"),
                            artifacts_written=self._extract_list(response, "Artifacts Written"),
                            open_issues=self._extract_list(response, "Open Issues"),
                            completed_at=datetime.now(),
                        )
                        is_resume = False  # Only use resume prompt for the first resumed subtask
                    except Exception as resume_err:
                        logger.warning(f"Session resume prompt failed, falling back to normal: {resume_err}")
                        result = await self.execute_subtask(wp_id, subtask.subtask_id, previous_results)
                else:
                    result = await self.execute_subtask(wp_id, subtask.subtask_id, previous_results)

                # v1.2 §8.2 T2: 累积结构化摘要，不传完整 summary
                structured_summary = f"\n### {subtask.subtask_id}\n"
                if result.what_changed:
                    structured_summary += f"What changed: {', '.join(result.what_changed[:5])}\n"
                if result.metrics:
                    structured_summary += f"Metrics: {str(result.metrics)[:200]}\n"
                if result.open_issues:
                    structured_summary += f"Open issues: {', '.join(result.open_issues[:3])}\n"
                previous_results += structured_summary

                # 更新 state
                def update_subtask(s: ExecutionState, st_id=subtask.subtask_id, res=result) -> ExecutionState:
                    s.wp_states[wp_id].subtask_results[st_id] = res
                    return s
                state = self.state_store.update(self.project_id, update_subtask, state.state_version)

                # §2.2.8: 运行所有 post-subtask hooks
                changed = result.what_changed or result.artifacts_written
                if changed:
                    try:
                        def _clean_path(f):
                            """Strip markdown backticks and (created)/(modified) suffixes from AI-generated paths"""
                            p = f if isinstance(f, str) else f.get("path", "")
                            p = p.strip().strip('`')
                            # Remove trailing status like "(created)", "(modified)"
                            import re as _re
                            p = _re.sub(r'\s*\((?:created|modified|deleted|updated)\)\s*$', '', p, flags=_re.IGNORECASE)
                            return p.strip()
                        hook_results = HookRunner.run_all_post_subtask(
                            project_path=str(Path(settings.projects_path) / self.project_id),
                            changed_files=[_clean_path(f) for f in changed],
                            allowed_paths=subtask.allowed_paths,
                            forbidden_paths=subtask.forbidden_paths,
                            step_count=len(wp_state.subtask_results) + 1,
                        )
                        for hr in hook_results:
                            if not hr.passed:
                                logger.warning(f"Hook {hr.hook_name} failed: {hr.message}")
                                if hr.hook_name in ("frozen_guard", "boundary_check"):
                                    raise RuntimeError(f"Hook {hr.hook_name}: {hr.message}")
                    except RuntimeError:
                        raise
                    except Exception as hook_err:
                        logger.debug(f"Hook runner (non-blocking): {hook_err}")

                # §4.2: Boundary check after each subtask
                changed = result.what_changed or result.artifacts_written
                if changed:
                    bc_result = ArtifactBoundaryChecker.check(
                        changed_files=[_clean_path(f) for f in changed],
                        allowed_paths=subtask.allowed_paths,
                        forbidden_paths=subtask.forbidden_paths,
                    )
                    if not bc_result.passed:
                        logger.error(f"Boundary violation in {subtask.subtask_id}: {bc_result.details}")
                        def mark_boundary_fail(s: ExecutionState, st_id=subtask.subtask_id, detail=bc_result.details) -> ExecutionState:
                            r = s.wp_states[wp_id].subtask_results[st_id]
                            r.status = "failed"
                            r.open_issues.append(f"Boundary violation: {detail}")
                            return s
                        state = self.state_store.update(self.project_id, mark_boundary_fail, state.state_version)
                        raise RuntimeError(f"Subtask {subtask.subtask_id} boundary violation: {bc_result.details}")

                # §2.2.3: Subtask gate check
                try:
                    st_gate = await self.wp_gate_checker.check_subtask_gate(subtask, result)
                    if st_gate.verdict != GateVerdict.PASS:
                        logger.warning(f"Subtask gate FAIL for {subtask.subtask_id}: {st_gate.suggestions}")
                        # 不硬阻断，记录到 open_issues，WP 级 gate 会最终判定
                        def add_gate_issue(s: ExecutionState, st_id=subtask.subtask_id, suggestions=st_gate.suggestions) -> ExecutionState:
                            r = s.wp_states[wp_id].subtask_results.get(st_id)
                            if r:
                                r.open_issues.append(f"Subtask gate: {suggestions}")
                            return s
                        state = self.state_store.update(self.project_id, add_gate_issue, state.state_version)
                except Exception as sg_err:
                    logger.debug(f"Subtask gate check (non-blocking): {sg_err}")

                # §4.2 E2: 增量写入 session log
                try:
                    self.session_logger.log_decision(
                        self._current_session_id(),
                        f"Subtask {subtask.subtask_id} completed: {result.status} | artifacts: {len(result.artifacts_written)} | issues: {len(result.open_issues)}"
                    )
                except Exception as sl_err:
                    logger.debug(f"Session log write after subtask (non-blocking): {sl_err}")

            except Exception as e:
                logger.error(f"Subtask {subtask.subtask_id} failed: {e}")
                def mark_failed(s: ExecutionState, err=str(e)) -> ExecutionState:
                    s.wp_states[wp_id].status = WPStatus.FAILED
                    s.wp_states[wp_id].error_message = err
                    return s
                self.state_store.update(self.project_id, mark_failed, state.state_version)
                raise

        # 移到 REVIEW 状态
        def set_review(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].status = WPStatus.REVIEW
            return s
        state = self.state_store.update(self.project_id, set_review, state.state_version)

        return state.wp_states[wp_id]

    async def execute_subtask(self, wp_id: str, subtask_id: str, previous_results: str = "") -> SubtaskResult:
        """
        执行单个 subtask

        Args:
            wp_id: WP ID
            subtask_id: Subtask ID
            previous_results: 之前 subtask 的结果摘要

        Returns:
            SubtaskResult: 执行结果
        """
        state = self.state_store.load(self.project_id)
        wp_spec = state.wp_specs[wp_id]
        subtask_spec = next((st for st in wp_spec.subtasks if st.subtask_id == subtask_id), None)
        if not subtask_spec:
            raise ValueError(f"Subtask {subtask_id} not found in WP {wp_id}")

        logger.info(f"E1: Executing subtask {subtask_id}")

        # v7.1: Pre-flight parameter check
        pf_dump = None
        try:
            from app.services.pre_flight_service import PreFlightService
            preflight = PreFlightService(chatgpt_client=self.chatgpt_client)
            subtask_yaml = yaml.dump(subtask_spec.model_dump(), default_flow_style=False)
            pf_result = await preflight.run_full_check(subtask_yaml, previous_results)
            pf_dump = pf_result.model_dump()
            if pf_result.blocked_params:
                logger.warning(f"Pre-flight BLOCKED: {pf_result.blocked_params}")
                from app.services.hil_service import HILService
                from app.models.hil import HILTicketCreate, TicketPriority
                hil = HILService()
                await hil.create_ticket(HILTicketCreate(
                    project_id=self.project_id,
                    question=f"Pre-flight blocked params for {subtask_id}: {pf_result.blocked_params}",
                    context="Parameters need human review before execution",
                    priority=TicketPriority.HIGH,
                    source_step="step_3_exec",
                ))
                return SubtaskResult(
                    subtask_id=subtask_id,
                    status="BLOCKED_PREFLIGHT",
                    summary=f"Pre-flight blocked: {pf_result.blocked_params}",
                    metrics={},
                    open_issues=pf_result.blocked_params,
                    preflight_result=pf_dump,
                )
            if pf_result.revised_params:
                revisions = "\n".join(f"- {k} revised to: {v}" for k, v in pf_result.revised_params.items())
                previous_results = (previous_results or "") + f"\n\n## Pre-flight Revisions\n{revisions}"
                logger.info(f"Pre-flight revised params: {pf_result.revised_params}")
        except Exception as pf_err:
            logger.warning(f"Pre-flight check failed (non-blocking): {pf_err}")

        # 构建 prompt
        # v1.2 §6.2: 注入 MEMORY.md 相关教训
        memory_lessons = ""
        try:
            memory_lessons = self.memory_store.get_injection_content(max_tokens=500)
        except Exception as mem_err:
            logger.debug(f"v1.2: MEMORY.md injection failed (non-blocking): {mem_err}")

        prompt = render_execute_prompt(
            wp_spec_yaml=yaml.dump(wp_spec.model_dump(), default_flow_style=False),
            subtask_spec_yaml=yaml.dump(subtask_spec.model_dump(), default_flow_style=False),
            previous_results=previous_results,
            memory_lessons=memory_lessons,
            wp_id=wp_id,
            subtask_id=subtask_id,
            owner_model=wp_spec.owner,
        )

        # 调用 AI
        client = self._get_ai_client(wp_spec.owner)
        response = await client.chat(
            prompt,
            system_prompt=f"You are a Research Execution Agent working on WP '{wp_spec.name}'.",
        )

        # 记录对话
        conversation_logger.log_conversation(
            project_id=self.project_id,
            step_id=f"step_3_exec_{subtask_id}",
            model=wp_spec.owner,
            system_prompt=f"Execute subtask {subtask_id}",
            user_prompt=prompt[:500] + "...",
            response=response[:1000] + "..."
        )

        # v1.2 §8: 尝试获取 token usage
        token_usage = None
        try:
            if hasattr(client, 'last_token_usage'):
                token_usage = client.last_token_usage
            elif hasattr(client, 'token_usage'):
                token_usage = client.token_usage
        except Exception:
            pass

        # 解析结果
        result = SubtaskResult(
            subtask_id=subtask_id,
            status="completed",
            summary=self._extract_section(response, "Summary"),
            what_changed=self._extract_list(response, "Artifacts Written"),
            artifacts_written=self._extract_list(response, "Artifacts Written"),
            open_issues=self._extract_list(response, "Open Issues"),
            completed_at=datetime.now(),
            preflight_result=pf_dump,
            token_usage=token_usage,
        )

        # v1.2: Log decision + update AGENTS.md
        try:
            self.session_logger.log_decision(
                self._current_session_id(),
                f"Subtask {subtask_id} completed: {result.summary[:80]}"
            )
            state = self.state_store.load(self.project_id)
            wp_results = [{"wp_id": wid, "status": ws.status.value} for wid, ws in state.wp_states.items()]
            dynamic = self.snapshot_generator.generate_agents_md_dynamic_section(
                state={"phase": "E1_EXECUTING", "current_subtask": subtask_id},
                active_wp_results=wp_results,
                next_task={"wp_id": wp_id, "subtask": subtask_id},
            )
            self.snapshot_generator.update_agents_md(dynamic)
        except Exception as e:
            logger.debug(f"v1.2 subtask logging (non-blocking): {e}")

        return result

    async def review_wp(self, wp_id: str) -> Dict[str, Any]:
        """
        E3: 发送给 reviewer 进行验收审查

        Args:
            wp_id: WP ID

        Returns:
            Dict: review 结果
        """
        state = self.state_store.load(self.project_id)
        wp_spec = state.wp_specs[wp_id]
        wp_state = state.wp_states[wp_id]

        logger.info(f"E3: Reviewing WP {wp_id}")

        # 构建 subtask 结果摘要
        results_summary = ""
        for st_id, result in wp_state.subtask_results.items():
            results_summary += f"\n### {st_id}\nStatus: {result.status}\nSummary: {result.summary}\n"

        gate_criteria = "\n".join(f"- {c}" for c in wp_spec.gate_criteria)

        prompt = render_review_acceptance_prompt(
            wp_spec_yaml=yaml.dump(wp_spec.model_dump(), default_flow_style=False),
            subtask_results_summary=results_summary,
            gate_criteria=gate_criteria,
        )

        # 调用 reviewer AI
        reviewer_client = self._get_ai_client(wp_spec.reviewer)
        response = await reviewer_client.chat(
            prompt,
            system_prompt="You are a Research Reviewer performing acceptance review.",
        )

        review_result = WPGateChecker.parse_review_yaml(response)

        # 运行 WP Gate
        gate_result = await self.wp_gate_checker.check_wp_gate(
            project_id=self.project_id,
            wp_id=wp_id,
            wp_spec=wp_spec,
            wp_state=wp_state,
            review_result=review_result,
        )

        # 更新状态
        def update_review(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].gate_result = gate_result.model_dump()
            if gate_result.verdict == GateVerdict.PASS:
                # v1.2: Gate PASS → RA_PENDING (而非直接 FROZEN)
                s.wp_states[wp_id].status = WPStatus.RA_PENDING
            else:
                s.wp_states[wp_id].iteration_count += 1
                if s.wp_states[wp_id].iteration_count >= wp_spec.max_iterations:
                    s.wp_states[wp_id].status = WPStatus.ESCALATED
                else:
                    s.wp_states[wp_id].status = WPStatus.ITERATING
            return s

        self.state_store.update(self.project_id, update_review, state.state_version)

        # v7.1: Auto-trigger RA after Gate PASS
        if gate_result.verdict == GateVerdict.PASS:
            try:
                ra_prompt = self.readiness_assessor.generate_ra_prompt(
                    wp_id=wp_id,
                    agents_md_content=self.snapshot_generator.get_agents_md_content(),
                    memory_md_content=self.memory_store.get_injection_content(max_tokens=500),
                    passed_criteria=str(gate_result.check_items)[:500],
                    artifacts_summary=results_summary[:500],
                )
                ra_response = await self.chatgpt_client.chat(
                    ra_prompt,
                    system_prompt="You are ChatGPT performing a strategic Readiness Assessment.",
                )
                ra_result = self.readiness_assessor.parse_result(ra_response)
                await self.process_ra_verdict(wp_id, ra_result)
                logger.info(f"v7.1: Auto-RA for {wp_id}: {ra_result.verdict.value}")
            except Exception as ra_err:
                logger.warning(f"v7.1: Auto-RA failed for {wp_id} (stays RA_PENDING): {ra_err}")

        # v1.2: Log gate result + update AGENTS.md
        try:
            verdict_str = gate_result.verdict.value
            self.session_logger.log_decision(
                self._current_session_id(),
                f"WP {wp_id} gate: {verdict_str}"
            )
            if gate_result.verdict != GateVerdict.PASS:
                # Gate FAIL → auto-extract lesson to MEMORY.md
                self.memory_store.add_learn_entry(
                    domain="workflow",
                    lesson=f"WP {wp_id} gate FAIL iter={wp_state.iteration_count}: {review_result[:80]}",
                    source="gate_failure"
                )
                # v7.1: Write error pattern to 4-layer memory
                self.memory_store.add_error_pattern(
                    symptom=f"WP {wp_id} gate FAIL (iter {wp_state.iteration_count})",
                    root_cause=str(review_result)[:200],
                    correction=f"Review and fix issues for WP {wp_id}",
                    source_actor="system",
                    wp_id=wp_id,
                )
                # §2.2.7: 检测跨模型冲突
                owner_model = wp_spec.owner
                reviewer_model = wp_spec.reviewer
                if owner_model != reviewer_model:
                    self.memory_store.add_conflict_resolution(
                        wp_id=wp_id,
                        actor_a=owner_model,
                        actor_b=reviewer_model,
                        conflict_desc=f"Owner completed subtasks but reviewer rejected",
                        resolution=f"Entering fix cycle (iter {wp_state.iteration_count})",
                        arbiter="system",
                    )
        except Exception as e:
            logger.debug(f"v1.2 review logging (non-blocking): {e}")

        return {
            "review_result": review_result,
            "gate_result": gate_result.model_dump(),
            "wp_status": gate_result.verdict.value,
        }

    async def iterate_wp(self, wp_id: str, review_issues: str) -> WPState:
        """
        E4: Review-Fix 循环

        Args:
            wp_id: WP ID
            review_issues: Reviewer 指出的问题

        Returns:
            WPState: 更新后的 WP 状态
        """
        state = self.state_store.load(self.project_id)
        wp_spec = state.wp_specs[wp_id]
        wp_state = state.wp_states[wp_id]

        logger.info(f"E4: Iterating WP {wp_id} (iteration {wp_state.iteration_count})")

        allowed_paths = []
        forbidden_paths = []
        previous_output = ""
        for st in wp_spec.subtasks:
            allowed_paths.extend(st.allowed_paths)
            if hasattr(st, 'forbidden_paths'):
                forbidden_paths.extend(st.forbidden_paths)
            result = wp_state.subtask_results.get(st.subtask_id)
            if result:
                previous_output += f"\n### {st.subtask_id}\n{result.summary}\n"

        # v1.2 §6.2: 注入 MEMORY.md 相关教训
        iter_memory_lessons = ""
        try:
            iter_memory_lessons = self.memory_store.get_injection_content(max_tokens=500)
        except Exception:
            pass

        prompt = render_review_fix_prompt(
            wp_spec_yaml=yaml.dump(wp_spec.model_dump(), default_flow_style=False),
            review_issues=review_issues,
            allowed_paths="\n".join(allowed_paths),
            previous_output=previous_output,
            memory_lessons=iter_memory_lessons,
            wp_id=wp_id,
            iteration_count=wp_state.iteration_count,
            forbidden_paths="\n".join(forbidden_paths),
        )

        client = self._get_ai_client(wp_spec.owner)
        response = await client.chat(
            prompt,
            system_prompt="You are a Research Execution Agent fixing reviewer issues.",
        )

        # 更新 subtask 结果
        fix_result = SubtaskResult(
            subtask_id=f"{wp_id}_fix_{wp_state.iteration_count}",
            status="completed",
            summary=self._extract_section(response, "Fixes Applied"),
            completed_at=datetime.now(),
        )

        def update_fix(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].subtask_results[fix_result.subtask_id] = fix_result
            s.wp_states[wp_id].status = WPStatus.REVIEW
            return s

        state = self.state_store.update(self.project_id, update_fix, state.state_version)
        return state.wp_states[wp_id]

    def _get_secondary_reviewer(self, owner: str) -> str:
        """§2.2.4: 选择与 owner 不同的模型作为 secondary reviewer"""
        owner_lower = owner.lower()
        if owner_lower.startswith("claude") or owner_lower == "claude":
            return "chatgpt"
        elif owner_lower in ("chatgpt", "gpt") or owner_lower.startswith("gpt"):
            return "claude"
        else:
            return "chatgpt"

    async def secondary_review_wp(self, wp_id: str) -> Dict[str, Any]:
        """
        E4.5: Secondary Reviewer 审查 (§2.2.4)

        使用与 Primary Owner 不同的模型进行 2 轮 review-fix。

        Args:
            wp_id: WP ID

        Returns:
            Dict: secondary review 结果
        """
        state = self.state_store.load(self.project_id)
        wp_spec = state.wp_specs[wp_id]
        wp_state = state.wp_states[wp_id]

        secondary_model = self._get_secondary_reviewer(wp_spec.owner)
        secondary_client = self._get_ai_client(secondary_model)

        logger.info(f"E4.5: Secondary review for WP {wp_id} by {secondary_model}")

        # 设置状态为 SECONDARY_REVIEW
        def set_secondary(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].status = WPStatus.SECONDARY_REVIEW
            return s
        state = self.state_store.update(self.project_id, set_secondary, state.state_version)

        for round_num in range(2):
            # 构建 review prompt
            results_summary = ""
            wp_state = state.wp_states[wp_id]
            for st_id, result in wp_state.subtask_results.items():
                results_summary += f"\n### {st_id}\nStatus: {result.status}\nSummary: {result.summary}\n"

            gate_criteria = "\n".join(f"- {c}" for c in wp_spec.gate_criteria)

            prompt = render_review_acceptance_prompt(
                wp_spec_yaml=yaml.dump(wp_spec.model_dump(), default_flow_style=False),
                subtask_results_summary=results_summary,
                gate_criteria=gate_criteria,
            )

            response = await secondary_client.chat(
                prompt,
                system_prompt=f"You are a Secondary Reviewer ({secondary_model}) performing acceptance review.",
            )

            review_result = WPGateChecker.parse_review_yaml(response)
            verdict = review_result.get("verdict", "FAIL")

            if verdict == "PASS":
                # Secondary reviewer approves → RA_PENDING
                def set_ra_pending(s: ExecutionState) -> ExecutionState:
                    s.wp_states[wp_id].status = WPStatus.RA_PENDING
                    s.wp_states[wp_id].gate_result = {"verdict": "PASS", "reviewer": secondary_model, "round": round_num + 1}
                    return s
                state = self.state_store.update(self.project_id, set_ra_pending, state.state_version)
                logger.info(f"E4.5: Secondary reviewer {secondary_model} PASS on round {round_num + 1}")
                return {"verdict": "PASS", "reviewer": secondary_model, "round": round_num + 1}

            # FAIL → iterate fix
            if round_num < 1:  # Still have rounds left
                issues = str(review_result.get("issues", []))
                await self.iterate_wp(wp_id, issues)
                state = self.state_store.load(self.project_id)

        # 2 轮后仍 FAIL → 保持 ESCALATED
        def set_escalated(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].status = WPStatus.ESCALATED
            return s
        state = self.state_store.update(self.project_id, set_escalated, state.state_version)
        logger.info(f"E4.5: Secondary reviewer {secondary_model} FAIL after 2 rounds → ESCALATED")
        return {"verdict": "FAIL", "reviewer": secondary_model, "round": 2}

    async def escalate_wp(self, wp_id: str) -> WPState:
        """
        E5: 升级链 — Gemini 诊断 → HIL

        Args:
            wp_id: WP ID

        Returns:
            WPState: 更新后的 WP 状态
        """
        state = self.state_store.load(self.project_id)
        wp_spec = state.wp_specs[wp_id]
        wp_state = state.wp_states[wp_id]

        logger.info(f"E5: Escalating WP {wp_id}")

        # §2.2.4: 读取 escalation_policy
        if wp_spec.escalation_policy == "skip_gemini":
            logger.info(f"E5: skip_gemini policy — skipping Gemini diagnosis for WP {wp_id}")
            # 直接创建 HIL ticket，跳过 Gemini 诊断
            try:
                from app.services.hil_service import HILService
                from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                hil = HILService()
                await hil.create_ticket(HILTicketCreate(
                    project_id=self.project_id,
                    step_id="step_3_exec",
                    question_type=QuestionType.VALIDATION,
                    question=f"WP {wp_id} escalated (skip_gemini): needs human review",
                    context={"wp_id": wp_id, "policy": "skip_gemini", "iterations": wp_state.iteration_count},
                    priority=TicketPriority.HIGH,
                    blocking=True,
                    timeout_hours=48,
                ))
            except Exception as hil_err:
                logger.warning(f"Failed to create skip_gemini HIL ticket: {hil_err}")
            return state.wp_states[wp_id]

        # 构建迭代历史
        iteration_history = ""
        for st_id, result in wp_state.subtask_results.items():
            iteration_history += f"\n### {st_id}\n{result.summary}\nIssues: {result.open_issues}\n"

        gate_failures = str(wp_state.gate_result) if wp_state.gate_result else "No gate result"

        # v1.2 §6.5: Inject AGENTS.md + MEMORY.md into diagnose prompt
        diag_agents_md = ""
        diag_memory_lessons = ""
        try:
            diag_agents_md = self.snapshot_generator.get_dynamic_section()
        except Exception:
            pass
        try:
            diag_memory_lessons = self.memory_store.get_injection_content(max_tokens=500)
        except Exception:
            pass

        prompt = render_diagnose_prompt(
            wp_spec_yaml=yaml.dump(wp_spec.model_dump(), default_flow_style=False),
            iteration_history=iteration_history,
            gate_failures=gate_failures,
            agents_md_dynamic=diag_agents_md,
            memory_lessons=diag_memory_lessons,
        )

        response = await self.gemini_client.chat(
            prompt,
            system_prompt="You are a Senior Research Advisor diagnosing WP failures.",
        )

        diagnosis = WPGateChecker.parse_review_yaml(response)

        # v1.2 §15: Track if memory entry was added
        memory_entry_added = False
        try:
            diag_summary = str(diagnosis)[:80] if diagnosis else "unknown"
            self.memory_store.add_learn_entry(
                domain="workflow",
                lesson=f"WP {wp_id} escalated after {wp_state.iteration_count} iterations: {diag_summary}",
                source="escalation"
            )
            # v7.1: Write error pattern for escalation
            self.memory_store.add_error_pattern(
                symptom=f"WP {wp_id} escalated after {wp_state.iteration_count} iterations",
                root_cause=diag_summary,
                correction=f"Escalated to HIL for human diagnosis",
                source_actor="gemini",
                wp_id=wp_id,
            )
            memory_entry_added = True
        except Exception as mem_err:
            logger.warning(f"Failed to add MEMORY.md entry during escalation: {mem_err}")

        def update_escalation(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].escalation_history.append({
                "timestamp": datetime.now().isoformat(),
                "diagnosis": diagnosis,
                "memory_entry_added": memory_entry_added,  # v1.2 §15
            })
            return s

        state = self.state_store.update(self.project_id, update_escalation, state.state_version)

        # §2.2.4: 升级链末端 → 创建 HIL ticket
        try:
            from app.services.hil_service import HILService
            from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
            hil = HILService()
            await hil.create_ticket(HILTicketCreate(
                project_id=self.project_id,
                step_id="step_3_exec",
                question_type=QuestionType.VALIDATION,
                question=f"WP {wp_id} escalated: {str(diagnosis)[:200]}",
                context={"wp_id": wp_id, "diagnosis": diagnosis, "iterations": wp_state.iteration_count},
                priority=TicketPriority.HIGH,
                blocking=True,
                timeout_hours=48,
            ))
            logger.info(f"§2.2.4: Created escalation HIL ticket for WP {wp_id}")
        except Exception as hil_err:
            logger.warning(f"Failed to create escalation HIL ticket: {hil_err}")

        # Log decision
        try:
            self.session_logger.log_decision(
                self._current_session_id(),
                f"E5: WP {wp_id} escalated → HIL"
            )
            # v7.1: Session wrap-up on escalation
            self.session_logger.wrap_up(
                session_id=self._current_session_id(),
                completed=f"WP {wp_id} diagnosed and escalated",
                remaining=f"WP {wp_id} awaiting human intervention",
                next_steps="Resolve HIL ticket to unblock WP",
            )
        except Exception as e:
            logger.debug(f"v1.2 escalation logging (non-blocking): {e}")

        return state.wp_states[wp_id]

    async def freeze_wp(self, wp_id: str) -> None:
        """
        E6: 冻结 WP artifacts

        Args:
            wp_id: WP ID
        """
        state = self.state_store.load(self.project_id)
        wp_state = state.wp_states[wp_id]

        if wp_state.status != WPStatus.FROZEN:
            # 运行 freeze gate
            freeze_result = await self.wp_gate_checker.check_freeze_gate(
                self.project_id, wp_id, wp_state
            )
            if freeze_result.verdict != GateVerdict.PASS:
                logger.warning(f"Freeze gate failed for WP {wp_id}")
                return

        def do_freeze(s: ExecutionState) -> ExecutionState:
            s.wp_states[wp_id].status = WPStatus.FROZEN
            s.wp_states[wp_id].frozen_at = datetime.now()
            # 更新 ready WPs
            for ready_wp in s.get_ready_wps():
                if s.wp_states[ready_wp].status == WPStatus.INIT:
                    s.wp_states[ready_wp].status = WPStatus.READY
            return s

        self.state_store.update(self.project_id, do_freeze, state.state_version)
        logger.info(f"E6: WP {wp_id} frozen")

        # v1.2 DevSpec §11: Freeze Hygiene — git tag + FROZEN_MANIFEST
        try:
            from app.utils.git_manager import get_git_manager
            git_mgr = get_git_manager()
            state = self.state_store.load(self.project_id)
            version = state.state_version
            tag_name = f"{wp_id}-v{version}"
            git_mgr.create_tag(self.project_id, tag_name, f"Freeze WP {wp_id} at version {version}")

            # Generate FROZEN_MANIFEST (v1.2 §11.1 step 3: 含 ra_result 引用)
            project_path = Path(settings.projects_path) / self.project_id
            exec_dir = project_path / "execution"
            exec_dir.mkdir(parents=True, exist_ok=True)
            wp_state = state.wp_states.get(wp_id)
            artifacts = {}
            if wp_state:
                for st_id, result in wp_state.subtask_results.items():
                    for art_path in result.artifacts_written:
                        full_path = project_path / art_path
                        if full_path.exists():
                            sha = hashlib.sha256(full_path.read_bytes()).hexdigest()
                            artifacts[art_path] = {"sha256": sha, "subtask": st_id}

            # v1.2 §11.1: 包含 ra_result 引用
            ra_result_ref = None
            if wp_state and hasattr(wp_state, 'ra_result') and wp_state.ra_result:
                ra_result_ref = f"execution/{wp_id}/gate_results/ra_*.json"

            manifest = {
                "wp_id": wp_id,
                "tag": tag_name,
                "frozen_at": datetime.now().isoformat(),
                "artifacts": artifacts,
                "ra_result": ra_result_ref,  # v1.2 §11.1 step 3
            }
            manifest_path = exec_dir / f"FROZEN_MANIFEST_{wp_id}.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.info(f"v1.2 §11.1: FROZEN_MANIFEST for {wp_id}: {len(artifacts)} artifacts, ra_result={ra_result_ref}")

            # v1.2 §11.1 step 2: 上传产物到持久化存储（artifact store）
            try:
                from app.services.artifact_store import ArtifactStore
                artifact_store = ArtifactStore(str(project_path))
                for art_path, art_info in artifacts.items():
                    artifact_store.save_artifact(
                        artifact_id=f"{wp_id}_{art_path.replace('/', '_')}",
                        content_path=str(project_path / art_path),
                        metadata={"wp_id": wp_id, "subtask": art_info["subtask"], "sha256": art_info["sha256"]},
                        version="frozen",
                    )
                logger.info(f"v1.2 §11.1 step 2: Uploaded {len(artifacts)} artifacts to persistent store")
            except Exception as upload_err:
                logger.warning(f"v1.2 §11.1 step 2: Artifact upload failed (non-blocking): {upload_err}")
        except Exception as fh_err:
            logger.warning(f"v1.2: Freeze hygiene failed (non-blocking): {fh_err}")

        # v1.2: Update AGENTS.md + session wrap-up
        try:
            state = self.state_store.load(self.project_id)
            wp_results = [{"wp_id": wid, "status": ws.status.value} for wid, ws in state.wp_states.items()]
            frozen_count = sum(1 for ws in state.wp_states.values() if ws.status == WPStatus.FROZEN)
            total_wps = len(state.wp_states)
            dynamic = self.snapshot_generator.generate_agents_md_dynamic_section(
                state={"phase": "E6_FROZEN", "frozen_wps": frozen_count, "total_wps": total_wps},
                active_wp_results=wp_results,
                next_task={"wp_id": state.get_ready_wps()[0]} if state.get_ready_wps() else None,
            )
            self.snapshot_generator.update_agents_md(dynamic)
            self.session_logger.log_decision(
                self._current_session_id(),
                f"WP {wp_id} frozen ({frozen_count}/{total_wps} complete)"
            )
            # v7.1: Session wrap-up on freeze
            remaining_wps = [wid for wid, ws in state.wp_states.items() if ws.status != WPStatus.FROZEN]
            self.session_logger.wrap_up(
                session_id=self._current_session_id(),
                completed=f"WP {wp_id} frozen ({frozen_count}/{total_wps})",
                remaining=f"{len(remaining_wps)} WPs remaining: {', '.join(remaining_wps[:5])}",
                next_steps=f"Execute next ready WP" if state.get_ready_wps() else "All WPs frozen — proceed to Step 4",
            )
        except Exception as e:
            logger.debug(f"v1.2 freeze logging (non-blocking): {e}")

        # §4.2 E6: 如有新教训 → 写入 MEMORY.md
        try:
            state = self.state_store.load(self.project_id)
            wp_state = state.wp_states.get(wp_id)
            if wp_state:
                # Extract lessons from open_issues across all subtasks
                all_issues = []
                for st_id, sr in wp_state.subtask_results.items():
                    all_issues.extend(sr.open_issues)
                # Extract from error_message if WP had failures before freeze
                if wp_state.error_message:
                    all_issues.append(wp_state.error_message)
                # Extract from iteration history (fixes that were needed)
                if wp_state.iteration_count > 0:
                    self.memory_store.add_learn_entry(
                        domain=wp_id,
                        lesson=f"WP {wp_id} required {wp_state.iteration_count} fix iteration(s) before freeze",
                        source="freeze_wp",
                    )
                for issue in all_issues[:5]:  # Cap at 5 to avoid noise
                    self.memory_store.add_learn_entry(
                        domain=wp_id,
                        lesson=issue,
                        source="freeze_wp",
                    )
                if all_issues:
                    logger.info(f"§4.2 E6: Wrote {min(len(all_issues), 5)} lessons to MEMORY.md for {wp_id}")
        except Exception as mem_err:
            logger.debug(f"§4.2 E6 MEMORY.md lesson write (non-blocking): {mem_err}")

    async def get_execution_summary(self) -> Dict[str, Any]:
        """返回当前执行状态摘要"""
        state = self.state_store.load(self.project_id)

        wp_summaries = {}
        for wp_id, wp_state in state.wp_states.items():
            spec = state.wp_specs.get(wp_id)
            wp_summaries[wp_id] = {
                "name": spec.name if spec else wp_id,
                "status": wp_state.status.value,
                "owner": wp_state.owner,
                "reviewer": wp_state.reviewer,
                "iteration_count": wp_state.iteration_count,
                "subtasks_completed": wp_state.subtasks_completed,
                "subtasks_remaining": wp_state.subtasks_remaining,
                "frozen_at": wp_state.frozen_at.isoformat() if wp_state.frozen_at else None,
            }

        return {
            "project_id": self.project_id,
            "state_version": state.state_version,
            "total_wps": len(state.wp_states),
            "frozen_wps": sum(1 for ws in state.wp_states.values() if ws.status == WPStatus.FROZEN),
            "ready_wps": state.get_ready_wps(),
            "all_frozen": state.all_wps_frozen(),
            "wp_dag": state.wp_dag,
            "wps": wp_summaries,
        }

    # ========== v1.2 DevSpec Methods ==========

    async def process_ra_verdict(self, wp_id: str, ra_result) -> Dict[str, Any]:
        """
        E6A→E6: 处理 RA 判定结果

        Args:
            wp_id: WP ID
            ra_result: RAResult 对象

        Returns:
            Dict: 处理结果 {verdict, action, ...}
        """
        state = self.state_store.load(self.project_id)
        wp_state = state.wp_states.get(wp_id)
        if not wp_state or wp_state.status != WPStatus.RA_PENDING:
            raise ValueError(f"WP {wp_id} is not in RA_PENDING state")

        verdict = ra_result.verdict if hasattr(ra_result, 'verdict') else RAVerdict(ra_result.get("verdict", "BLOCK"))

        if verdict == RAVerdict.ADVANCE:
            await self.freeze_wp(wp_id)
            action = "frozen"
        elif verdict == RAVerdict.POLISH:
            await self.freeze_wp(wp_id)
            for suggestion in (ra_result.polish_suggestions if hasattr(ra_result, 'polish_suggestions') else []):
                self.memory_store.add_learn_entry(
                    domain="workflow",
                    lesson=f"RA POLISH {wp_id}: {suggestion[:80]}",
                    source="escalation"
                )
            action = "frozen_with_polish"
        else:
            # BLOCK → leave in RA_PENDING for human override
            reasoning = ra_result.reasoning[:200] if hasattr(ra_result, 'reasoning') else 'blocked'
            self.session_logger.log_decision(
                self._current_session_id(),
                f"RA BLOCK for {wp_id}: {reasoning[:80]}"
            )
            # v7.1: Write strategy to memory
            self.memory_store.add_strategy(
                symptom=f"RA BLOCK for WP {wp_id}",
                correction=reasoning,
                source_actor="chatgpt",
                wp_id=wp_id,
            )
            # §2.2.7: Gate PASS 但 RA BLOCK = ChatGPT 与 Gate 系统冲突
            self.memory_store.add_conflict_resolution(
                wp_id=wp_id,
                actor_a="gate_system",
                actor_b="chatgpt",
                conflict_desc="Gate PASS but RA BLOCK",
                resolution=reasoning[:100],
                arbiter="chatgpt",
            )
            # v7.1: Create BLOCKING HIL ticket
            try:
                from app.services.hil_service import HILService
                from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                hil = HILService()
                await hil.create_ticket(HILTicketCreate(
                    project_id=self.project_id,
                    step_id="step_3_exec",
                    question_type=QuestionType.VALIDATION,
                    question=f"RA BLOCK for WP {wp_id}: {reasoning[:200]}",
                    context={"wp_id": wp_id, "ra_verdict": "BLOCK"},
                    priority=TicketPriority.CRITICAL,
                    blocking=True,
                ))
            except Exception as hil_err:
                logger.warning(f"Failed to create RA BLOCK HIL ticket: {hil_err}")
            action = "blocked_hil"

        logger.info(f"RA verdict for {wp_id}: {verdict.value if hasattr(verdict, 'value') else verdict} → {action}")
        return {"wp_id": wp_id, "verdict": verdict.value if hasattr(verdict, 'value') else str(verdict), "action": action}

    def _current_session_id(self) -> str:
        """获取当前最新的 session ID（如果没有则创建一个）"""
        sessions = self.session_logger.list_sessions()
        if sessions:
            return sessions[-1]["session_id"]
        return self.session_logger.create_session(
            goal="Auto-created session",
            approach="Continuation of execution",
        )

    # ========== Helper Methods ==========

    def _parse_wp_registry(self, yaml_content: str) -> tuple[Dict[str, WPSpec], Dict[str, List[str]]]:
        """解析 WP 注册表 YAML"""
        # 清理 markdown code fences
        content = yaml_content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            logger.error(f"Failed to parse WP registry YAML: {e}")
            raise ValueError(f"Invalid WP registry YAML: {e}")

        wps_data = data.get("work_packages", [])
        if not wps_data:
            raise ValueError("No work_packages found in YAML")

        wp_specs = {}
        wp_dag = {}

        for wp_data in wps_data:
            wp_id = wp_data["wp_id"]
            subtasks = []
            for st_data in wp_data.get("subtasks", []):
                subtasks.append(SubtaskSpec(
                    subtask_id=st_data["subtask_id"],
                    wp_id=wp_id,
                    objective=st_data.get("objective", ""),
                    inputs=st_data.get("inputs", []),
                    outputs=st_data.get("outputs", []),
                    acceptance_criteria=st_data.get("acceptance_criteria", []),
                    allowed_paths=st_data.get("allowed_paths", []),
                    forbidden_paths=st_data.get("forbidden_paths", []),
                ))

            # v1.2: Heuristic default owner — code/figure/test WPs default to claude
            name_lower = wp_data.get("name", "").lower()
            if any(kw in name_lower for kw in ("code", "implement", "test", "figure", "plot", "verify", "experiment")):
                default_owner = "claude"
            else:
                default_owner = "chatgpt"

            # v1.2 §3.2: Reviewer follows owner — claude↔chatgpt cross-review
            resolved_owner = wp_data.get("owner", default_owner)
            if resolved_owner.lower().startswith("claude"):
                default_reviewer = "chatgpt"
            elif resolved_owner.lower() in ("chatgpt", "gpt") or resolved_owner.lower().startswith("gpt"):
                default_reviewer = "claude"
            else:
                default_reviewer = "gemini"

            wp_specs[wp_id] = WPSpec(
                wp_id=wp_id,
                name=wp_data.get("name", wp_id),
                owner=resolved_owner,
                reviewer=wp_data.get("reviewer", default_reviewer),
                depends_on=wp_data.get("depends_on", []),
                gate_criteria=wp_data.get("gate_criteria", []),
                subtasks=subtasks,
            )
            wp_dag[wp_id] = wp_data.get("depends_on", [])

        return wp_specs, wp_dag

    @staticmethod
    def _extract_section(text: str, section_name: str) -> str:
        """从 markdown 响应中提取指定 section 的内容"""
        import re
        pattern = rf"###\s*{re.escape(section_name)}\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _extract_list(text: str, section_name: str) -> List[str]:
        """从 markdown 响应中提取列表项"""
        section = WPExecutionEngine._extract_section(text, section_name)
        if not section or section.lower() == "none":
            return []
        items = []
        for line in section.split("\n"):
            line = line.strip()
            if line.startswith("- ") or line.startswith("* "):
                items.append(line[2:].strip())
            elif line and not line.startswith("#"):
                items.append(line)
        return items

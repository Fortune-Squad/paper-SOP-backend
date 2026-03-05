"""
PhaseEngine — M2M Phase-level execution engine.

Sits above WP Engine, orchestrates WorkPlan phases linearly with
convergence control.  Each phase follows the dispatch→execute→review
loop, producing HandoffPackets at every step.

Design constraints:
  - Linear phase execution (no parallelism)
  - Convergence bounded by phase.convergence.max_iterations
  - Every Packet stored immediately via PacketStore
  - Every discovery/failure recorded via TrajectoryStore
  - All recording wrapped in try-except (non-blocking)
  - Does NOT modify WP Engine, Phase A structures, or Autopilot
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.workplan import Phase, WorkPlan
from app.services.handoff_packet import (
    HandoffPacket,
    ReasoningBlock,
    DecisionBlock,
    ArtifactBlock,
    TaskBlock,
)
from app.services.packet_store import PacketStore
from app.services.trajectory_store import TrajectoryStore
from app.services.trajectory_record import TrajectoryRecord

logger = logging.getLogger(__name__)


# ── result dataclasses ───────────────────────────────────────────────


@dataclass
class PhaseResult:
    """Outcome of a single phase execution."""

    phase_id: str = ""
    final_action: str = ""  # ADVANCE | ITERATE | ESCALATE | ABORT | BLOCK
    iterations: int = 0
    packets: List[HandoffPacket] = field(default_factory=list)
    reason: str = ""


@dataclass
class WorkPlanResult:
    """Outcome of full WorkPlan execution."""

    status: str = ""  # COMPLETE | ABORT_TO_STEP2 | BLOCKED
    results: List[PhaseResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


# ── PhaseEngine ──────────────────────────────────────────────────────


class PhaseEngine:
    """Phase-level execution engine — linear WorkPlan orchestration + convergence control."""

    def __init__(
        self,
        workplan: WorkPlan,
        wp_engine: Any,
        router: Any,
        trajectory_store: TrajectoryStore,
        packet_store: PacketStore,
        hil_service: Any = None,
        project_id: str = "",
    ) -> None:
        self.workplan = workplan
        self.wp_engine = wp_engine
        self.router = router
        self.trajectory_store = trajectory_store
        self.packet_store = packet_store
        self.hil_service = hil_service
        self.project_id = project_id

    # ── top-level entry ──────────────────────────────────────────

    async def execute_workplan(self) -> WorkPlanResult:
        """Linearly execute all phases in the WorkPlan."""
        results: List[PhaseResult] = []

        for phase in self.workplan.phases:
            result = await self.execute_phase(phase)
            results.append(result)

            # Global abort: 3 consecutive ABORTs → ABORT_TO_STEP2
            if self._check_global_abort(results):
                logger.warning(
                    "Global abort triggered: 3 consecutive phase ABORTs"
                )
                return WorkPlanResult(
                    status="ABORT_TO_STEP2",
                    results=results,
                    summary={
                        "abort_reason": "3_consecutive_aborts",
                        "completed_phases": len(results),
                        "total_phases": len(self.workplan.phases),
                    },
                )

            # BLOCK → create HIL ticket + stop immediately
            if result.final_action == "BLOCK":
                logger.warning(
                    "WorkPlan blocked at phase %s: %s",
                    phase.phase_id,
                    result.reason,
                )
                await self._create_block_hil_ticket(phase, result, results)
                return WorkPlanResult(
                    status="BLOCKED",
                    results=results,
                    summary={
                        "blocked_phase": phase.phase_id,
                        "reason": result.reason,
                    },
                )

        return WorkPlanResult(
            status="COMPLETE",
            results=results,
            summary={
                "completed_phases": len(results),
                "total_phases": len(self.workplan.phases),
            },
        )

    # ── single phase execution ───────────────────────────────────

    async def execute_phase(self, phase: Phase) -> PhaseResult:
        """Execute a single phase with convergence control loop."""
        max_iter = 5
        if phase.convergence:
            max_iter = phase.convergence.max_iterations or 5

        logger.info(
            "Phase %s started: '%s' (owner=%s, max_iter=%d)",
            phase.phase_id, phase.title, phase.owner, max_iter,
        )

        history: List[HandoffPacket] = []
        iteration = 0

        while iteration < max_iter:
            iteration += 1

            # 1. Owner dispatches task
            dispatch = await self._owner_dispatch(phase, history)
            self._store_packet(dispatch)
            history.append(dispatch)

            # 2. Executor runs
            report = await self._executor_run(phase, dispatch)
            self._store_packet(report)
            history.append(report)

            # 3. Owner reviews
            verdict = await self._owner_review(phase, report)
            self._store_packet(verdict)
            history.append(verdict)

            # 4. Record trajectory from report
            self._record_trajectory(phase, report, verdict)

            # 5. Decide next action
            action = ""
            if verdict.decisions:
                action = verdict.decisions.ra_action or ""

            if action == "ADVANCE":
                logger.info(
                    "Phase %s completed: action=ADVANCE iterations=%d",
                    phase.phase_id, iteration,
                )
                return PhaseResult(
                    phase_id=phase.phase_id,
                    final_action="ADVANCE",
                    iterations=iteration,
                    packets=list(history),
                )

            if action == "ITERATE":
                if self._should_escalate(history, phase.convergence):
                    return PhaseResult(
                        phase_id=phase.phase_id,
                        final_action="ESCALATE",
                        iterations=iteration,
                        packets=list(history),
                        reason="repeated_same_error",
                    )
                continue

            if action in ("ESCALATE", "ABORT", "BLOCK"):
                logger.info(
                    "Phase %s completed: action=%s iterations=%d reason=%s",
                    phase.phase_id, action, iteration,
                    verdict.decisions.rationale_ref if verdict.decisions else "",
                )
                return PhaseResult(
                    phase_id=phase.phase_id,
                    final_action=action,
                    iterations=iteration,
                    packets=list(history),
                    reason=verdict.decisions.rationale_ref if verdict.decisions else "",
                )

            # Unknown action → treat as ITERATE, let loop continue
            continue

        # Exhausted max_iterations
        logger.info(
            "Phase %s completed: action=ABORT iterations=%d reason=max_iterations_exhausted",
            phase.phase_id, iteration,
        )
        return PhaseResult(
            phase_id=phase.phase_id,
            final_action="ABORT",
            iterations=iteration,
            packets=list(history),
            reason="max_iterations_exhausted",
        )

    # ── dispatch / execute / review ──────────────────────────────

    async def _owner_dispatch(
        self, phase: Phase, history: List[HandoffPacket]
    ) -> HandoffPacket:
        """Owner produces a task_dispatch Packet."""
        # Build context from history
        context_summary = ""
        for pkt in history[-6:]:  # Last 6 packets for context
            ptype = pkt.packet_type or "unknown"
            action = ""
            if pkt.decisions:
                action = pkt.decisions.ra_action or ""
            context_summary += f"[{ptype}] {action}\n"

        packet = HandoffPacket(
            from_model=phase.owner,
            to_model=self._get_executor(phase),
            phase_id=phase.phase_id,
            packet_type="task_dispatch",
            workplan_id=self.workplan.workplan_id,
            task=TaskBlock(
                objective=phase.title,
                steps=[f"Execute phase: {phase.title}"],
                stop_conditions=phase.acceptance_criteria[:],
                acceptance_tests=phase.acceptance_criteria[:],
            ),
            reasoning=ReasoningBlock(
                chain=f"Dispatching phase {phase.phase_id}: {phase.title}",
                evidence_refs=phase.inputs[:],
            ),
            convergence=phase.convergence,
        )
        return packet

    async def _executor_run(
        self, phase: Phase, dispatch: HandoffPacket
    ) -> HandoffPacket:
        """Executor executes and produces a result_report Packet."""
        # Delegate to wp_engine if available and has execute_phase method
        executor_result: Dict[str, Any] = {}
        try:
            if hasattr(self.wp_engine, "execute_phase_tasks"):
                executor_result = await self.wp_engine.execute_phase_tasks(
                    phase_id=phase.phase_id,
                    dispatch_packet=dispatch,
                )
        except Exception as e:
            logger.warning("WP Engine delegation failed (non-blocking): %s", e)
            executor_result = {"error": str(e)}

        packet = HandoffPacket(
            from_model=self._get_executor(phase),
            to_model=phase.owner,
            phase_id=phase.phase_id,
            packet_type="result_report",
            workplan_id=self.workplan.workplan_id,
            parent_packet_id=dispatch.packet_id,
            thread_id=dispatch.thread_id,
            reasoning=ReasoningBlock(
                chain=f"Execution report for phase {phase.phase_id}",
                discoveries=executor_result.get("discoveries", []),
                what_i_tried_but_failed=executor_result.get("failures", []),
            ),
            artifacts=ArtifactBlock(
                manifest=executor_result.get("artifacts", []),
            ),
        )
        return packet

    async def _owner_review(
        self, phase: Phase, report: HandoffPacket
    ) -> HandoffPacket:
        """Owner reviews and produces a review_verdict Packet."""
        # Default: ADVANCE if no issues, otherwise derive from report
        action = "ADVANCE"
        rationale = "Phase execution completed successfully"

        if report.reasoning:
            failures = report.reasoning.what_i_tried_but_failed or []
            if failures:
                action = "ITERATE"
                rationale = f"Failures detected: {len(failures)} items need retry"

        packet = HandoffPacket(
            from_model=phase.owner,
            to_model=self._get_executor(phase),
            phase_id=phase.phase_id,
            packet_type="review_verdict",
            workplan_id=self.workplan.workplan_id,
            parent_packet_id=report.packet_id,
            thread_id=report.thread_id,
            decisions=DecisionBlock(
                ra_action=action,
                rationale_ref=rationale,
            ),
        )
        return packet

    # ── convergence control ──────────────────────────────────────

    def _should_escalate(
        self,
        packets: List[HandoffPacket],
        convergence: Any = None,
    ) -> bool:
        """Check if escalation is triggered (consecutive K rounds same error type)."""
        # Collect result_report packets
        reports = [p for p in packets if p.packet_type == "result_report"]
        if len(reports) < 2:
            return False

        # Compare last 2 reports' failure signatures
        last_two = reports[-2:]
        signatures = []
        for r in last_two:
            sig = set()
            if r.reasoning and r.reasoning.what_i_tried_but_failed:
                sig = set(r.reasoning.what_i_tried_but_failed)
            signatures.append(sig)

        # If both have failures and they overlap significantly → escalate
        if signatures[0] and signatures[1]:
            overlap = signatures[0] & signatures[1]
            if overlap:
                return True

        # Check custom escalation_trigger
        if convergence and hasattr(convergence, "escalation_trigger"):
            trigger = convergence.escalation_trigger or ""
            if trigger:
                for r in last_two:
                    if r.reasoning and r.reasoning.chain and trigger in r.reasoning.chain:
                        return True

        return False

    def _check_global_abort(self, results: List[PhaseResult]) -> bool:
        """3 consecutive phase ABORTs → return True."""
        if len(results) < 3:
            return False
        return all(r.final_action == "ABORT" for r in results[-3:])

    # ── trajectory recording ─────────────────────────────────────

    def _record_trajectory(
        self,
        phase: Phase,
        report: HandoffPacket,
        verdict: HandoffPacket,
    ) -> None:
        """Record discoveries and failures from report into TrajectoryStore."""
        try:
            if report.reasoning and report.reasoning.discoveries:
                for discovery in report.reasoning.discoveries:
                    self.trajectory_store.record(
                        TrajectoryRecord(
                            problem_summary=discovery,
                            slot=phase.phase_id,
                            stage=phase.title,
                            source_system="phase_engine",
                            outcome=(
                                verdict.decisions.ra_action
                                if verdict.decisions
                                else ""
                            ),
                            tags=[
                                f"phase:{phase.phase_id}",
                                f"owner:{phase.owner}",
                            ],
                        )
                    )
            if report.reasoning and report.reasoning.what_i_tried_but_failed:
                for attempt in report.reasoning.what_i_tried_but_failed:
                    self.trajectory_store.record(
                        TrajectoryRecord(
                            problem_summary=attempt,
                            slot=phase.phase_id,
                            error_category="failed_attempt",
                            source_system="phase_engine",
                            outcome="failed",
                        )
                    )
        except Exception as e:
            logger.warning("_record_trajectory failed (non-blocking): %s", e)

    # ── packet storage ───────────────────────────────────────────

    def _store_packet(self, packet: HandoffPacket) -> None:
        """Store packet in PacketStore (non-blocking)."""
        try:
            self.packet_store.store(packet)
        except Exception as e:
            logger.warning("_store_packet failed (non-blocking): %s", e)

    # ── HIL ticket creation ────────────────────────────────────────

    async def _create_block_hil_ticket(
        self,
        phase: Phase,
        result: PhaseResult,
        prior_results: List[PhaseResult],
    ) -> None:
        """Create a HIL ticket when a phase is BLOCKED (non-blocking)."""
        if not self.hil_service or not self.project_id:
            return
        try:
            from app.models.hil import HILTicketCreate, QuestionType, TicketPriority

            # Collect recent reasoning from the last few packets
            reasoning_lines: List[str] = []
            for pkt in result.packets[-6:]:
                if pkt.reasoning and pkt.reasoning.chain:
                    reasoning_lines.append(pkt.reasoning.chain[:120])

            context = {
                "phase_id": phase.phase_id,
                "block_reason": result.reason,
                "iterations": result.iterations,
                "prior_phases_completed": len(prior_results) - 1,
                "recent_reasoning": reasoning_lines,
            }

            ticket_create = HILTicketCreate(
                project_id=self.project_id,
                step_id=f"phase_engine:{phase.phase_id}",
                question_type=QuestionType.DECISION,
                question=(
                    f"Phase '{phase.title}' ({phase.phase_id}) is BLOCKED after "
                    f"{result.iterations} iteration(s). Reason: {result.reason}. "
                    f"Please decide how to proceed."
                ),
                context=context,
                options=["Retry phase", "Skip phase", "Abort workplan"],
                priority=TicketPriority.HIGH,
                blocking=True,
                timeout_hours=72.0,
            )

            ticket = await self.hil_service.create_ticket(ticket_create)
            logger.info(
                "HIL ticket created for BLOCK: %s (phase=%s)",
                ticket.ticket_id, phase.phase_id,
            )
        except Exception as e:
            logger.warning("Failed to create BLOCK HIL ticket: %s", e)

    # ── helpers ───────────────────────────────────────────────────

    def _get_executor(self, phase: Phase) -> str:
        """Determine the executor model for a phase."""
        if phase.partners:
            return phase.partners[0]
        return phase.owner

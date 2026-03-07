"""
HandoffPacket — M2M Transfer Protocol data structures.

A HandoffPacket is the atomic unit of communication between AI models
in the M2M orchestration layer.  It carries reasoning, decisions,
artifacts, and task directives from one model to the next.

Valid ``packet_type`` values:
    task_dispatch | result_report | review_request |
    review_verdict | escalation | phase_handoff

Serialise with ``dataclasses.asdict(packet)``.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.workplan import ConvergenceConfig

# ── valid packet types ──────────────────────────────────────────────

VALID_PACKET_TYPES = frozenset({
    "task_dispatch",
    "result_report",
    "review_request",
    "review_verdict",
    "escalation",
    "phase_handoff",
})

# ── valid RA actions ────────────────────────────────────────────────

VALID_RA_ACTIONS = frozenset({
    "ADVANCE",
    "ITERATE",
    "ESCALATE",
    "ABORT",
    "BLOCK",
})

# ── sub-blocks ──────────────────────────────────────────────────────


@dataclass
class ReasoningBlock:
    """Structured reasoning trace attached to a handoff."""

    chain: str = ""
    unverified_assumptions: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    invariants: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    confidence: Dict[str, Any] = field(default_factory=dict)
    discoveries: List[str] = field(default_factory=list)
    what_i_tried_but_failed: List[str] = field(default_factory=list)

    # ── DevSpec v0.2: experience & pivot fields ──────────────────────
    failure_classification: Optional[str] = None  # FailureClassification value
    validated_checkpoints: List[Any] = field(default_factory=list)  # List[ValidatedCheckpoint]
    ruled_out_options: List[Any] = field(default_factory=list)  # List[RuledOutOption]
    structural_evidence_refs: List[str] = field(default_factory=list)
    pivot_suggestion: Optional[str] = None  # NONE | REPLAN | PIVOT_MODEL | PIVOT_TASK


@dataclass
class DecisionBlock:
    """Decision record within a handoff."""

    ra_action: str = ""  # ADVANCE | ITERATE | ESCALATE | ABORT | BLOCK
    rationale_ref: str = ""
    made: List[str] = field(default_factory=list)
    pending_decisions: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)


@dataclass
class ArtifactBlock:
    """Artifact manifest and reproducibility info."""

    manifest: List[str] = field(default_factory=list)
    repro: Dict[str, Any] = field(default_factory=dict)
    forbidden: List[str] = field(default_factory=list)


@dataclass
class TaskBlock:
    """Task directive for the receiving model."""

    objective: str = ""
    steps: List[str] = field(default_factory=list)
    stop_conditions: List[str] = field(default_factory=list)
    acceptance_tests: List[str] = field(default_factory=list)


# ── top-level packet ────────────────────────────────────────────────


@dataclass
class HandoffPacket:
    """Atomic M2M communication unit."""

    # ── identity ────────────────────────────────────────────────────
    packet_id: str = field(
        default_factory=lambda: f"pkt-{uuid.uuid4().hex[:12]}"
    )
    schema_version: str = "m2m-tp/0.2"
    mode: str = "quick"                       # quick | deep | review

    # ── routing ─────────────────────────────────────────────────────
    from_model: str = ""
    to_model: str = ""
    phase_id: str = ""
    packet_type: str = ""                     # see VALID_PACKET_TYPES
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── threading ───────────────────────────────────────────────────
    thread_id: str = field(
        default_factory=lambda: f"thr-{uuid.uuid4().hex[:12]}"
    )
    parent_packet_id: Optional[str] = None

    # ── context ─────────────────────────────────────────────────────
    workplan_id: str = ""
    stage_key: str = ""
    delivery_method: str = "DIRECT_API"

    # ── payload blocks (all optional) ───────────────────────────────
    reasoning: Optional[ReasoningBlock] = None
    decisions: Optional[DecisionBlock] = None
    artifacts: Optional[ArtifactBlock] = None
    task: Optional[TaskBlock] = None
    convergence: Optional[ConvergenceConfig] = None

    # ── DevSpec v0.2: experience & pivot fields ──────────────────────
    workphase_id: str = ""
    risk_flags: List[str] = field(default_factory=list)
    experience_bundle: Optional[Any] = None  # ExperienceBundle from experience_models

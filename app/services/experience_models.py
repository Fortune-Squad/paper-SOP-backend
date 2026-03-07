"""DevSpec v0.2 — Experience & Pivot data models.

Defines data structures for structured retreat and experience inheritance:
  - FailureClassification constants (Section 3)
  - ValidatedCheckpoint          (Section 4.3)
  - RuledOutOption               (Section 4.4)
  - ExperienceBundle             (Section 4.5)
  - WorkPlanLifecycleEvent       (Section 4.2)
  - PacketContext                (Section 6.1)
  - inject_context()             (Section 6.2)

Design: stdlib-only, zero third-party deps.  No imports from other
project modules (avoids circular dependencies).
All dataclasses support ``dataclasses.asdict()`` for JSON serialisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


# ── FailureClassification constants ──────────────────────────────────

FAILURE_CLASSIFICATIONS = frozenset({
    "CONVERGENCE_FAILURE",
    "STRUCTURAL_INFEASIBILITY",
    "PARAMETER_SENSITIVITY",
    "IMPLEMENTATION_BUG",
    "DATA_ISSUE",
    "TOOLCHAIN_LIMITATION",
    "INSUFFICIENT_EVIDENCE",
    "UNKNOWN",
})


# ── ValidatedCheckpoint ─────────────────────────────────────────────

@dataclass
class ValidatedCheckpoint:
    """Minimal structure for a reusable verified result.

    verification_kind recommended values (not enforced):
        TEST_PASS | PROOF | SIMULATION | DATA_VALIDATION | LITERATURE_CONFIRMATION
    """

    checkpoint_id: str = ""
    title: str = ""
    summary: str = ""
    verification_kind: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    artifact_refs: List[str] = field(default_factory=list)
    confidence: str = "MED"  # LOW | MED | HIGH
    tags: List[str] = field(default_factory=list)


# ── RuledOutOption ───────────────────────────────────────────────────

@dataclass
class RuledOutOption:
    """Record of an eliminated approach.

    rejected_because supports multiple FailureClassification values.
    """

    option_id: str = ""
    description: str = ""
    rejected_because: List[str] = field(default_factory=list)  # FailureClassification values
    rejected_because_notes: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    notes: Optional[str] = None


# ── ExperienceBundle ─────────────────────────────────────────────────

@dataclass
class ExperienceBundle:
    """Unified carrier aggregating reusable outputs from a failed/pivoted path."""

    bundle_id: str = ""
    source_workplan_id: str = ""
    source_workphase_id: Optional[str] = None
    created_at: str = ""  # ISO 8601
    validated_checkpoints: List[ValidatedCheckpoint] = field(default_factory=list)
    ruled_out_options: List[RuledOutOption] = field(default_factory=list)
    reusable_artifact_refs: List[str] = field(default_factory=list)
    summary: str = ""
    recommended_next_moves: List[str] = field(default_factory=list)


# ── WorkPlanLifecycleEvent ───────────────────────────────────────────

@dataclass
class WorkPlanLifecycleEvent:
    """Lightweight event logged via PacketStore for workplan state transitions.

    event_type values: STARTED | COMPLETED | PIVOTED | FAILED | SUSPENDED
    classification values: see FAILURE_CLASSIFICATIONS
    """

    event_type: str = ""  # STARTED | COMPLETED | PIVOTED | FAILED | SUSPENDED
    workplan_id: str = ""
    timestamp: str = ""  # ISO 8601
    actor: str = ""  # human name or agent identifier
    reason: Optional[str] = None
    classification: Optional[str] = None  # FailureClassification value
    evidence_refs: List[str] = field(default_factory=list)
    derived_workplan_id: Optional[str] = None  # new plan after pivot


# ── PacketContext ────────────────────────────────────────────────────

@dataclass
class PacketContext:
    """Lightweight context for workplan_id injection into HandoffPackets."""

    workplan_id: Optional[str] = None
    workphase_id: Optional[str] = None  # default = phase_id


# ── inject_context() ────────────────────────────────────────────────

def inject_context(packet: Any, ctx: PacketContext) -> Any:
    """Inject workplan/workphase IDs into a packet if not already set.

    Uses Any for packet type to avoid circular import with handoff_packet.py.
    Handles both ``""`` (str default) and ``None`` (Optional default) as empty.
    """
    if not getattr(packet, "workplan_id", ""):
        packet.workplan_id = ctx.workplan_id
    if not getattr(packet, "workphase_id", ""):
        packet.workphase_id = ctx.workphase_id
    return packet

"""
TrajectoryRecord — canonical data structure for the trajectory store.

Each record captures the five essential elements of an incident:
  1. What was the problem (problem_summary + problem_detail)
  2. Why the error occurred (root_cause + error_category)
  3. Specific error content (problem_detail + parameters)
  4. Solution applied (solution_summary + solution_detail)
  5. Outcome (outcome + validation_result + performance_delta)

All fields have defaults (None / 0) so callers construct incrementally.
Serialise with ``dataclasses.asdict(record)``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class TrajectoryRecord:
    # ── identity ─────────────────────────────────────────────────────
    record_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── element 1: what was the problem ──────────────────────────────
    problem_summary: str = ""
    problem_detail: str = ""

    # ── element 2: why the error occurred ────────────────────────────
    root_cause: str = ""
    error_category: str = ""
    #   gate_fail | ra_block | boundary_violation | wp_fail
    #   subtask_error | collector_pattern | slot_b_error | custom

    # ── element 3: context & parameters ──────────────────────────────
    slot: str = ""           # slot_a | slot_b | slot_c | core | inverse
    stage: str = ""          # step/stage where the incident occurred
    wp_id: str = ""
    subtask_id: str = ""
    project_id: str = ""
    solver: str = ""         # slot-b solver name (feko/cst/hfss)
    task_type: str = ""      # TaskType enum value when available
    parameters: Dict[str, Any] = field(default_factory=dict)

    # ── element 4: solution ──────────────────────────────────────────
    solution_summary: str = ""
    solution_detail: str = ""

    # ── element 5: outcome ───────────────────────────────────────────
    outcome: str = ""        # resolved | workaround | escalated | unresolved
    validation_result: str = ""  # PASS | FAIL | PENDING | N/A
    performance_delta: Dict[str, Any] = field(default_factory=dict)

    # ── provenance ───────────────────────────────────────────────────
    source_system: str = ""  # wp_engine | gate_runner | ra | boundary | collector | slot_b_memory
    source_actor: str = ""   # chatgpt | claude | gemini | human | system
    tags: List[str] = field(default_factory=list)

"""
Task Type enum — describes *what kind of work* is being requested.

Used by ModelRouter.resolve_by_task() to pick the best-fit model
based on the three-model capability profile (DevSpec v1.3 Addendum §A4):

  - Claude:   execution / code / review / structured extraction
  - ChatGPT:  reasoning / spec writing / RA / gate evaluation
  - Gemini:   exploration / literature / knowledge retrieval
"""

from __future__ import annotations

from enum import Enum


class TaskType(str, Enum):
    """Semantic task categories for model routing."""

    # ── Claude-affinity tasks ─────────────────────────────────────
    CODE_GENERATION = "code_generation"
    SCRIPT_BUILD = "script_build"
    STRUCTURED_EXTRACT = "structured_extract"
    REVIEW = "review"
    PACKAGING = "packaging"
    CITATION_QA = "citation_qa"

    # ── ChatGPT-affinity tasks ────────────────────────────────────
    SPEC_WRITING = "spec_writing"
    REASONING = "reasoning"
    GATE_EVALUATION = "gate_evaluation"
    CLAIMS_ANALYSIS = "claims_analysis"
    RED_TEAM = "red_team"
    SYNTHESIS = "synthesis"

    # ── Gemini-affinity tasks ─────────────────────────────────────
    EXPLORATION = "exploration"
    LITERATURE_SEARCH = "literature_search"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    FIGURE_FIRST = "figure_first"
    DATA_EXPLORE = "data_explore"

    # ── Phase E additions ──────────────────────────────────────────
    HYPOTHESIS_GENERATION = "hypothesis_generation"
    TRANSLATION = "translation"
    CONTEXT_COMPRESS = "context_compress"
    INTAKE = "intake"

    # ── Boundary / generic ────────────────────────────────────────
    BOUNDARY_CHECK = "boundary_check"
    CUSTOM = "custom"

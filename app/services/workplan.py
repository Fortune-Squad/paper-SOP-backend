"""
WorkPlan — M2M multi-phase execution plan data structures.

Defines the plan that governs how multiple AI models collaborate
on a research task.  Each WorkPlan contains phases, each phase has
an owner model, partner models, acceptance criteria, and optional
warning gates / convergence settings.

Serialise with ``dataclasses.asdict(workplan)``.
Load/dump via ``WorkPlanLoader.load`` / ``WorkPlanLoader.dump``.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


# ── sub-structures ──────────────────────────────────────────────────


@dataclass
class ConvergenceConfig:
    """Controls iteration limits and escalation for a phase."""

    max_iterations: int = 5
    escalation_trigger: str = ""
    escalation_target: str = "chatgpt"
    abort_trigger: str = ""
    abort_action: str = "BLOCK"


@dataclass
class Phase:
    """A single execution phase within a WorkPlan."""

    phase_id: str = ""
    title: str = ""
    owner: str = ""                    # "chatgpt" | "claude" | "gemini"
    partners: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    warning_gates: List[str] = field(default_factory=list)
    prompt_templates: Dict[str, str] = field(default_factory=dict)
    convergence: Optional[ConvergenceConfig] = None


@dataclass
class WorkPlan:
    """Top-level M2M execution plan."""

    workplan_id: str = ""
    title: str = ""
    north_star: str = ""
    handoff_protocol: str = "m2m-tp/0.2"
    claims: List[str] = field(default_factory=list)
    scope_in: List[str] = field(default_factory=list)
    scope_out: List[str] = field(default_factory=list)
    agents: List[str] = field(default_factory=list)
    warning_gates: List[str] = field(default_factory=list)
    phases: List[Phase] = field(default_factory=list)


# ── loader / validator / dumper ─────────────────────────────────────


class WorkPlanLoader:
    """Load, validate, and dump WorkPlan YAML files."""

    @staticmethod
    def load(yaml_path: str) -> WorkPlan:
        """Deserialise a WorkPlan from a YAML file."""
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw: Dict[str, Any] = yaml.safe_load(f) or {}

        phases: List[Phase] = []
        for p in raw.get("phases", []):
            conv_raw = p.get("convergence")
            conv = ConvergenceConfig(**conv_raw) if conv_raw else None
            phases.append(
                Phase(
                    phase_id=p.get("phase_id", ""),
                    title=p.get("title", ""),
                    owner=p.get("owner", ""),
                    partners=p.get("partners", []),
                    inputs=p.get("inputs", []),
                    outputs=p.get("outputs", []),
                    acceptance_criteria=p.get("acceptance_criteria", []),
                    warning_gates=p.get("warning_gates", []),
                    prompt_templates=p.get("prompt_templates", {}),
                    convergence=conv,
                )
            )

        return WorkPlan(
            workplan_id=raw.get("workplan_id", ""),
            title=raw.get("title", ""),
            north_star=raw.get("north_star", ""),
            handoff_protocol=raw.get("handoff_protocol", "m2m-tp/0.2"),
            claims=raw.get("claims", []),
            scope_in=raw.get("scope_in", []),
            scope_out=raw.get("scope_out", []),
            agents=raw.get("agents", []),
            warning_gates=raw.get("warning_gates", []),
            phases=phases,
        )

    @staticmethod
    def validate(workplan: WorkPlan) -> List[str]:
        """Return a list of validation errors.  Empty list == valid."""
        errors: List[str] = []
        if not workplan.workplan_id:
            errors.append("WorkPlan missing workplan_id")
        if not workplan.title:
            errors.append("WorkPlan missing title")
        if not workplan.north_star:
            errors.append("WorkPlan missing north_star")
        for phase in workplan.phases:
            if not phase.phase_id:
                errors.append("Phase missing phase_id")
            if not phase.owner:
                errors.append(f"{phase.phase_id or '?'} missing owner")
            if not phase.acceptance_criteria:
                errors.append(
                    f"{phase.phase_id or '?'} missing acceptance_criteria"
                )
        return errors

    @staticmethod
    def dump(workplan: WorkPlan, yaml_path: str) -> None:
        """Serialise a WorkPlan to a YAML file."""
        data = asdict(workplan)
        os.makedirs(os.path.dirname(yaml_path) or ".", exist_ok=True)
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

    # ── Phase C: construct WorkPlan from Step 2 outputs ───────────

    @staticmethod
    def from_plan_freeze(
        program_spec: str,
        data_sim_spec: str,
        eng_decomp: str,
        project_id: str,
    ) -> WorkPlan:
        """Build a WorkPlan skeleton from Step 2's three main outputs.

        Best-effort extraction — never raises on bad input; returns a
        WorkPlan with whatever could be parsed plus sensible defaults.

        Args:
            program_spec: Full Proposal (``02_Full_Proposal.md``) content.
            data_sim_spec: Data / Simulation Spec content (may be empty).
            eng_decomp: Engineering Spec (``03_Engineering_Spec.md``) content.
            project_id: Current project identifier.

        Returns:
            A populated :class:`WorkPlan`.
        """
        north_star = _extract_north_star(program_spec)
        claims = _extract_claims(program_spec)
        scope_in, scope_out = _extract_scope(program_spec)
        phases = _extract_phases(eng_decomp)

        # Fallback: if no phases could be parsed, create one default phase
        if not phases:
            phases = [
                Phase(
                    phase_id="wp_default",
                    title="Full execution",
                    owner="chatgpt",
                    acceptance_criteria=["All sanity checks pass"],
                    convergence=ConvergenceConfig(max_iterations=5),
                )
            ]

        return WorkPlan(
            workplan_id=f"wp-{project_id[:32]}-{uuid.uuid4().hex[:8]}",
            title=f"WorkPlan for {project_id}",
            north_star=north_star,
            claims=claims,
            scope_in=scope_in,
            scope_out=scope_out,
            agents=["chatgpt", "gemini", "claude"],
            warning_gates=["gate_2"],
            phases=phases,
        )


# ── private helpers for from_plan_freeze ──────────────────────────


def _extract_north_star(program_spec: str) -> str:
    """Extract the primary research question / hypothesis."""
    if not program_spec:
        return "Research objective (auto-extracted)"
    # Try common heading patterns
    for pattern in [
        r"(?i)(?:research\s+question|hypothesis|objective|north.?star)[:\s]*\n+(.+)",
        r"(?i)##\s*(?:1\.|system|study)\s*(?:model|design)?[^\n]*\n+(.*?)(?:\n##|\Z)",
    ]:
        m = re.search(pattern, program_spec, re.DOTALL)
        if m:
            text = m.group(1).strip().split("\n")[0].strip()
            if len(text) > 10:
                return text[:500]
    # Fallback: first non-empty, non-YAML line after front-matter
    lines = _strip_frontmatter(program_spec).split("\n")
    for line in lines:
        clean = line.strip().lstrip("#").strip()
        if len(clean) > 15 and not clean.startswith("doc_type"):
            return clean[:500]
    return "Research objective (auto-extracted)"


def _extract_claims(program_spec: str) -> List[str]:
    """Extract claim statements from the proposal."""
    claims: List[str] = []
    if not program_spec:
        return claims
    # Look for numbered claims (C1, C2, ...) or bullet claims
    for m in re.finditer(
        r"(?:^|\n)\s*(?:C\d+|Claim\s*\d+)[.:\s]+(.+)", program_spec
    ):
        c = m.group(1).strip()
        if c:
            claims.append(c[:300])
    if claims:
        return claims
    # Fallback: look for "Claim-to-Evidence" section bullets
    section = re.search(
        r"(?i)claim.to.evidence[^\n]*\n(.*?)(?:\n##|\Z)",
        program_spec,
        re.DOTALL,
    )
    if section:
        for m in re.finditer(r"[-*]\s+(.+)", section.group(1)):
            c = m.group(1).strip()
            if c and len(c) > 5:
                claims.append(c[:300])
    return claims[:20]


def _extract_scope(program_spec: str) -> tuple:
    """Return (scope_in, scope_out) lists."""
    scope_in: List[str] = []
    scope_out: List[str] = []
    if not program_spec:
        return scope_in, scope_out
    for label, target in [("scope.in", scope_in), ("in.scope", scope_in),
                          ("scope.out", scope_out), ("out.of.scope", scope_out)]:
        sec = re.search(
            rf"(?i){label}[^\n]*\n(.*?)(?:\n##|\Z)",
            program_spec,
            re.DOTALL,
        )
        if sec:
            for m in re.finditer(r"[-*]\s+(.+)", sec.group(1)):
                target.append(m.group(1).strip()[:200])
    return scope_in, scope_out


def _extract_phases(eng_decomp: str) -> List[Phase]:
    """Parse engineering spec modules into Phase objects."""
    phases: List[Phase] = []
    if not eng_decomp:
        return phases

    body = _strip_frontmatter(eng_decomp)

    # Strategy 1: match "### Module <ID>" or "### <ID>." or "### M<N>" headings
    module_blocks = re.split(
        r"\n###\s+(?:Module\s+)?([A-Za-z0-9_.-]+)[.:\s]",
        body,
    )

    if len(module_blocks) >= 3:
        # module_blocks = [preamble, id1, content1, id2, content2, ...]
        for i in range(1, len(module_blocks) - 1, 2):
            mod_id = module_blocks[i].strip()
            mod_content = module_blocks[i + 1]
            phase = _parse_module_block(mod_id, mod_content)
            if phase:
                phases.append(phase)

    # Strategy 2: numbered list items ("1. **ModuleName** — ...")
    if not phases:
        for m in re.finditer(
            r"\n\d+\.\s+\*{0,2}([^*\n]+?)\*{0,2}\s*[-—:]\s*(.+?)(?=\n\d+\.|\n##|\Z)",
            body,
            re.DOTALL,
        ):
            title = m.group(1).strip()
            content = m.group(2).strip()
            mod_id = re.sub(r"\W+", "_", title.lower())[:30]
            phases.append(
                Phase(
                    phase_id=mod_id,
                    title=title[:120],
                    owner="chatgpt",
                    acceptance_criteria=_extract_bullets(content, limit=3)
                    or [f"{title} verified"],
                    convergence=ConvergenceConfig(max_iterations=5),
                )
            )

    return phases


def _parse_module_block(mod_id: str, content: str) -> Optional[Phase]:
    """Convert a single module text block to a Phase."""
    # Title: first non-empty line
    lines = [l.strip() for l in content.split("\n") if l.strip()]
    title = lines[0] if lines else mod_id
    title = title.lstrip("#").strip("*: ").strip()[:120]

    # Owner heuristic
    owner = "chatgpt"
    low = content.lower()
    if "gemini" in low:
        owner = "gemini"
    elif "claude" in low:
        owner = "claude"

    # Inputs / outputs
    inputs = _extract_section_items(content, r"input")
    outputs = _extract_section_items(content, r"output")

    # Acceptance criteria from "Verification" or bullet items
    criteria = _extract_section_items(content, r"(?:verif|acceptance|pass)")
    if not criteria:
        criteria = _extract_bullets(content, limit=3) or [f"{title} completed"]

    return Phase(
        phase_id=mod_id,
        title=title,
        owner=owner,
        inputs=inputs,
        outputs=outputs,
        acceptance_criteria=criteria,
        convergence=ConvergenceConfig(max_iterations=5),
    )


def _extract_section_items(text: str, heading_pat: str) -> List[str]:
    """Extract bullet items under a sub-heading matching *heading_pat*."""
    sec = re.search(
        rf"(?:^|\n)\s*[-*]?\s*\**{heading_pat}[^:\n]*:\**\s*(.*?)(?:\n\s*[-*]?\s*\**(?:Output|Input|Verif|Accept|Purpose)|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not sec:
        return []
    return _extract_bullets(sec.group(1), limit=10)


def _extract_bullets(text: str, limit: int = 5) -> List[str]:
    """Return up to *limit* bullet / dash items from *text*."""
    items: List[str] = []
    for m in re.finditer(r"[-*]\s+(.+)", text):
        v = m.group(1).strip()
        if v:
            items.append(v[:200])
        if len(items) >= limit:
            break
    return items


def _strip_frontmatter(text: str) -> str:
    """Remove leading YAML front-matter (--- ... ---) from markdown."""
    stripped = re.sub(r"\A---.*?---\s*", "", text, count=1, flags=re.DOTALL)
    return stripped

"""
Model Router for the Autopilot dispatch loop.

Provides a centralised routing table that maps (module, stage) pairs to
a RouteDecision describing *which* AI model should handle the stage,
*how* the request is delivered, and what the escalation chain looks like
if the primary model fails or times out.

Phase E adds **model-level smart routing**: callers pass a BudgetMode and
the router returns a concrete model ID + decision trace, replacing the
previous brand-level static lookup.

Design goals
────────────
1. **Standalone** – zero imports from sop.autopilot.* so the module can
   be tested, versioned, and reasoned about independently of the rest of
   the autopilot engine.
2. **Stdlib-only** – dataclasses + enum + typing; no third-party deps.
3. **Additive** – existing files are never modified; the autopilot loop
   can opt-in to using ModelRouter at its own pace.

Typical usage
─────────────
    from sop.autopilot.model_router import create_default_router, BudgetMode

    router = create_default_router()
    decision = router.resolve("autopilot", "generate_candidates")
    print(decision.target_model, decision.delivery_method)

    # Smart routing (Phase E)
    decision = router.resolve_by_task("code_generation", budget_mode=BudgetMode.ECONOMY)
    print(decision.resolved_model_id, decision.decision_trace)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────

class TargetModel(Enum):
    """AI models that the system can route work to."""
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    HUMAN = "human"


class DeliveryMethod(Enum):
    """How a prompt reaches its target model."""
    DIRECT_API = "direct_api"
    HUMAN_RELAY = "human_relay"
    AGENTIC_WRAPPER = "agentic_wrapper"
    LOCAL_CLI = "local_cli"


class BudgetMode(str, Enum):
    """Cost/quality trade-off selector for smart routing."""
    PERFORMANCE = "performance"
    BALANCED = "balanced"
    ECONOMY = "economy"


# ── ModelSpec + MODELS catalog (Phase E) ─────────────────────────────

@dataclass(frozen=True)
class ModelSpec:
    """Capability + cost descriptor for a concrete model ID."""
    provider: str           # "anthropic" | "openai" | "google"
    model_id: str           # API model string
    input_cost_per_m: float
    output_cost_per_m: float
    max_context: int
    supports_thinking: bool = False
    supports_vision: bool = False


MODELS: Dict[str, ModelSpec] = {
    # Anthropic
    "claude-opus-4-6":       ModelSpec("anthropic", "claude-opus-4-6",       5.00, 25.00, 200_000, True, True),
    "claude-sonnet-4-6":     ModelSpec("anthropic", "claude-sonnet-4-6",     3.00, 15.00, 200_000, True, True),
    "claude-haiku-4-5":      ModelSpec("anthropic", "claude-haiku-4-5",      1.00,  5.00, 200_000, True, True),
    # OpenAI
    "gpt-5.2":               ModelSpec("openai",    "gpt-5.2",              1.75, 14.00, 128_000, False, False),
    "gpt-5":                 ModelSpec("openai",    "gpt-5",                1.25, 10.00, 128_000, False, False),
    "gpt-4.1":               ModelSpec("openai",    "gpt-4.1",              2.00,  8.00, 1_000_000, False, True),
    "gpt-4.1-mini":          ModelSpec("openai",    "gpt-4.1-mini",         0.40,  1.60, 1_000_000, False, True),
    "gpt-4.1-nano":          ModelSpec("openai",    "gpt-4.1-nano",         0.10,  0.40, 1_000_000, False, False),
    "o3":                    ModelSpec("openai",    "o3",                   2.00,  8.00, 200_000, True, False),
    "o4-mini":               ModelSpec("openai",    "o4-mini",              1.10,  4.40, 200_000, True, False),
    "gpt-4o":                ModelSpec("openai",    "gpt-4o",               2.50, 10.00, 128_000, False, True),
    "gpt-4o-mini":           ModelSpec("openai",    "gpt-4o-mini",          0.15,  0.60, 128_000, False, True),
    # Google
    "gemini-3.1-pro":        ModelSpec("google",    "gemini-3.1-pro-preview", 2.00, 12.00, 1_000_000, True, True),
    "gemini-3-flash":        ModelSpec("google",    "gemini-3-flash",       0.50,  3.00, 1_000_000, True, True),
    "gemini-2.5-pro":        ModelSpec("google",    "gemini-2.5-pro",       1.25, 10.00, 1_000_000, True, True),
    "gemini-2.5-flash":      ModelSpec("google",    "gemini-2.5-flash",     0.30,  2.50, 1_000_000, True, True),
    "gemini-2.5-flash-lite": ModelSpec("google",    "gemini-2.5-flash-lite", 0.10, 0.40, 1_000_000, False, False),
    "gemini-2.0-flash":      ModelSpec("google",    "gemini-2.0-flash",     0.10,  0.40, 1_000_000, False, True),
    "gemini-2.0-flash-lite": ModelSpec("google",    "gemini-2.0-flash-lite", 0.075, 0.30, 1_000_000, False, False),
}


# ── TASK_MODEL_POOL + QUALITY_FLOOR (Phase E) ───────────────────────

# task_type → [PERFORMANCE, BALANCED, ECONOMY]
TASK_MODEL_POOL: Dict[str, List[str]] = {
    # Claude 主场
    "code_generation":      ["claude-sonnet-4-6", "gpt-5.2", "gpt-4.1-mini"],
    "script_build":         ["claude-sonnet-4-6", "claude-haiku-4-5"],
    "structured_extract":   ["claude-haiku-4-5", "gpt-4.1-nano", "gemini-2.0-flash-lite"],
    "review":               ["claude-sonnet-4-6", "claude-haiku-4-5"],
    "packaging":            ["claude-haiku-4-5", "gpt-4.1-nano"],
    "citation_qa":          ["claude-haiku-4-5", "gemini-2.0-flash"],
    # ChatGPT 主场
    "spec_writing":         ["gpt-5.2", "gpt-5", "gpt-4.1-mini"],
    "reasoning":            ["o3", "gpt-5.2", "o4-mini"],
    "gate_evaluation":      ["gpt-5.2", "gpt-5", "gpt-4.1-mini"],
    "claims_analysis":      ["o3", "gpt-5.2", "gpt-5"],
    "red_team":             ["gpt-5.2", "gpt-5"],
    "synthesis":            ["gpt-5", "gemini-2.5-pro", "gpt-4.1-mini"],
    # Gemini 主场
    "exploration":          ["gemini-2.5-flash", "gemini-3-flash", "gemini-2.0-flash-lite"],
    "literature_search":    ["gemini-2.5-flash", "gemini-3-flash", "gemini-2.0-flash"],
    "knowledge_retrieval":  ["gemini-2.5-flash", "gemini-2.0-flash"],
    "figure_first":         ["gemini-3.1-pro", "gemini-3-flash", "gpt-4o"],
    "data_explore":         ["gemini-2.5-flash", "gemini-3-flash"],
    "hypothesis_generation": ["gemini-3.1-pro", "gemini-3-flash", "gemini-2.5-flash"],
    # 边界/辅助
    "intake":               ["gpt-5", "gpt-4.1-mini"],
    "boundary_check":       ["claude-haiku-4-5", "gpt-4.1-nano"],
    "translation":          ["gpt-5", "claude-sonnet-4-6", "gpt-4.1-mini"],
    "context_compress":     ["gemini-2.5-flash", "gpt-4.1", "gpt-4.1-mini"],
}

# High-risk tasks: floor = BALANCED (cannot be downgraded to ECONOMY)
QUALITY_FLOOR: Dict[str, BudgetMode] = {
    "gate_evaluation":   BudgetMode.BALANCED,
    "spec_writing":      BudgetMode.BALANCED,
    "claims_analysis":   BudgetMode.BALANCED,
    "reasoning":         BudgetMode.BALANCED,
    "red_team":          BudgetMode.BALANCED,
    "review":            BudgetMode.BALANCED,
}
# Unlisted task_types default to ECONOMY


# ── Smart routing helpers (Phase E) ──────────────────────────────────

_BUDGET_PRIORITY = {BudgetMode.ECONOMY: 0, BudgetMode.BALANCED: 1, BudgetMode.PERFORMANCE: 2}


def adjust_budget_mode(
    requested: BudgetMode,
    task_type: str,
    context: dict,
) -> BudgetMode:
    """Adjust BudgetMode under QualityFloor constraints and context signals."""
    floor = QUALITY_FLOOR.get(task_type, BudgetMode.ECONOMY)

    # Auto-upgrade: retry or iteration count > 2
    if context.get("is_retry") or context.get("wp_iteration", 0) > 2:
        mode = BudgetMode.PERFORMANCE
    else:
        mode = requested

    # Auto-downgrade: only low-risk + very short tasks
    if floor == BudgetMode.ECONOMY:
        token_est = context.get("token_estimate", 0)
        if 0 < token_est < 500:
            mode = BudgetMode.ECONOMY

    # Floor enforcement: never go below quality floor
    if _BUDGET_PRIORITY[mode] < _BUDGET_PRIORITY[floor]:
        mode = floor

    return mode


def capability_guard(model_id: str, context: dict) -> bool:
    """Check if a candidate model meets hard capability requirements."""
    spec = MODELS[model_id]
    token_est = context.get("token_estimate", 0)
    if token_est > spec.max_context:
        return False
    if context.get("requires_vision") and not spec.supports_vision:
        return False
    return True


# ── RouteDecision ────────────────────────────────────────────────────

@dataclass(frozen=True)
class RouteDecision:
    """Immutable description of how a single (module, stage) should be routed."""
    target_model: TargetModel
    delivery_method: DeliveryMethod
    prompt_template: Optional[str] = None
    timeout_seconds: int = 300
    escalation_chain: List[TargetModel] = field(default_factory=list)
    agentic_wrapper_config: dict = field(default_factory=dict)
    max_retries: int = 2
    # v1.4 Phase 1: routing provenance fields
    source: str = "default"
    task_type: Optional[str] = None
    # Phase E: smart routing fields
    model_pool: tuple = ()
    resolved_model_id: Optional[str] = None
    decision_trace: Optional[dict] = None


# ── ModelRouter ──────────────────────────────────────────────────────

class ModelRouter:
    """Registry of per-module, per-stage route decisions.

    Modules are top-level namespaces (e.g. ``"autopilot"``, ``"paper_sop"``).
    Stages are workflow phases *within* a module (e.g. ``"generate_candidates"``).
    """

    def __init__(self) -> None:
        self._tables: Dict[str, Dict[str, RouteDecision]] = {}

    # ── mutation ──────────────────────────────────────────────────

    def register_module(self, module_name: str, routes: Dict[str, RouteDecision]) -> None:
        """Register (or overwrite) the full route table for *module_name*."""
        self._tables[module_name] = dict(routes)

    # ── lookup ───────────────────────────────────────────────────

    def resolve(self, module_name: str, stage: str) -> RouteDecision:
        """Return the RouteDecision for *(module_name, stage)*.

        Raises
        ------
        KeyError
            If *module_name* is not registered **or** *stage* is not
            present in that module's table.  The error message lists
            all available modules / stages so the caller can self-diagnose.
        """
        table = self._tables.get(module_name)
        if table is None:
            available = ", ".join(sorted(self._tables)) or "(none)"
            raise KeyError(
                f"module '{module_name}' is not registered. "
                f"Available modules: {available}"
            )
        decision = table.get(stage)
        if decision is None:
            available = ", ".join(sorted(table)) or "(none)"
            raise KeyError(
                f"stage '{stage}' not found in module '{module_name}'. "
                f"Available stages: {available}"
            )
        return decision

    # ── task-type routing (v1.4 Phase 1 + Phase E smart routing) ─

    _BUDGET_UNSET = object()  # sentinel for backward-compat detection

    def resolve_by_task(
        self,
        task_type: str,
        budget_mode: object = _BUDGET_UNSET,
        slot: Optional[str] = None,
        stage_key: Optional[str] = None,
        wp_owner: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> RouteDecision:
        """Four-tier route resolution with model-level smart routing.

        Priority (highest → lowest):
          Tier 1: slot_route — (slot, stage_key) exact match in registered modules
          Tier 2: task_type — TASK_MODEL_POOL lookup
          Tier 3: wp_owner  — owner string → model fallback
          Tier 4: global    — chatgpt / gpt-5

        When *budget_mode* is explicitly passed, Phase E smart routing
        activates: BudgetMode selection, QualityFloor enforcement,
        capability_guard filtering, and decision_trace for explainability.

        When *budget_mode* is omitted, legacy behavior is preserved
        (brand-level routing from DEFAULT_TASK_ROUTES).

        Returns a RouteDecision with *source* set to the tier that matched.
        Never raises; always returns a valid decision.
        """
        # Legacy path: budget_mode not explicitly provided → old behavior
        if budget_mode is self._BUDGET_UNSET:
            return self._resolve_by_task_legacy(task_type, slot, stage_key, wp_owner)

        # Smart routing path (Phase E)
        context = context or {}
        budget_mode_e: BudgetMode = budget_mode  # type: ignore[assignment]

        # Step 1: pick route source (four-tier cascade)
        source, base_pool, slot_base = self._pick_route_source(
            task_type, slot, stage_key, wp_owner,
        )

        # Step 2: adjust budget mode + resolve concrete model from pool
        final_mode = adjust_budget_mode(budget_mode_e, task_type, context)
        model_id, skip_reasons = self._resolve_model_from_pool(base_pool, final_mode, context)

        spec = MODELS.get(model_id)
        if spec:
            _PROVIDER_MAP = {
                "anthropic": TargetModel.CLAUDE,
                "openai": TargetModel.CHATGPT,
                "google": TargetModel.GEMINI,
            }
            target_model = _PROVIDER_MAP[spec.provider]
            delivery = self._infer_delivery(spec, context)
        else:
            target_model = DEFAULT_TASK_ROUTES.get(task_type, TargetModel.CHATGPT)
            delivery = DeliveryMethod.DIRECT_API

        trace = {
            "tier_source": source,
            "requested_budget_mode": budget_mode_e.value,
            "floor_adjusted_mode": final_mode.value,
            "chosen_model_id": model_id,
            "pool_candidates": list(base_pool),
            "skip_reasons": skip_reasons,
        }

        logger.info(
            "resolve_by_task: task=%s model=%s source=%s budget=%s→%s",
            task_type, model_id, source,
            budget_mode_e.value, final_mode.value,
        )

        # Tier 1 (slot_route): preserve delivery_method + other fields from slot
        if slot_base is not None:
            return RouteDecision(
                target_model=target_model,
                delivery_method=slot_base.delivery_method,
                prompt_template=slot_base.prompt_template,
                timeout_seconds=slot_base.timeout_seconds,
                escalation_chain=slot_base.escalation_chain,
                agentic_wrapper_config=slot_base.agentic_wrapper_config,
                max_retries=slot_base.max_retries,
                source=source,
                task_type=task_type,
                model_pool=tuple(base_pool),
                resolved_model_id=model_id,
                decision_trace=trace,
            )

        return RouteDecision(
            target_model=target_model,
            delivery_method=delivery,
            source=source,
            task_type=task_type,
            model_pool=tuple(base_pool),
            resolved_model_id=model_id,
            decision_trace=trace,
        )

    # ── legacy resolve_by_task (backward compat) ─────────────

    def _resolve_by_task_legacy(
        self, task_type: str, slot: Optional[str],
        stage_key: Optional[str], wp_owner: Optional[str],
    ) -> RouteDecision:
        """Original four-tier brand-level routing (pre-Phase E)."""
        # Tier 1: slot route table
        if slot and stage_key:
            table = self._tables.get(slot)
            if table and stage_key in table:
                base = table[stage_key]
                return RouteDecision(
                    target_model=base.target_model,
                    delivery_method=base.delivery_method,
                    prompt_template=base.prompt_template,
                    timeout_seconds=base.timeout_seconds,
                    escalation_chain=base.escalation_chain,
                    agentic_wrapper_config=base.agentic_wrapper_config,
                    max_retries=base.max_retries,
                    source="slot_route",
                    task_type=task_type,
                )

        # Tier 2: task_type default routes
        task_route = DEFAULT_TASK_ROUTES.get(task_type)
        if task_route is not None:
            return RouteDecision(
                target_model=task_route,
                delivery_method=DeliveryMethod.DIRECT_API,
                source="task_type",
                task_type=task_type,
            )

        # Tier 3: wp_owner fallback
        if wp_owner:
            model = _owner_to_target_model(wp_owner)
            return RouteDecision(
                target_model=model,
                delivery_method=DeliveryMethod.DIRECT_API,
                source="wp_owner",
                task_type=task_type,
            )

        # Tier 4: global default
        return RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.DIRECT_API,
            source="global_default",
            task_type=task_type,
        )

    # ── smart routing internals (Phase E) ─────────────────────

    def _pick_route_source(
        self, task_type: str, slot: Optional[str],
        stage_key: Optional[str], wp_owner: Optional[str],
    ) -> Tuple[str, List[str], Optional[RouteDecision]]:
        """Four-tier cascade → (source_name, model_pool, slot_base_or_None)."""
        # Tier 1: slot route table (slot overrides task_type entirely)
        if slot and stage_key:
            table = self._tables.get(slot)
            if table and stage_key in table:
                existing = table[stage_key]
                pool = self._pool_from_target(existing.target_model)
                return "slot_route", pool, existing

        # Tier 2: task_type → TASK_MODEL_POOL
        if task_type in TASK_MODEL_POOL:
            return "task_type", list(TASK_MODEL_POOL[task_type]), None

        # Tier 3: wp_owner
        if wp_owner:
            target = _owner_to_target_model(wp_owner)
            pool = self._pool_from_target(target, task_type)
            return "wp_owner", pool, None

        # Tier 4: global default
        return "global_default", ["gpt-5"], None

    @staticmethod
    def _resolve_model_from_pool(
        pool: List[str], budget_mode: BudgetMode, context: dict,
    ) -> Tuple[str, dict]:
        """Pick a model from *pool* by budget tier, skipping guard failures."""
        idx_map = {
            BudgetMode.PERFORMANCE: 0,
            BudgetMode.BALANCED: min(1, len(pool) - 1),
            BudgetMode.ECONOMY: len(pool) - 1,
        }
        start_idx = idx_map[budget_mode]
        skip_reasons: dict = {}

        # Walk from target tier toward PERFORMANCE (index 0)
        for i in range(start_idx, -1, -1):
            model_id = pool[i]
            if model_id in MODELS and capability_guard(model_id, context):
                return model_id, skip_reasons
            else:
                reason = "capability_guard_failed" if model_id in MODELS else "model_not_found"
                skip_reasons[model_id] = reason

        # All skipped → fallback to pool[0] (strongest)
        return pool[0], skip_reasons

    @staticmethod
    def _infer_delivery(spec: ModelSpec, context: Optional[dict] = None) -> DeliveryMethod:
        """Infer delivery method from ModelSpec provider."""
        if spec.provider == "anthropic":
            return DeliveryMethod.LOCAL_CLI
        return DeliveryMethod.HUMAN_RELAY

    @staticmethod
    def _pool_from_target(target_model: TargetModel, task_type: Optional[str] = None) -> List[str]:
        """Derive a model pool from TargetModel (backward compat bridge)."""
        # Prefer task_type pool if available
        if task_type and task_type in TASK_MODEL_POOL:
            return list(TASK_MODEL_POOL[task_type])
        # Otherwise brand defaults
        defaults = {
            TargetModel.CLAUDE:  ["claude-sonnet-4-6", "claude-haiku-4-5"],
            TargetModel.CHATGPT: ["gpt-5.2", "gpt-5", "gpt-4.1-mini"],
            TargetModel.GEMINI:  ["gemini-2.5-flash", "gemini-3-flash", "gemini-2.0-flash-lite"],
            TargetModel.HUMAN:   ["gpt-5"],
        }
        return list(defaults.get(target_model, ["gpt-5"]))

    # ── introspection ────────────────────────────────────────────

    def list_modules(self) -> List[str]:
        """Return sorted list of registered module names."""
        return sorted(self._tables)

    def list_stages(self, module_name: str) -> List[str]:
        """Return sorted list of stage names for *module_name*.

        Raises
        ------
        KeyError
            If *module_name* is not registered.
        """
        table = self._tables.get(module_name)
        if table is None:
            available = ", ".join(sorted(self._tables)) or "(none)"
            raise KeyError(
                f"module '{module_name}' is not registered. "
                f"Available modules: {available}"
            )
        return sorted(table)


# ── Task-type default routes (v1.4 Phase 1 — DevSpec Addendum §A4) ──

DEFAULT_TASK_ROUTES: Dict[str, TargetModel] = {
    # Claude-affinity
    "code_generation": TargetModel.CLAUDE,
    "script_build": TargetModel.CLAUDE,
    "structured_extract": TargetModel.CLAUDE,
    "review": TargetModel.CLAUDE,
    "packaging": TargetModel.CLAUDE,
    "citation_qa": TargetModel.CLAUDE,
    # ChatGPT-affinity
    "spec_writing": TargetModel.CHATGPT,
    "reasoning": TargetModel.CHATGPT,
    "gate_evaluation": TargetModel.CHATGPT,
    "claims_analysis": TargetModel.CHATGPT,
    "red_team": TargetModel.CHATGPT,
    "synthesis": TargetModel.CHATGPT,
    # Gemini-affinity
    "exploration": TargetModel.GEMINI,
    "literature_search": TargetModel.GEMINI,
    "knowledge_retrieval": TargetModel.GEMINI,
    "figure_first": TargetModel.GEMINI,
    "data_explore": TargetModel.GEMINI,
    "hypothesis_generation": TargetModel.GEMINI,
    # Boundary / auxiliary (Phase E)
    "boundary_check": TargetModel.CLAUDE,
    "intake": TargetModel.CHATGPT,
    "translation": TargetModel.CHATGPT,
    "context_compress": TargetModel.GEMINI,
}


def _owner_to_target_model(owner: str) -> TargetModel:
    """Map an owner string (e.g. ``"gemini"``) to a TargetModel enum."""
    low = owner.lower()
    if low in ("gemini", "gemini-2.0-flash"):
        return TargetModel.GEMINI
    if low.startswith("claude") or low in ("claude-sonnet", "claude-opus", "claude-sonnet-4-6"):
        return TargetModel.CLAUDE
    return TargetModel.CHATGPT


# ── Inverse Engine routes ────────────────────────────────────────────


def _inverse_route(model: str, tmpl: str, **kwargs) -> RouteDecision:
    """Shortcut builder. Claude → LOCAL_CLI, others → HUMAN_RELAY."""
    target = TargetModel(model)
    if model == "claude":
        delivery = DeliveryMethod.LOCAL_CLI
    else:
        delivery = DeliveryMethod.HUMAN_RELAY
    return RouteDecision(
        target_model=target,
        delivery_method=delivery,
        prompt_template=f"prompts/inverse/{tmpl}.md",
        **kwargs,
    )


INVERSE_ROUTES: Dict[Tuple[str, str], RouteDecision] = {
    # ── M1 Debunk (踢馆) ──
    ("debunk", "intake"):       _inverse_route("chatgpt", "debunk_intake"),
    ("debunk", "decompose"):    _inverse_route("chatgpt", "debunk_decompose"),
    ("debunk", "plan"):         _inverse_route("chatgpt", "debunk_plan"),
    ("debunk", "execute"):      _inverse_route("claude",  "debunk_execute"),
    ("debunk", "analyze"):      _inverse_route("chatgpt", "debunk_analyze"),
    ("debunk", "report"):       _inverse_route("chatgpt", "debunk_report"),

    # ── M2 Harvest (木马) ──
    ("harvest", "validate"):    _inverse_route("claude", "harvest_validate"),
    ("harvest", "check"):       _inverse_route("claude", "harvest_check"),
    ("harvest", "diagnose"):    _inverse_route("claude", "harvest_diagnose"),
    ("harvest", "respond"):     _inverse_route("claude", "harvest_respond"),

    # ── M3 Discover / Ghost (幽灵) ──
    ("discover", "sweep"):       _inverse_route("claude", "discover_sweep"),
    ("discover", "orchestrate"): _inverse_route("claude", "discover_orchestrate"),
    ("discover", "detect"):      _inverse_route("claude", "discover_detect"),
    ("discover", "hil"):         RouteDecision(
        target_model=TargetModel.HUMAN,
        delivery_method=DeliveryMethod.HUMAN_RELAY,
        prompt_template="prompts/inverse/discover_hil.md",
    ),
    ("discover", "report"):      _inverse_route("chatgpt", "discover_report"),

    # ── M4 Patent (捡漏) ──
    ("patent", "validate"):     _inverse_route("chatgpt", "patent_validate"),
    ("patent", "draft"):        _inverse_route("chatgpt", "patent_draft"),
    ("patent", "seal"):         _inverse_route("claude",  "patent_seal"),

    # ── M5 Collect (寄生层，非独立 mode) ──
    ("collect", "diagnose"):    _inverse_route("gemini", "collect_diagnose",
                                   agentic_wrapper_config={"require_citations": True}),
    ("collect", "store"):       _inverse_route("claude", "collect_store"),

    # ── 通配：任何 mode 的 escalation 统一走 Gemini 诊断 ──
    ("*", "escalation"):        _inverse_route("gemini", "escalation",
                                   agentic_wrapper_config={
                                       "require_citations": True,
                                       "max_retries": 1,
                                   }),
}


def resolve_model_route(
    mode: str, stage: str
) -> Optional[RouteDecision]:
    """Look up an inverse-engine route.  Exact match first, then wildcard.

    Args:
        mode: "debunk" | "harvest" | "discover" | "patent" | "collect"
        stage: workflow phase within the mode

    Returns:
        RouteDecision or None
    """
    key = (mode, stage)
    if key in INVERSE_ROUTES:
        return INVERSE_ROUTES[key]
    wildcard = ("*", stage)
    if wildcard in INVERSE_ROUTES:
        return INVERSE_ROUTES[wildcard]
    return None


def _build_inverse_module_tables() -> Dict[str, Dict[str, RouteDecision]]:
    """Convert tuple-keyed INVERSE_ROUTES into per-mode module tables."""
    tables: Dict[str, Dict[str, RouteDecision]] = {}
    for (mode, stage), decision in INVERSE_ROUTES.items():
        module = f"inverse.{mode}"
        tables.setdefault(module, {})[stage] = decision
    return tables


# ── Default route tables ─────────────────────────────────────────────

DEFAULT_ROUTE_TABLES: Dict[str, Dict[str, RouteDecision]] = {
    "autopilot": {
        "generate_candidates": RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.DIRECT_API,
            prompt_template=None,
            timeout_seconds=120,
            escalation_chain=[TargetModel.GEMINI, TargetModel.HUMAN],
        ),
        "score_and_decide": RouteDecision(
            target_model=TargetModel.GEMINI,
            delivery_method=DeliveryMethod.AGENTIC_WRAPPER,
            prompt_template=None,
            timeout_seconds=180,
            escalation_chain=[TargetModel.CHATGPT, TargetModel.HUMAN],
        ),
        "escalation_review": RouteDecision(
            target_model=TargetModel.HUMAN,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template=None,
            timeout_seconds=600,
            escalation_chain=[],
        ),
    },
    "seal": {
        "hash_generate": RouteDecision(
            target_model=TargetModel.CLAUDE,
            delivery_method=DeliveryMethod.DIRECT_API,
            prompt_template="Generate SHA-256 manifest for {run_dir}",
            timeout_seconds=60,
            escalation_chain=[TargetModel.HUMAN],
        ),
        "manifest_compile": RouteDecision(
            target_model=TargetModel.CLAUDE,
            delivery_method=DeliveryMethod.DIRECT_API,
            prompt_template="Compile canonical manifest JSON",
            timeout_seconds=60,
            escalation_chain=[TargetModel.HUMAN],
        ),
        "prior_art_check": RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="Search prior art for: {topic}",
            timeout_seconds=300,
            escalation_chain=[TargetModel.GEMINI, TargetModel.HUMAN],
        ),
        "patent_draft_claims": RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="Draft patent claims for: {invention}",
            timeout_seconds=600,
            escalation_chain=[TargetModel.CLAUDE, TargetModel.HUMAN],
        ),
        "patent_draft_desc": RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="Draft patent description for: {invention}",
            timeout_seconds=600,
            escalation_chain=[TargetModel.CLAUDE, TargetModel.HUMAN],
        ),
        "cross_check": RouteDecision(
            target_model=TargetModel.GEMINI,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="Cross-validate seal against: {reference}",
            timeout_seconds=300,
            escalation_chain=[TargetModel.CHATGPT, TargetModel.HUMAN],
        ),
        "git_tag": RouteDecision(
            target_model=TargetModel.CLAUDE,
            delivery_method=DeliveryMethod.DIRECT_API,
            prompt_template="Create git tag for sealed artifact",
            timeout_seconds=120,
            escalation_chain=[TargetModel.HUMAN],
        ),
        "chain_prep": RouteDecision(
            target_model=TargetModel.CLAUDE,
            delivery_method=DeliveryMethod.DIRECT_API,
            prompt_template="Prepare blockchain anchoring payload",
            timeout_seconds=180,
            escalation_chain=[TargetModel.HUMAN],
        ),
    },
    **_build_inverse_module_tables(),
    # ── D-C Protocol routes (Phase F) ────────────────────────────
    "dc.slot_a": {
        "hypothesis_gen": RouteDecision(
            target_model=TargetModel.GEMINI,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="slota/dc_phase_d",
            agentic_wrapper_config={"require_citations": False, "allow_speculation": True},
            task_type="hypothesis_generation",
        ),
        "hypothesis_judge": RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="slota/dc_phase_c",
            task_type="gate_evaluation",
        ),
    },
    "dc.idea_lab": {
        "diverge": RouteDecision(
            target_model=TargetModel.GEMINI,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="idealab/dc_phase_d",
            agentic_wrapper_config={"require_citations": False, "allow_speculation": True},
            task_type="hypothesis_generation",
        ),
        "converge": RouteDecision(
            target_model=TargetModel.CHATGPT,
            delivery_method=DeliveryMethod.HUMAN_RELAY,
            prompt_template="idealab/dc_phase_c",
            task_type="gate_evaluation",
        ),
    },
}


# ── Factory ──────────────────────────────────────────────────────────

def create_default_router() -> ModelRouter:
    """Return a ModelRouter pre-loaded with :data:`DEFAULT_ROUTE_TABLES`."""
    router = ModelRouter()
    for module_name, routes in DEFAULT_ROUTE_TABLES.items():
        router.register_module(module_name, routes)
    return router

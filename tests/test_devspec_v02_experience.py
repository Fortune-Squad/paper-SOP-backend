"""
Unit tests for DevSpec v0.2 — Pivot & Experience Inheritance.

Covers:
  1. experience_models: FailureClassification, ValidatedCheckpoint,
     RuledOutOption, ExperienceBundle, WorkPlanLifecycleEvent,
     PacketContext, inject_context()
  2. HandoffPacket / ReasoningBlock new fields (Section 5)
  3. PacketStore new queries: query_by_workplan, query_by_workphase,
     query_lineage_chain (Section 7)
  4. WorkPlan lineage fields + WorkPlanLoader YAML round-trip (Section 4.1)
  5. ExperienceBundle JSONL round-trip (Section 10.3)
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
import yaml

from app.services.experience_models import (
    FAILURE_CLASSIFICATIONS,
    ExperienceBundle,
    PacketContext,
    RuledOutOption,
    ValidatedCheckpoint,
    WorkPlanLifecycleEvent,
    inject_context,
)
from app.services.handoff_packet import HandoffPacket, ReasoningBlock
from app.services.packet_store import PacketStore
from app.services.workplan import Phase, WorkPlan, WorkPlanLoader


# ═══════════════════════════════════════════════════════════════════
# 1. experience_models — data structures
# ═══════════════════════════════════════════════════════════════════


class TestFailureClassifications:
    """FAILURE_CLASSIFICATIONS frozenset."""

    def test_contains_all_eight_values(self):
        expected = {
            "CONVERGENCE_FAILURE",
            "STRUCTURAL_INFEASIBILITY",
            "PARAMETER_SENSITIVITY",
            "IMPLEMENTATION_BUG",
            "DATA_ISSUE",
            "TOOLCHAIN_LIMITATION",
            "INSUFFICIENT_EVIDENCE",
            "UNKNOWN",
        }
        assert FAILURE_CLASSIFICATIONS == expected

    def test_is_frozenset(self):
        assert isinstance(FAILURE_CLASSIFICATIONS, frozenset)


class TestValidatedCheckpoint:
    """ValidatedCheckpoint dataclass."""

    def test_defaults(self):
        cp = ValidatedCheckpoint()
        assert cp.checkpoint_id == ""
        assert cp.title == ""
        assert cp.summary == ""
        assert cp.verification_kind is None
        assert cp.evidence_refs == []
        assert cp.artifact_refs == []
        assert cp.confidence == "MED"
        assert cp.tags == []

    def test_custom_values(self):
        cp = ValidatedCheckpoint(
            checkpoint_id="cp-001",
            title="BVP solver converges",
            summary="Verified on 3 test cases",
            verification_kind="TEST_PASS",
            evidence_refs=["ref1"],
            confidence="HIGH",
            tags=["solver", "bvp"],
        )
        assert cp.checkpoint_id == "cp-001"
        assert cp.verification_kind == "TEST_PASS"
        assert cp.confidence == "HIGH"

    def test_asdict_round_trip(self):
        cp = ValidatedCheckpoint(checkpoint_id="cp-001", title="T")
        d = asdict(cp)
        restored = ValidatedCheckpoint(**d)
        assert restored.checkpoint_id == "cp-001"


class TestRuledOutOption:
    """RuledOutOption dataclass."""

    def test_defaults(self):
        ro = RuledOutOption()
        assert ro.option_id == ""
        assert ro.description == ""
        assert ro.rejected_because == []
        assert ro.rejected_because_notes is None
        assert ro.evidence_refs == []
        assert ro.notes is None

    def test_multi_cause_rejection(self):
        ro = RuledOutOption(
            option_id="opt-imai-keane",
            description="Imai-Keane 2D DP model",
            rejected_because=[
                "STRUCTURAL_INFEASIBILITY",
                "PARAMETER_SENSITIVITY",
            ],
            rejected_because_notes="Numerical divergence at boundary",
        )
        assert len(ro.rejected_because) == 2
        assert "STRUCTURAL_INFEASIBILITY" in ro.rejected_because


class TestExperienceBundle:
    """ExperienceBundle dataclass."""

    def test_defaults(self):
        eb = ExperienceBundle()
        assert eb.bundle_id == ""
        assert eb.source_workplan_id == ""
        assert eb.source_workphase_id is None
        assert eb.created_at == ""
        assert eb.validated_checkpoints == []
        assert eb.ruled_out_options == []
        assert eb.reusable_artifact_refs == []
        assert eb.summary == ""
        assert eb.recommended_next_moves == []

    def test_with_checkpoints_and_ruled_out(self):
        eb = ExperienceBundle(
            bundle_id="eb-001",
            source_workplan_id="wp-old",
            source_workphase_id="phase-2",
            created_at="2026-03-07T12:00:00Z",
            validated_checkpoints=[
                ValidatedCheckpoint(checkpoint_id="cp-1", title="BVP OK"),
                ValidatedCheckpoint(checkpoint_id="cp-2", title="Grid OK"),
            ],
            ruled_out_options=[
                RuledOutOption(option_id="opt-1", description="Imai-Keane"),
            ],
            reusable_artifact_refs=["artifacts/grid_spec.yaml"],
            summary="Phase 2 partial results before pivot",
            recommended_next_moves=["Try Rust-Bellman instead"],
        )
        assert len(eb.validated_checkpoints) == 2
        assert len(eb.ruled_out_options) == 1
        assert eb.recommended_next_moves == ["Try Rust-Bellman instead"]


class TestWorkPlanLifecycleEvent:
    """WorkPlanLifecycleEvent dataclass."""

    def test_defaults(self):
        ev = WorkPlanLifecycleEvent()
        assert ev.event_type == ""
        assert ev.workplan_id == ""
        assert ev.timestamp == ""
        assert ev.actor == ""
        assert ev.reason is None
        assert ev.classification is None
        assert ev.evidence_refs == []
        assert ev.derived_workplan_id is None

    def test_pivot_event(self):
        ev = WorkPlanLifecycleEvent(
            event_type="PIVOTED",
            workplan_id="wp-old",
            timestamp="2026-03-07T12:00:00Z",
            actor="maxwell",
            reason="Imai-Keane numerically incompatible",
            classification="STRUCTURAL_INFEASIBILITY",
            derived_workplan_id="wp-new",
        )
        assert ev.event_type == "PIVOTED"
        assert ev.derived_workplan_id == "wp-new"


class TestPacketContext:
    """PacketContext dataclass."""

    def test_defaults(self):
        ctx = PacketContext()
        assert ctx.workplan_id is None
        assert ctx.workphase_id is None

    def test_custom_values(self):
        ctx = PacketContext(workplan_id="wp-001", workphase_id="phase-A")
        assert ctx.workplan_id == "wp-001"


# ═══════════════════════════════════════════════════════════════════
# 2. inject_context()
# ═══════════════════════════════════════════════════════════════════


class TestInjectContext:
    """inject_context() fills empty workplan/workphase IDs."""

    def test_fills_empty_string(self):
        pkt = HandoffPacket()  # workplan_id="" workphase_id=""
        ctx = PacketContext(workplan_id="wp-001", workphase_id="wph-A")
        inject_context(pkt, ctx)
        assert pkt.workplan_id == "wp-001"
        assert pkt.workphase_id == "wph-A"

    def test_preserves_existing_values(self):
        pkt = HandoffPacket(workplan_id="wp-existing", workphase_id="wph-existing")
        ctx = PacketContext(workplan_id="wp-new", workphase_id="wph-new")
        inject_context(pkt, ctx)
        assert pkt.workplan_id == "wp-existing"
        assert pkt.workphase_id == "wph-existing"

    def test_partial_fill(self):
        pkt = HandoffPacket(workplan_id="wp-existing")
        ctx = PacketContext(workplan_id="wp-new", workphase_id="wph-A")
        inject_context(pkt, ctx)
        assert pkt.workplan_id == "wp-existing"
        assert pkt.workphase_id == "wph-A"

    def test_returns_same_packet(self):
        pkt = HandoffPacket()
        ctx = PacketContext(workplan_id="wp-001")
        result = inject_context(pkt, ctx)
        assert result is pkt


# ═══════════════════════════════════════════════════════════════════
# 3. HandoffPacket / ReasoningBlock — new fields
# ═══════════════════════════════════════════════════════════════════


class TestHandoffPacketNewFields:
    """DevSpec v0.2 fields on HandoffPacket."""

    def test_defaults(self):
        pkt = HandoffPacket()
        assert pkt.workphase_id == ""
        assert pkt.risk_flags == []
        assert pkt.experience_bundle is None

    def test_risk_flags_independent(self):
        p1 = HandoffPacket()
        p2 = HandoffPacket()
        p1.risk_flags.append("flag1")
        assert p2.risk_flags == []

    def test_asdict_includes_new_fields(self):
        pkt = HandoffPacket(
            workphase_id="wph-1",
            risk_flags=["stale_data"],
        )
        d = asdict(pkt)
        assert d["workphase_id"] == "wph-1"
        assert d["risk_flags"] == ["stale_data"]
        assert d["experience_bundle"] is None


class TestReasoningBlockNewFields:
    """DevSpec v0.2 fields on ReasoningBlock."""

    def test_defaults(self):
        rb = ReasoningBlock()
        assert rb.failure_classification is None
        assert rb.validated_checkpoints == []
        assert rb.ruled_out_options == []
        assert rb.structural_evidence_refs == []
        assert rb.pivot_suggestion is None

    def test_custom_values(self):
        rb = ReasoningBlock(
            failure_classification="STRUCTURAL_INFEASIBILITY",
            structural_evidence_refs=["theorem_3_contradiction"],
            pivot_suggestion="PIVOT_MODEL",
        )
        assert rb.failure_classification == "STRUCTURAL_INFEASIBILITY"
        assert rb.pivot_suggestion == "PIVOT_MODEL"

    def test_existing_fields_unchanged(self):
        rb = ReasoningBlock(
            chain="test",
            warnings=["w1"],
            what_i_tried_but_failed=["attempt1"],
        )
        assert rb.chain == "test"
        assert rb.warnings == ["w1"]
        assert rb.what_i_tried_but_failed == ["attempt1"]


# ═══════════════════════════════════════════════════════════════════
# 4. PacketStore — new queries
# ═══════════════════════════════════════════════════════════════════


class TestPacketStoreWorkplanQueries:
    """PacketStore query_by_workplan / query_by_workphase / query_lineage_chain."""

    @pytest.fixture
    def store(self, tmp_path):
        return PacketStore(str(tmp_path))

    def _pkt(self, **overrides) -> HandoffPacket:
        defaults = dict(
            from_model="chatgpt",
            to_model="gemini",
            phase_id="p1",
            packet_type="task_dispatch",
            workplan_id="wp-001",
            workphase_id="wph-A",
        )
        defaults.update(overrides)
        return HandoffPacket(**defaults)

    def test_query_by_workplan_basic(self, store):
        store.store(self._pkt(packet_id="p1", workplan_id="wp-001"))
        store.store(self._pkt(packet_id="p2", workplan_id="wp-002"))
        store.store(self._pkt(packet_id="p3", workplan_id="wp-001"))

        results = store.query_by_workplan("wp-001")
        assert len(results) == 2
        ids = {r.packet_id for r in results}
        assert ids == {"p1", "p3"}

    def test_query_by_workplan_with_packet_types_filter(self, store):
        store.store(self._pkt(
            packet_id="p1", workplan_id="wp-001",
            packet_type="task_dispatch",
        ))
        store.store(self._pkt(
            packet_id="p2", workplan_id="wp-001",
            packet_type="result_report",
        ))
        store.store(self._pkt(
            packet_id="p3", workplan_id="wp-001",
            packet_type="task_dispatch",
        ))

        results = store.query_by_workplan(
            "wp-001", packet_types=["task_dispatch"],
        )
        assert len(results) == 2
        assert all(r.packet_type == "task_dispatch" for r in results)

    def test_query_by_workplan_excludes_empty(self, store):
        store.store(self._pkt(packet_id="p1", workplan_id="wp-001"))
        store.store(self._pkt(packet_id="p2", workplan_id=""))

        results = store.query_by_workplan("wp-001")
        assert len(results) == 1
        assert results[0].packet_id == "p1"

    def test_query_by_workphase_basic(self, store):
        store.store(self._pkt(packet_id="p1", workphase_id="wph-A"))
        store.store(self._pkt(packet_id="p2", workphase_id="wph-B"))
        store.store(self._pkt(packet_id="p3", workphase_id="wph-A"))

        results = store.query_by_workphase("wph-A")
        assert len(results) == 2

    def test_query_by_workphase_with_packet_types(self, store):
        store.store(self._pkt(
            packet_id="p1", workphase_id="wph-A",
            packet_type="task_dispatch",
        ))
        store.store(self._pkt(
            packet_id="p2", workphase_id="wph-A",
            packet_type="result_report",
        ))

        results = store.query_by_workphase(
            "wph-A", packet_types=["result_report"],
        )
        assert len(results) == 1
        assert results[0].packet_id == "p2"

    def test_query_lineage_chain_stub(self, store):
        chain = store.query_lineage_chain("wp-001")
        assert chain == ["wp-001"]

    def test_new_fields_survive_store_round_trip(self, store):
        pkt = self._pkt(
            packet_id="p1",
            workplan_id="wp-001",
            workphase_id="wph-A",
            risk_flags=["stale_data", "solver_mismatch"],
        )
        store.store(pkt)

        results = store.query_by_workplan("wp-001")
        assert len(results) == 1
        r = results[0]
        assert r.workphase_id == "wph-A"
        assert r.risk_flags == ["stale_data", "solver_mismatch"]
        assert r.experience_bundle is None

    def test_index_includes_by_workplan(self, store, tmp_path):
        store.store(self._pkt(workplan_id="wp-001"))
        store.store(self._pkt(workplan_id="wp-001"))
        store.store(self._pkt(workplan_id="wp-002"))

        with open(tmp_path / "handoff" / "index.json") as f:
            index = json.load(f)

        assert index["by_workplan"]["wp-001"] == 2
        assert index["by_workplan"]["wp-002"] == 1

    def test_index_skips_empty_workplan_id(self, store, tmp_path):
        store.store(self._pkt(workplan_id=""))

        with open(tmp_path / "handoff" / "index.json") as f:
            index = json.load(f)

        assert "by_workplan" not in index or "" not in index.get("by_workplan", {})


# ═══════════════════════════════════════════════════════════════════
# 5. WorkPlan lineage fields
# ═══════════════════════════════════════════════════════════════════


class TestWorkPlanLineage:
    """WorkPlan DevSpec v0.2 lineage fields."""

    def test_defaults(self):
        wp = WorkPlan(workplan_id="wp-001")
        assert wp.predecessor_workplan_id is None
        assert wp.pivot_reason is None
        assert wp.pivot_classification is None
        assert wp.pivot_evidence_refs == []

    def test_custom_lineage(self):
        wp = WorkPlan(
            workplan_id="wp-new",
            predecessor_workplan_id="wp-old",
            pivot_reason="Imai-Keane numerically incompatible",
            pivot_classification="STRUCTURAL_INFEASIBILITY",
            pivot_evidence_refs=["ref1", "ref2"],
        )
        assert wp.predecessor_workplan_id == "wp-old"
        assert wp.pivot_classification == "STRUCTURAL_INFEASIBILITY"
        assert len(wp.pivot_evidence_refs) == 2

    def test_asdict_includes_lineage(self):
        wp = WorkPlan(
            workplan_id="wp-new",
            predecessor_workplan_id="wp-old",
        )
        d = asdict(wp)
        assert d["predecessor_workplan_id"] == "wp-old"
        assert d["pivot_reason"] is None
        assert d["pivot_evidence_refs"] == []

    def test_yaml_round_trip_with_lineage(self, tmp_path):
        wp = WorkPlan(
            workplan_id="wp-new",
            title="Pivoted Plan",
            north_star="NS",
            predecessor_workplan_id="wp-old",
            pivot_reason="Structural failure",
            pivot_classification="STRUCTURAL_INFEASIBILITY",
            pivot_evidence_refs=["evidence_1"],
            phases=[
                Phase(
                    phase_id="p1",
                    owner="chatgpt",
                    acceptance_criteria=["done"],
                ),
            ],
        )
        yaml_file = str(tmp_path / "workplan.yaml")
        WorkPlanLoader.dump(wp, yaml_file)
        loaded = WorkPlanLoader.load(yaml_file)

        assert loaded.predecessor_workplan_id == "wp-old"
        assert loaded.pivot_reason == "Structural failure"
        assert loaded.pivot_classification == "STRUCTURAL_INFEASIBILITY"
        assert loaded.pivot_evidence_refs == ["evidence_1"]

    def test_yaml_load_without_lineage(self, tmp_path):
        yaml_file = str(tmp_path / "old_workplan.yaml")
        data = {
            "workplan_id": "wp-legacy",
            "title": "Legacy Plan",
            "north_star": "NS",
            "phases": [],
        }
        with open(yaml_file, "w") as f:
            yaml.dump(data, f)

        loaded = WorkPlanLoader.load(yaml_file)
        assert loaded.workplan_id == "wp-legacy"
        assert loaded.predecessor_workplan_id is None
        assert loaded.pivot_reason is None
        assert loaded.pivot_evidence_refs == []


# ═══════════════════════════════════════════════════════════════════
# 6. ExperienceBundle JSONL round-trip
# ═══════════════════════════════════════════════════════════════════


class TestExperienceBundleJSONL:
    """ExperienceBundle serialise/deserialise through JSONL."""

    def _make_bundle(self) -> ExperienceBundle:
        return ExperienceBundle(
            bundle_id="eb-001",
            source_workplan_id="wp-old",
            source_workphase_id="phase-2",
            created_at="2026-03-07T12:00:00Z",
            validated_checkpoints=[
                ValidatedCheckpoint(
                    checkpoint_id="cp-1",
                    title="BVP solver converges",
                    summary="OK on 3 cases",
                    verification_kind="TEST_PASS",
                    confidence="HIGH",
                ),
            ],
            ruled_out_options=[
                RuledOutOption(
                    option_id="opt-imai-keane",
                    description="Imai-Keane 2D DP",
                    rejected_because=["STRUCTURAL_INFEASIBILITY"],
                    rejected_because_notes="Numerical divergence",
                ),
            ],
            reusable_artifact_refs=["grid_spec.yaml"],
            summary="Partial results before pivot",
            recommended_next_moves=["Try Rust-Bellman"],
        )

    def test_jsonl_round_trip(self):
        bundle = self._make_bundle()
        d = asdict(bundle)
        json_str = json.dumps(d, ensure_ascii=False)
        loaded = json.loads(json_str)
        restored = ExperienceBundle(**{
            k: v for k, v in loaded.items()
            if k != "validated_checkpoints" and k != "ruled_out_options"
        })
        restored.validated_checkpoints = [
            ValidatedCheckpoint(**cp) for cp in loaded["validated_checkpoints"]
        ]
        restored.ruled_out_options = [
            RuledOutOption(**ro) for ro in loaded["ruled_out_options"]
        ]

        assert restored.bundle_id == "eb-001"
        assert len(restored.validated_checkpoints) == 1
        assert restored.validated_checkpoints[0].checkpoint_id == "cp-1"
        assert len(restored.ruled_out_options) == 1
        assert restored.ruled_out_options[0].option_id == "opt-imai-keane"
        assert restored.recommended_next_moves == ["Try Rust-Bellman"]

    def test_empty_bundle_serialisable(self):
        bundle = ExperienceBundle()
        d = asdict(bundle)
        json_str = json.dumps(d, ensure_ascii=False)
        loaded = json.loads(json_str)
        assert loaded["validated_checkpoints"] == []
        assert loaded["ruled_out_options"] == []

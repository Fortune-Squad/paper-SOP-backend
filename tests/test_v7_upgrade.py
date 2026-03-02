"""
v7 升级自动化测试

验证 v7 规格文档与代码实现的一致性：
- 数据模型（DocumentType, StepInfo, Project, Gate）
- 步骤流转（_get_next_step, _validate_step_prerequisites）
- Gate 系统
- Loop/回退系统
- Step ID 映射
- Rigor Profile

所有测试使用 mock，不调用真实 AI API。
"""
import pytest
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# ── Mock heavy dependencies BEFORE importing app modules ──────────
_MOCK_MODULES = [
    "google", "google.generativeai", "google.ai", "google.ai.generativelanguage",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "chromadb", "chromadb.config", "chromadb.api",
    "tiktoken", "openai",
]
for _mod in _MOCK_MODULES:
    sys.modules[_mod] = MagicMock()

# Models
from app.models.project import Project, ProjectConfig, StepInfo, StepStatus, ResearchType, DataStatus
from app.models.document import DocumentType
from app.models.gate import (
    GateType, GateVerdict, Gate1Checklist, Gate1_25Checklist,
    Gate0Checklist, Gate1_5Checklist, Gate1_6Checklist, Gate2Checklist,
    GateResult,
)
from app.models.rigor_profile import (
    TOP_JOURNAL_PROFILE, FAST_TRACK_PROFILE, RigorLevel, get_rigor_profile,
)

# Services & Steps
from app.services.project_manager import ProjectManager, LOOP_DEFINITIONS
from app.api.projects import VALID_STEP_IDS, VALID_GATE_NAMES

from app.steps.step0 import Step0_1_IntakeCard, Step0_2_VenueTaste
from app.steps.step1 import (
    Step1_1a_SearchPlan, Step1_1b_Hunt, Step1_1c_Synthesis,
    Step1_3b_ReferenceQA, Step1_2_TopicDecision, Step1_3_KillerPriorCheck,
    Step1_4_ClaimsFreeze, Step1_5_FigureFirstStory,
)
from app.steps.step2 import (
    Step2_0_FigureTableList, Step2_1_FullProposal, Step2_2_DataSimSpec,
    Step2_3_EngineeringDecomposition, Step2_4_RedTeamReview,
    Step2_4b_PatchPropagation, Step2_5_PlanFreeze,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _make_config() -> ProjectConfig:
    return ProjectConfig(
        topic="Test Topic",
        target_venue="NeurIPS 2025",
        research_type=ResearchType.ML,
        data_status=DataStatus.AVAILABLE,
        hard_constraints=["c1", "c2", "c3"],
        keywords=["kw1", "kw2", "kw3"],
    )


def _make_project(**overrides) -> Project:
    defaults = dict(project_id="test-proj-001", project_name="Test Project", config=_make_config())
    defaults.update(overrides)
    return Project(**defaults)


def _make_pm() -> ProjectManager:
    return ProjectManager(
        file_manager=MagicMock(), git_manager=MagicMock(),
        vector_store=MagicMock(), gate_checker=MagicMock(),
    )


# ═══════════════════════════════════════════════════════════════════
# 1. TestV7DataModels (8 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7DataModels:

    def test_document_types_exist(self):
        assert hasattr(DocumentType, "SEARCH_PLAN")
        assert hasattr(DocumentType, "RAW_INTEL_LOG")
        assert hasattr(DocumentType, "LITERATURE_MATRIX_V7")
        assert hasattr(DocumentType, "PATCH_DIFF")

    def test_gate_types_exist(self):
        assert hasattr(GateType, "GATE_0")
        assert hasattr(GateType, "GATE_1")
        assert hasattr(GateType, "GATE_1_25")
        assert hasattr(GateType, "GATE_1_5")
        assert hasattr(GateType, "GATE_1_6")
        assert hasattr(GateType, "GATE_2")

    def test_step_info_has_loop_fields(self):
        si = StepInfo(step_id="x", step_name="x")
        assert si.retry_count == 0
        assert si.max_retries == 2

    def test_project_has_loop_history(self):
        p = _make_project()
        assert p.loop_history == []

    def test_project_initializes_all_steps(self):
        p = _make_project()
        assert len(p.steps) == 26  # v7 + v1.2 step_4_repro = 26

    def test_project_step_ids_match_v7(self):
        p = _make_project()
        expected = {
            "step_s_1",
            "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
            "step_3_init", "step_3_exec",
            "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
        }
        assert set(p.steps.keys()) == expected

    def test_document_type_values(self):
        assert DocumentType.SEARCH_PLAN.value == "01_A_Search_Plan"
        assert DocumentType.RAW_INTEL_LOG.value == "01_B_Raw_Intel_Log"
        assert DocumentType.LITERATURE_MATRIX_V7.value == "01_C_Literature_Matrix"
        assert DocumentType.PATCH_DIFF.value == "03_Patch_Diff"

    def test_project_gate_fields(self):
        p = _make_project()
        assert p.gate_0_passed is False
        assert p.gate_1_passed is False
        assert p.gate_1_25_passed is True  # v7.0: deprecated, defaults to True
        assert p.gate_1_5_passed is False
        assert p.gate_1_6_passed is False
        assert p.gate_2_passed is False

# PLACEHOLDER_SEQ

# ═══════════════════════════════════════════════════════════════════
# 2. TestV7StepSequence (8 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7StepSequence:

    def setup_method(self):
        self.pm = _make_pm()

    def test_get_next_step_from_step_0_1(self):
        assert self.pm._get_next_step("step_0_1") == "step_0_2"

    def test_get_next_step_full_chain(self):
        expected = [
            "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
            "step_3_init", "step_3_exec",
            "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
        ]
        cur = expected[0]
        visited = [cur]
        while (nxt := self.pm._get_next_step(cur)) is not None:
            visited.append(nxt)
            cur = nxt
        assert visited == expected

    def test_get_next_step_last_returns_none(self):
        assert self.pm._get_next_step("step_4_package") is None

    def test_get_next_step_unknown_returns_none(self):
        assert self.pm._get_next_step("step_999") is None

    def test_validate_prerequisites_first_step(self):
        p = _make_project()
        ok, _ = self.pm._validate_step_prerequisites(p, "step_s_1")
        assert ok is True

    def test_validate_prerequisites_blocks_skip(self):
        p = _make_project()
        p.steps["step_s_1"].status = StepStatus.COMPLETED
        # step_1_1a requires step_0_1 and step_0_2 to be completed
        ok, msg = self.pm._validate_step_prerequisites(p, "step_1_1a")
        assert ok is False

    def test_validate_prerequisites_step2_needs_gate_1_5(self):
        p = _make_project()
        for sid in ["step_s_1", "step_0_1", "step_0_2",
                     "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2",
                     "step_1_3", "step_1_3b", "step_1_4", "step_1_5"]:
            p.steps[sid].status = StepStatus.COMPLETED
        p.gate_1_5_passed = False
        ok, msg = self.pm._validate_step_prerequisites(p, "step_2_0")
        assert ok is False
        assert "Gate 1.5" in msg

    def test_validate_prerequisites_allows_step2_with_gate_1_5(self):
        p = _make_project()
        for sid in ["step_s_1", "step_0_1", "step_0_2",
                     "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2",
                     "step_1_3", "step_1_3b", "step_1_4", "step_1_5"]:
            p.steps[sid].status = StepStatus.COMPLETED
        p.gate_1_5_passed = True
        ok, _ = self.pm._validate_step_prerequisites(p, "step_2_0")
        assert ok is True


# ═══════════════════════════════════════════════════════════════════
# 3. TestV7GateSystem (6 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7GateSystem:

    def test_gate_1_25_deprecated_but_exists(self):
        """v7.0: GATE_1_25 kept for backward compat but deprecated."""
        assert hasattr(GateType, "GATE_1_25")
        assert GateType.GATE_1_25.value == "gate_1_25"

    def test_gate_1_25_removed_from_valid_gate_names(self):
        """v7.0: gate_1_25 removed from VALID_GATE_NAMES (merged into gate_1)."""
        assert "gate_1_25" not in VALID_GATE_NAMES

    def test_valid_gate_names_complete(self):
        expected = {"gate_0", "gate_1", "gate_1_5", "gate_1_6", "gate_2",
                    "gate_wp", "gate_freeze", "gate_delivery"}
        assert VALID_GATE_NAMES == expected

    def test_clear_related_gates(self):
        pm = _make_pm()
        p = _make_project()
        p.gate_1_5_passed = True
        p.gate_results["gate_1_5"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_1_3")
        assert p.gate_1_5_passed is False

    def test_clear_related_gates_1_6(self):
        pm = _make_pm()
        p = _make_project()
        p.gate_1_6_passed = True
        p.gate_results["gate_1_6"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_1_3b")
        assert p.gate_1_6_passed is False

    def test_auto_gate_trigger_after_step_1_3b(self):
        async def _test():
            pm = _make_pm()
            p = _make_project()
            for sid in ["step_s_1", "step_0_1", "step_0_2",
                         "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3"]:
                p.steps[sid].status = StepStatus.COMPLETED
            with patch("app.services.project_manager.Step1_3b_ReferenceQA") as MockStep:
                MockStep.return_value.execute = AsyncMock(return_value=MagicMock())
                MockStep.return_value.ai_model = "gemini-2.0-flash"
                mock_gr = GateResult(
                    gate_type=GateType.GATE_1_6, verdict=GateVerdict.PASS,
                    check_items=[], passed_count=5, total_count=5,
                    suggestions=[], project_id=p.project_id,
                )
                pm.gate_checker.check_gate_1_6 = AsyncMock(return_value=mock_gr)
                pm._save_project = AsyncMock()
                await pm.execute_step(p, "step_1_3b")
                pm.gate_checker.check_gate_1_6.assert_awaited_once()
        asyncio.run(_test())

# PLACEHOLDER_LOOP

# ═══════════════════════════════════════════════════════════════════
# 4. TestV7LoopSystem (7 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7LoopSystem:

    def test_loop_definitions_match_spec(self):
        assert len(LOOP_DEFINITIONS) == 5
        assert LOOP_DEFINITIONS["gate_1"]["trigger_gate"] == "gate_1" if "trigger_gate" in LOOP_DEFINITIONS["gate_1"] else True
        assert LOOP_DEFINITIONS["gate_1"]["target_step"] == "step_1_1a"
        assert LOOP_DEFINITIONS["gate_1_5"]["target_step"] == "step_1_2"
        assert LOOP_DEFINITIONS["gate_1_6"]["target_step"] == "step_1_1b"  # SOP 3.3: Loop C → S1b (Hunt)
        assert LOOP_DEFINITIONS["gate_2"]["target_step"] == "step_2_1"
        assert LOOP_DEFINITIONS["red_team"]["target_step"] == "step_2_1"

    def test_loop_a_gate1_fail_rollback(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_0_1", "step_0_2",
                         "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2"]:
                p.steps[sid].status = StepStatus.COMPLETED
            result = await pm.handle_gate_failure(p, "gate_1")
            assert result["action"] == "rollback"
            assert result["target_step"] == "step_1_1a"
            assert result["loop_id"] == "loop_a"
        asyncio.run(_test())

    def test_loop_b_gate1_5_fail_rollback(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_0_1", "step_0_2",
                         "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3"]:
                p.steps[sid].status = StepStatus.COMPLETED
            result = await pm.handle_gate_failure(p, "gate_1_5")
            assert result["action"] == "rollback"
            assert result["target_step"] == "step_1_2"
            assert result["loop_id"] == "loop_b"
        asyncio.run(_test())

    def test_loop_max_retries_exhausted(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            from app.models.project import LoopHistoryEntry
            p.loop_history = [
                LoopHistoryEntry(loop_id="loop_a", gate_name="gate_1",
                                 target_step="step_1_1a", retry_number=1, action="rollback"),
                LoopHistoryEntry(loop_id="loop_a", gate_name="gate_1",
                                 target_step="step_1_1a", retry_number=2, action="rollback"),
            ]
            result = await pm.handle_gate_failure(p, "gate_1")
            assert result["action"] == "exhausted"
        asyncio.run(_test())

    def test_loop_rollback_resets_steps(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_0_1", "step_0_2",
                         "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2",
                         "step_1_3", "step_1_3b", "step_1_4", "step_1_5"]:
                p.steps[sid].status = StepStatus.COMPLETED
            await pm.handle_gate_failure(p, "gate_1")
            # step_1_1a through step_1_5 should be reset
            assert p.steps["step_1_1a"].status == StepStatus.PENDING
            assert p.steps["step_1_2"].status == StepStatus.PENDING
            # step_0_2 should remain completed
            assert p.steps["step_0_2"].status == StepStatus.COMPLETED
        asyncio.run(_test())

    def test_loop_history_recorded(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_0_1", "step_0_2",
                         "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2"]:
                p.steps[sid].status = StepStatus.COMPLETED
            assert len(p.loop_history) == 0
            await pm.handle_gate_failure(p, "gate_1")
            assert len(p.loop_history) == 1
            assert p.loop_history[0].loop_id == "loop_a"
            assert p.loop_history[0].action == "rollback"
        asyncio.run(_test())

    def test_no_loop_for_unknown_gate(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            result = await pm.handle_gate_failure(p, "gate_0")
            assert result["action"] == "no_loop"
        asyncio.run(_test())

# PLACEHOLDER_STEPID

# ═══════════════════════════════════════════════════════════════════
# 5. TestV7StepClasses (5 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7StepClasses:

    def test_step0_1_properties(self):
        p = _make_project()
        step = Step0_1_IntakeCard(p)
        assert step.step_id == "step_0_1"

    def test_step1_1_properties(self):
        p = _make_project()
        step = Step1_1a_SearchPlan(p)
        assert step.step_id == "step_1_1a"

    def test_step1_1b_properties(self):
        p = _make_project()
        step = Step1_3b_ReferenceQA(p)
        assert step.step_id == "step_1_3b"

    def test_step2_1_properties(self):
        p = _make_project()
        step = Step2_1_FullProposal(p)
        assert step.step_id == "step_2_1"

    def test_step2_5_properties(self):
        p = _make_project()
        step = Step2_5_PlanFreeze(p)
        assert step.step_id == "step_2_5"


# ═══════════════════════════════════════════════════════════════════
# 6. TestV7StepIdMapping (5 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7StepIdMapping:

    def test_step0_uses_correct_ids(self):
        assert Step0_1_IntakeCard(_make_project()).step_id == "step_0_1"
        assert Step0_2_VenueTaste(_make_project()).step_id == "step_0_2"

    def test_step1_uses_correct_ids(self):
        assert Step1_2_TopicDecision(_make_project()).step_id == "step_1_2"
        assert Step1_3_KillerPriorCheck(_make_project()).step_id == "step_1_3"

    def test_ref_qa_is_step_1_3b(self):
        assert Step1_3b_ReferenceQA(_make_project()).step_id == "step_1_3b"

    def test_valid_step_ids_complete(self):
        expected = {
            "step_s_1",
            "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
            "step_3_init", "step_3_exec",
            "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
        }
        assert VALID_STEP_IDS == expected

    def test_get_next_step_from_bootloader(self):
        # _get_next_step doesn't include step_s_1 in its sequence
        # so step_s_1 returns None (bootloader is handled separately)
        pm = _make_pm()
        assert pm._get_next_step("step_s_1") is None
        assert pm._get_next_step("step_0_1") == "step_0_2"


# ═══════════════════════════════════════════════════════════════════
# 7. TestV7RigorProfile (3 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV7RigorProfile:

    def test_top_journal_thresholds(self):
        assert TOP_JOURNAL_PROFILE.min_literature_count == 25  # v7: 25 (was 30)
        assert TOP_JOURNAL_PROFILE.min_doi_parseability == 0.95  # v7: 95% (was 90%)
        assert TOP_JOURNAL_PROFILE.min_similar_works == 15
        assert TOP_JOURNAL_PROFILE.min_robustness_checks == 6

    def test_fast_track_thresholds(self):
        assert FAST_TRACK_PROFILE.min_literature_count == 15
        assert FAST_TRACK_PROFILE.min_doi_parseability == 0.85  # v7: 85% (was 70%)
        assert FAST_TRACK_PROFILE.min_similar_works == 10
        assert FAST_TRACK_PROFILE.min_robustness_checks == 3

    def test_get_rigor_profile(self):
        top = get_rigor_profile("top_journal")
        assert top.level == RigorLevel.TOP_JOURNAL
        fast = get_rigor_profile("fast_track")
        assert fast.level == RigorLevel.FAST_TRACK


# ═══════════════════════════════════════════════════════════════════
# 8. TestV6ToV7Migration (3 tests)
# ═══════════════════════════════════════════════════════════════════

class TestV6ToV7Migration:

    def test_v6_step_map_exists(self):
        """Test that v6→v7 step ID mapping exists on Project."""
        p = _make_project()
        mapping = p._V6_TO_V7_STEP_MAP
        assert mapping["step_s0"] == "step_0_1"
        assert mapping["step_s0b"] == "step_0_2"
        assert mapping["step_s2"] == "step_1_2"

    def test_v6_current_step_map_exists(self):
        p = _make_project()
        mapping = p._V6_TO_V7_CURRENT_STEP_MAP
        assert mapping["step_s0"] == "step_0_1"
        assert mapping["step_s4_story"] == "step_1_5"

    def test_v6_steps_migrated_on_init(self):
        """Test that v6 step IDs are migrated to v7 on Project init."""
        p = Project(
            project_id="test",
            project_name="Test",
            config=_make_config(),
            current_step="step_s0b",
            steps={
                "step_s0": StepInfo(step_id="step_s0", step_name="Intake", status=StepStatus.COMPLETED),
                "step_s0b": StepInfo(step_id="step_s0b", step_name="Venue", status=StepStatus.PENDING),
            }
        )
        # After migration, step_s0 → step_0_1, step_s0b → step_0_2
        assert "step_0_1" in p.steps
        assert "step_0_2" in p.steps
        assert p.steps["step_0_1"].status == StepStatus.COMPLETED
        assert p.current_step == "step_0_2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

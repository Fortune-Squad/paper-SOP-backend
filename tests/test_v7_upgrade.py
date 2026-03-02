"""
v7 升级自动化测试

验证 v7 规格文档与代码实现的一致性：
- 数据模型（DocumentType, StepInfo, Project, Gate）
- 步骤流转（_get_next_step, _validate_step_prerequisites）
- Gate 系统（Gate 1 含 Topic Alignment, Gate 1.25 deprecated）
- Loop/回退系统
- 搜索三步拆分（S1a, S1b, S1c）
- Step ID 映射
- Rigor Profile
- 迁移脚本

所有测试使用 mock，不调用真实 AI API。
"""
import pytest
import json
import asyncio
import importlib
import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path
from datetime import datetime


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)

# ── Mock heavy dependencies BEFORE importing app modules ──────────
# google.generativeai / openai / chromadb can hang or fail without API keys.
# Force-inject mocks so transitive imports don't block.
_MOCK_MODULES = [
    "google", "google.generativeai", "google.ai", "google.ai.generativelanguage",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "chromadb", "chromadb.config", "chromadb.api",
    "tiktoken", "openai",
]
for _mod in _MOCK_MODULES:
    sys.modules[_mod] = MagicMock()

# Models (safe — no heavy deps)
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

# Services & Steps (depend on ai_client → google.generativeai, now mocked)
from app.services.project_manager import ProjectManager, LOOP_DEFINITIONS
from app.api.projects import VALID_STEP_IDS, VALID_GATE_NAMES

from app.steps.step0 import Step0_1_IntakeCard, Step0_2_VenueTaste
from app.steps.step1 import (
    Step_S1a_SearchPlan, Step_S1b_Hunt, Step_S1c_Synthesis,
    Step1_1b_ReferenceQA, Step1_2_TopicDecision, Step1_3_KillerPriorCheck,
    Step1_4_ClaimsFreeze, Step1_5_FigureFirstStory,
)
from app.steps.step2 import (
    Step2_0_FigureTableList, Step2_1_FullProposal, Step2_2_DataSimSpec,
    Step2_3_EngineeringDecomposition, Step2_4_RedTeamReview,
    Step2_4b_PatchPropagation, Step2_5_PlanFreeze,
)
from app.prompts.step1_prompts import (
    render_step_s1a_search_plan_prompt,
    render_step_s1c_synthesis_prompt,
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
# 1. TestV7DataModels（8 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7DataModels:

    def test_new_document_types_exist(self):
        assert hasattr(DocumentType, "SEARCH_PLAN")
        assert hasattr(DocumentType, "RAW_INTEL_LOG")
        assert hasattr(DocumentType, "LITERATURE_MATRIX_V7")
        assert hasattr(DocumentType, "PATCH_REVIEW")

    def test_gate_1_25_deprecated(self):
        assert hasattr(GateType, "GATE_1_25")
        assert GateType.GATE_1_25.value == "gate_1_25"
        assert "gate_1_25" not in VALID_GATE_NAMES

    def test_gate1_checklist_has_alignment_fields(self):
        cl = Gate1Checklist()
        assert cl.north_star_covered is False
        assert cl.core_keywords_present is False
        assert cl.scope_boundaries_clear is False

    def test_step_info_has_loop_fields(self):
        si = StepInfo(step_id="x", step_name="x")
        assert si.retry_count == 0
        assert si.max_retries == 2

    def test_project_has_loop_history(self):
        p = _make_project()
        assert p.loop_history == []

    def test_project_initializes_18_steps(self):
        p = _make_project()
        assert len(p.steps) == 18

    def test_project_step_ids_match_v7(self):
        p = _make_project()
        expected = {
            "step_s_1", "step_s0", "step_s0b",
            "step_s1a", "step_s1b", "step_s1c",
            "step_s2", "step_s3", "step_s3b", "step_s4",
            "step_s5a", "step_s5b", "step_s5c",
            "step_s6", "step_s6b", "step_s7",
            "step_s4_story", "step_s5_figlist",
        }
        assert set(p.steps.keys()) == expected

    def test_document_type_values_match_spec(self):
        assert DocumentType.SEARCH_PLAN.value == "01_A_Search_Plan"
        assert DocumentType.RAW_INTEL_LOG.value == "01_B_Raw_Intel_Log"
        assert DocumentType.LITERATURE_MATRIX_V7.value == "01_C_Literature_Matrix"
        assert DocumentType.PATCH_REVIEW.value == "03_Patch_Review"


# ═══════════════════════════════════════════════════════════════════
# 2. TestV7StepSequence（8 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7StepSequence:

    def setup_method(self):
        self.pm = _make_pm()

    def test_get_next_step_from_bootloader(self):
        assert self.pm._get_next_step("step_s_1") == "step_s0"

    def test_get_next_step_full_chain(self):
        expected = [
            "step_s_1", "step_s0", "step_s0b",
            "step_s1a", "step_s1b", "step_s1c", "step_s2",
            "step_s3", "step_s3b", "step_s4",
            "step_s5a", "step_s5b", "step_s5c",
            "step_s6", "step_s6b", "step_s7",
        ]
        cur = expected[0]
        visited = [cur]
        while (nxt := self.pm._get_next_step(cur)) is not None:
            visited.append(nxt)
            cur = nxt
        assert visited == expected

    def test_get_next_step_last_returns_none(self):
        assert self.pm._get_next_step("step_s7") is None

    def test_get_next_step_unknown_returns_none(self):
        assert self.pm._get_next_step("step_999") is None

    def test_validate_prerequisites_first_step(self):
        p = _make_project()
        ok, _ = self.pm._validate_step_prerequisites(p, "step_s_1")
        assert ok is True

    def test_validate_prerequisites_blocks_skip(self):
        p = _make_project()
        p.steps["step_s_1"].status = StepStatus.COMPLETED
        ok, msg = self.pm._validate_step_prerequisites(p, "step_s1a")
        assert ok is False

    def test_validate_prerequisites_s5_needs_gate_1_5(self):
        p = _make_project()
        for sid in ["step_s_1", "step_s0", "step_s0b",
                     "step_s1a", "step_s1b", "step_s1c",
                     "step_s2", "step_s3", "step_s3b", "step_s4"]:
            p.steps[sid].status = StepStatus.COMPLETED
        p.gate_1_5_passed = False
        ok, msg = self.pm._validate_step_prerequisites(p, "step_s5a")
        assert ok is False
        assert "Gate 1.5" in msg

    def test_validate_prerequisites_optional_steps(self):
        p = _make_project()
        for sid in ["step_s_1", "step_s0", "step_s0b",
                     "step_s1a", "step_s1b", "step_s1c",
                     "step_s2", "step_s3", "step_s3b", "step_s4"]:
            p.steps[sid].status = StepStatus.COMPLETED
        ok1, _ = self.pm._validate_step_prerequisites(p, "step_s4_story")
        ok2, _ = self.pm._validate_step_prerequisites(p, "step_s5_figlist")
        assert ok1 is True
        assert ok2 is True


# ═══════════════════════════════════════════════════════════════════
# 3. TestV7GateSystem（8 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7GateSystem:

    def test_gate1_includes_topic_alignment(self):
        cl = Gate1Checklist(
            top1_selected=True, backup_defined=True,
            draft_claims_exist=True, non_claims_exist=True, figure_count=3,
            north_star_covered=True, core_keywords_present=True, scope_boundaries_clear=True,
        )
        names = [i.item_name for i in cl.validate().check_items]
        assert "North-Star Question Covered" in names
        assert "Core Keywords Present" in names
        assert "Scope Boundaries Clear" in names

    def test_gate1_pass_requires_all_checks(self):
        cl = Gate1Checklist(
            top1_selected=True, backup_defined=True,
            draft_claims_exist=True, non_claims_exist=True, figure_count=3,
            north_star_covered=True, core_keywords_present=True, scope_boundaries_clear=True,
        )
        r = cl.validate()
        assert r.verdict == GateVerdict.PASS
        assert r.passed_count == r.total_count

    def test_gate1_fail_on_missing_alignment(self):
        cl = Gate1Checklist(
            top1_selected=True, backup_defined=True,
            draft_claims_exist=True, non_claims_exist=True, figure_count=3,
            north_star_covered=False, core_keywords_present=True, scope_boundaries_clear=True,
        )
        assert cl.validate().verdict == GateVerdict.FAIL

    def test_gate_1_25_redirects_to_gate_1(self):
        async def _test():
            pm = _make_pm()
            p = _make_project()
            mock_result = GateResult(
                gate_type=GateType.GATE_1, verdict=GateVerdict.PASS,
                check_items=[], passed_count=8, total_count=8,
                suggestions=[], project_id=p.project_id,
            )
            pm.gate_checker.check_gate_1 = AsyncMock(return_value=mock_result)
            pm._save_project = AsyncMock()
            await pm.check_gate(p, "gate_1_25")
            pm.gate_checker.check_gate_1.assert_awaited_once()
            assert p.gate_1_passed is True
            assert p.gate_1_25_passed is True
        _run(_test())

    def test_auto_gate_trigger_after_s2(self):
        async def _test():
            pm = _make_pm()
            p = _make_project()
            for sid in ["step_s_1", "step_s0", "step_s0b",
                         "step_s1a", "step_s1b", "step_s1c"]:
                p.steps[sid].status = StepStatus.COMPLETED
            p.current_step = "step_s2"
            with patch("app.services.project_manager.Step1_2_TopicDecision") as MockStep:
                MockStep.return_value.execute = AsyncMock(return_value=MagicMock())
                MockStep.return_value.ai_model = "gpt-4o"
                mock_gr = GateResult(
                    gate_type=GateType.GATE_1, verdict=GateVerdict.PASS,
                    check_items=[], passed_count=8, total_count=8,
                    suggestions=[], project_id=p.project_id,
                )
                pm.gate_checker.check_gate_1 = AsyncMock(return_value=mock_gr)
                pm._save_project = AsyncMock()
                await pm.execute_step(p, "step_s2")
                pm.gate_checker.check_gate_1.assert_awaited_once()
        _run(_test())

    def test_auto_gate_trigger_after_s3b(self):
        async def _test():
            pm = _make_pm()
            p = _make_project()
            for sid in ["step_s_1", "step_s0", "step_s0b",
                         "step_s1a", "step_s1b", "step_s1c", "step_s2", "step_s3"]:
                p.steps[sid].status = StepStatus.COMPLETED
            p.current_step = "step_s3b"
            with patch("app.services.project_manager.Step1_1b_ReferenceQA") as MockStep:
                MockStep.return_value.execute = AsyncMock(return_value=MagicMock())
                MockStep.return_value.ai_model = "gemini-2.0-flash"
                mock_gr = GateResult(
                    gate_type=GateType.GATE_1_6, verdict=GateVerdict.PASS,
                    check_items=[], passed_count=5, total_count=5,
                    suggestions=[], project_id=p.project_id,
                )
                pm.gate_checker.check_gate_1_6 = AsyncMock(return_value=mock_gr)
                pm._save_project = AsyncMock()
                await pm.execute_step(p, "step_s3b")
                pm.gate_checker.check_gate_1_6.assert_awaited_once()
        _run(_test())

    def test_clear_related_gates_v7(self):
        pm = _make_pm()
        p = _make_project()
        p.gate_1_passed = True
        p.gate_results["gate_1"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_s2")
        assert p.gate_1_passed is False
        assert "gate_1" not in p.gate_results

        p.gate_1_6_passed = True
        p.gate_results["gate_1_6"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_s3b")
        assert p.gate_1_6_passed is False
        assert "gate_1_6" not in p.gate_results

    def test_valid_gate_names_no_1_25(self):
        assert VALID_GATE_NAMES == {"gate_0", "gate_1", "gate_1_5", "gate_1_6", "gate_2"}


# ═══════════════════════════════════════════════════════════════════
# 4. TestV7LoopSystem（7 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7LoopSystem:

    def test_loop_definitions_match_spec(self):
        assert len(LOOP_DEFINITIONS) == 5
        assert LOOP_DEFINITIONS["loop_a"]["trigger_gate"] == "gate_1"
        assert LOOP_DEFINITIONS["loop_a"]["target_step"] == "step_s1a"
        assert LOOP_DEFINITIONS["loop_b"]["trigger_gate"] == "gate_1_5"
        assert LOOP_DEFINITIONS["loop_b"]["target_step"] == "step_s2"
        assert LOOP_DEFINITIONS["loop_c"]["trigger_gate"] == "gate_1_6"
        assert LOOP_DEFINITIONS["loop_c"]["target_step"] == "step_s1b"
        assert LOOP_DEFINITIONS["loop_d"]["trigger_gate"] == "gate_2"
        assert LOOP_DEFINITIONS["loop_d"]["target_step"] == "step_s5a"
        assert LOOP_DEFINITIONS["loop_e"]["trigger_gate"] is None
        assert LOOP_DEFINITIONS["loop_e"]["target_step"] == "step_s5a"

    def test_loop_a_gate1_fail_rollback(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_s0", "step_s0b",
                         "step_s1a", "step_s1b", "step_s1c", "step_s2"]:
                p.steps[sid].status = StepStatus.COMPLETED
            result = await pm.handle_gate_failure(p, "gate_1", MagicMock())
            assert result["action"] == "rollback"
            assert result["target_step"] == "step_s1a"
            assert result["loop_id"] == "loop_a"
        _run(_test())

    def test_loop_b_gate1_5_fail_rollback(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_s0", "step_s0b",
                         "step_s1a", "step_s1b", "step_s1c", "step_s2", "step_s3"]:
                p.steps[sid].status = StepStatus.COMPLETED
            result = await pm.handle_gate_failure(p, "gate_1_5", MagicMock())
            assert result["action"] == "rollback"
            assert result["target_step"] == "step_s2"
            assert result["loop_id"] == "loop_b"
        _run(_test())

    def test_loop_max_retries_creates_hil(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            p.loop_history = [
                {"loop_id": "loop_a", "action": "rollback"},
                {"loop_id": "loop_a", "action": "rollback"},
            ]
            result = await pm.handle_gate_failure(p, "gate_1", MagicMock())
            assert result["action"] == "hil_required"
        _run(_test())

    def test_loop_rollback_resets_steps(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_s0", "step_s0b",
                         "step_s1a", "step_s1b", "step_s1c", "step_s2"]:
                p.steps[sid].status = StepStatus.COMPLETED
            await pm.handle_gate_failure(p, "gate_1", MagicMock())
            assert p.steps["step_s1a"].status == StepStatus.PENDING
            assert p.steps["step_s1b"].status == StepStatus.PENDING
            assert p.steps["step_s2"].status == StepStatus.PENDING
            assert p.steps["step_s0b"].status == StepStatus.COMPLETED
        _run(_test())

    def test_loop_history_recorded(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            for sid in ["step_s_1", "step_s0", "step_s0b",
                         "step_s1a", "step_s1b", "step_s1c", "step_s2"]:
                p.steps[sid].status = StepStatus.COMPLETED
            assert len(p.loop_history) == 0
            await pm.handle_gate_failure(p, "gate_1", MagicMock())
            assert len(p.loop_history) == 1
            assert p.loop_history[0]["loop_id"] == "loop_a"
            assert p.loop_history[0]["action"] == "rollback"
        _run(_test())

    def test_no_loop_for_unknown_gate(self):
        async def _test():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            result = await pm.handle_gate_failure(p, "gate_0", MagicMock())
            assert result["action"] == "manual"
        _run(_test())


# ═══════════════════════════════════════════════════════════════════
# 5. TestV7SearchThreeStep（5 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7SearchThreeStep:

    def test_s1a_step_properties(self):
        p = _make_project()
        step = Step_S1a_SearchPlan(p)
        assert step.step_id == "step_s1a"
        assert step.output_doc_type == DocumentType.SEARCH_PLAN

    def test_s1b_step_properties(self):
        p = _make_project()
        step = Step_S1b_Hunt(p)
        assert step.step_id == "step_s1b"
        assert step.output_doc_type == DocumentType.RAW_INTEL_LOG

    def test_s1c_step_properties(self):
        p = _make_project()
        step = Step_S1c_Synthesis(p)
        assert step.step_id == "step_s1c"
        assert step.output_doc_type == DocumentType.LITERATURE_MATRIX_V7

    def test_s1a_prompt_renders(self):
        result = render_step_s1a_search_plan_prompt(
            topic="Test", target_venue="NeurIPS",
            research_type="ML", intake_card_content="content",
        )
        assert isinstance(result, str)
        assert len(result) > 50

    def test_s1c_prompt_renders(self):
        result = render_step_s1c_synthesis_prompt(
            raw_intel_content="raw intel", intake_card_content="intake",
        )
        assert isinstance(result, str)
        assert len(result) > 50


# ═══════════════════════════════════════════════════════════════════
# 6. TestV7StepIdMapping（5 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7StepIdMapping:

    def test_step0_uses_v7_ids(self):
        assert Step0_1_IntakeCard(_make_project()).step_id == "step_s0"

    def test_step2_uses_v7_ids(self):
        assert Step2_1_FullProposal(_make_project()).step_id == "step_s5a"

    def test_ref_qa_moved_to_s3b(self):
        assert Step1_1b_ReferenceQA(_make_project()).step_id == "step_s3b"

    def test_valid_step_ids_complete(self):
        expected = {
            "step_s_1", "step_s0", "step_s0b",
            "step_s1a", "step_s1b", "step_s1c",
            "step_s2", "step_s3", "step_s3b", "step_s4",
            "step_s4_story", "step_s5_figlist",
            "step_s5a", "step_s5b", "step_s5c",
            "step_s6", "step_s6b", "step_s7",
        }
        assert VALID_STEP_IDS == expected

    def test_bootloader_confirm_uses_step_s0(self):
        assert _make_pm()._get_next_step("step_s_1") == "step_s0"


# ═══════════════════════════════════════════════════════════════════
# 7. TestV7RigorProfile（3 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7RigorProfile:

    def test_top_journal_thresholds(self):
        assert TOP_JOURNAL_PROFILE.min_literature_count == 25
        assert TOP_JOURNAL_PROFILE.min_doi_parseability == 0.95
        assert TOP_JOURNAL_PROFILE.min_similar_works_kp == 15

    def test_fast_track_thresholds(self):
        assert FAST_TRACK_PROFILE.min_literature_count == 15
        assert FAST_TRACK_PROFILE.min_doi_parseability == 0.85
        assert FAST_TRACK_PROFILE.min_similar_works_kp == 10

    def test_profiles_no_gate_1_25(self):
        assert "gate_1_25" not in TOP_JOURNAL_PROFILE.gate_thresholds
        assert "gate_1_25" not in FAST_TRACK_PROFILE.gate_thresholds


# ═══════════════════════════════════════════════════════════════════
# 8. TestV7MigrationScript（2 tests）
# ═══════════════════════════════════════════════════════════════════

class TestV7MigrationScript:

    def _load_migration_module(self):
        script_path = Path(__file__).parent.parent / "scripts" / "migrate_v4_to_v7.py"
        spec = importlib.util.spec_from_file_location("migrate_v4_to_v7", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_step_migration_mapping(self):
        mod = self._load_migration_module()
        expected_old_ids = {
            "step_0_1", "step_0_2",
            "step_1_1", "step_1_1b", "step_1_2", "step_1_2b",
            "step_1_3", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3",
            "step_2_4", "step_2_4b", "step_2_5",
        }
        assert set(mod.STEP_MIGRATION.keys()) == expected_old_ids

    def test_migrate_project_json(self, tmp_path):
        mod = self._load_migration_module()
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        old_data = {
            "project_id": "test",
            "current_step": "step_1_2",
            "steps": {
                "step_s_1": {"step_id": "step_s_1", "step_name": "Bootloader", "status": "completed"},
                "step_0_1": {"step_id": "step_0_1", "step_name": "Intake", "status": "completed"},
                "step_0_2": {"step_id": "step_0_2", "step_name": "Venue", "status": "completed"},
                "step_1_1": {"step_id": "step_1_1", "step_name": "Deep Research", "status": "completed"},
                "step_1_2": {"step_id": "step_1_2", "step_name": "Topic", "status": "pending"},
            },
            "gate_results": {},
        }
        (project_dir / "project.json").write_text(json.dumps(old_data), encoding="utf-8")
        result = mod.migrate_project(project_dir, dry_run=False)
        assert result["status"] == "migrated"
        migrated = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
        assert "step_s0" in migrated["steps"]
        assert "step_s0b" in migrated["steps"]
        assert "step_s1b" in migrated["steps"]
        assert "step_s2" in migrated["steps"]
        assert migrated["current_step"] == "step_s2"
        assert "step_s1a" in migrated["steps"]
        assert "step_s1c" in migrated["steps"]
        assert migrated.get("loop_history") == []

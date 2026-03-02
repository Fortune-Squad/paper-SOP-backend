"""
Unit tests for ProjectManager service.
Tests project creation, step prerequisites, gate clearing, and step execution.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from app.services.project_manager import ProjectManager
from app.models.project import Project, ProjectConfig, StepInfo, StepStatus, ResearchType, DataStatus
from app.models.gate import GateResult, GateType, GateVerdict


def _make_config():
    return ProjectConfig(
        topic="Test ML Project",
        target_venue="NeurIPS 2026",
        research_type=ResearchType.ML,
        data_status=DataStatus.AVAILABLE,
        hard_constraints=["Must use PyTorch", "Must be reproducible"],
        keywords=["machine learning", "deep learning", "neural networks"],
    )


def _make_project(**overrides):
    defaults = dict(project_id="test_project", project_name="Test Project", config=_make_config())
    defaults.update(overrides)
    return Project(**defaults)


def _make_pm():
    return ProjectManager(
        file_manager=MagicMock(), git_manager=MagicMock(),
        vector_store=MagicMock(), gate_checker=MagicMock(),
    )


def _complete_bootloader(project):
    project.steps["step_s_1"].status = StepStatus.COMPLETED


def _complete_steps(project, step_ids):
    for sid in step_ids:
        project.steps[sid].status = StepStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════
# 1. TestProjectCreation (3 tests)
# ═══════════════════════════════════════════════════════════════════

def _mock_clarity_score():
    """Create a mock ClarityScore that passes isinstance checks."""
    from unittest.mock import PropertyMock
    score = MagicMock()
    score.overall_score = 85.0
    score.recommendation = "skip_bootloader"
    score.model_dump.return_value = {
        "overall_score": 85.0, "recommendation": "skip_bootloader",
        "topic_score": 80.0, "context_score": 30.0, "constraint_score": 96.0,
    }
    return score


class TestProjectCreation:
    """Test suite for project creation."""

    def test_create_project(self):
        """Test creating a new project with valid configuration."""
        async def _run():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            config = _make_config()
            with patch('app.services.clarity_analyzer.get_clarity_analyzer') as mock_ca:
                mock_ca.return_value.analyze_input_clarity = AsyncMock(return_value=_mock_clarity_score())
                project = await pm.create_project(config)
            assert project is not None
            assert project.config.topic == config.topic
            assert project.config.target_venue == config.target_venue
            assert len(project.steps) == 26  # v7 + v1.2 step_4_repro = 26 steps
        asyncio.run(_run())

    def test_create_project_initializes_all_steps(self):
        """Test that project creation initializes all 25 steps correctly."""
        async def _run():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            config = _make_config()
            with patch('app.services.clarity_analyzer.get_clarity_analyzer') as mock_ca:
                mock_ca.return_value.analyze_input_clarity = AsyncMock(return_value=_mock_clarity_score())
                project = await pm.create_project(config)
            expected_step_ids = {
                "step_s_1",
                "step_0_1", "step_0_2",
                "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
                "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
                "step_3_init", "step_3_exec",
                "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
            }
            assert set(project.steps.keys()) == expected_step_ids
        asyncio.run(_run())

    def test_create_project_initializes_gates(self):
        """Test that project creation initializes all 6 gates as not passed."""
        async def _run():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            config = _make_config()
            with patch('app.services.clarity_analyzer.get_clarity_analyzer') as mock_ca:
                mock_ca.return_value.analyze_input_clarity = AsyncMock(return_value=_mock_clarity_score())
                project = await pm.create_project(config)
            assert project.gate_0_passed is False
            assert project.gate_1_passed is False
            assert project.gate_1_25_passed is True  # v7.0: deprecated, defaults to True
            assert project.gate_1_5_passed is False
            assert project.gate_1_6_passed is False
            assert project.gate_2_passed is False
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════
# 2. TestStepPrerequisites (5 tests)
# ═══════════════════════════════════════════════════════════════════

class TestStepPrerequisites:
    """Test suite for step prerequisite validation."""

    def test_validate_first_step(self):
        """step_s_1 (bootloader) has no prerequisites."""
        pm = _make_pm()
        p = _make_project()
        ok, msg = pm._validate_step_prerequisites(p, "step_s_1")
        assert ok is True

    def test_validate_sequential_steps_blocked(self):
        """step_0_2 requires step_0_1 to be completed."""
        pm = _make_pm()
        p = _make_project()
        _complete_bootloader(p)
        ok, msg = pm._validate_step_prerequisites(p, "step_0_2")
        assert ok is False

    def test_validate_sequential_steps_allowed(self):
        """step_0_2 proceeds when step_0_1 is completed."""
        pm = _make_pm()
        p = _make_project()
        _complete_steps(p, ["step_s_1", "step_0_1"])
        ok, msg = pm._validate_step_prerequisites(p, "step_0_2")
        assert ok is True

    def test_gate_1_5_blocks_step_2(self):
        """Gate 1.5 must pass before entering Step 2."""
        pm = _make_pm()
        p = _make_project()
        _complete_steps(p, [
            "step_s_1", "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2",
            "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
        ])
        p.gate_1_5_passed = False
        ok, msg = pm._validate_step_prerequisites(p, "step_2_0")
        assert ok is False
        assert "Gate 1.5" in msg

    def test_gate_1_5_allows_step_2(self):
        """Step 2 can proceed when Gate 1.5 passes."""
        pm = _make_pm()
        p = _make_project()
        _complete_steps(p, [
            "step_s_1", "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2",
            "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
        ])
        p.gate_1_5_passed = True
        ok, msg = pm._validate_step_prerequisites(p, "step_2_0")
        assert ok is True


# ═══════════════════════════════════════════════════════════════════
# 3. TestGateClearing (3 tests)
# ═══════════════════════════════════════════════════════════════════

class TestGateClearing:
    """Test suite for gate clearing on step re-execution."""

    def test_clear_related_gates_step_0_2(self):
        """Re-executing step_0_2 clears Gate 0."""
        pm = _make_pm()
        p = _make_project()
        p.gate_0_passed = True
        p.gate_results["gate_0"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_0_2")
        assert p.gate_0_passed is False
        assert "gate_0" not in p.gate_results

    def test_clear_related_gates_step_1_3(self):
        """Re-executing step_1_3 clears Gate 1.5."""
        pm = _make_pm()
        p = _make_project()
        p.gate_1_5_passed = True
        p.gate_results["gate_1_5"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_1_3")
        assert p.gate_1_5_passed is False

    def test_clear_related_gates_step_2_4b(self):
        """Re-executing step_2_4b clears Gate 2."""
        pm = _make_pm()
        p = _make_project()
        p.gate_2_passed = True
        p.gate_results["gate_2"] = {"verdict": "PASS"}
        pm._clear_related_gates(p, "step_2_4b")
        assert p.gate_2_passed is False

    def test_clear_unrelated_step_no_effect(self):
        """Re-executing step_0_1 (not in mapping) clears nothing."""
        pm = _make_pm()
        p = _make_project()
        p.gate_0_passed = True
        pm._clear_related_gates(p, "step_0_1")
        assert p.gate_0_passed is True


# ═══════════════════════════════════════════════════════════════════
# 4. TestGetNextStep (3 tests)
# ═══════════════════════════════════════════════════════════════════

class TestGetNextStep:
    """Test suite for _get_next_step."""

    def test_get_next_step_at_start(self):
        pm = _make_pm()
        assert pm._get_next_step("step_0_1") == "step_0_2"

    def test_get_next_step_chain(self):
        pm = _make_pm()
        assert pm._get_next_step("step_0_2") == "step_1_1a"
        assert pm._get_next_step("step_1_5") == "step_2_0"

    def test_get_next_step_last_returns_none(self):
        pm = _make_pm()
        assert pm._get_next_step("step_4_package") is None


# ═══════════════════════════════════════════════════════════════════
# 5. TestExecuteStepValidation (2 tests)
# ═══════════════════════════════════════════════════════════════════

_PM = "app.services.project_manager"


def _mock_step_class():
    mock_cls = MagicMock()
    mock_instance = AsyncMock()
    mock_instance.execute = AsyncMock(return_value=MagicMock())
    mock_instance.ai_model = "test-model"
    mock_cls.return_value = mock_instance
    return mock_cls


class TestExecuteStepValidation:
    """Test suite for step execution validation."""

    def test_execute_step_fails_prerequisite(self):
        """Step execution fails when prerequisites are not met."""
        async def _run():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            _complete_bootloader(p)
            # step_0_2 requires step_0_1 completed
            with pytest.raises(ValueError):
                await pm.execute_step(p, "step_0_2")
        asyncio.run(_run())

    def test_execute_step_clears_gates_on_retry(self):
        """Re-executing a completed-with-error step clears related gates."""
        async def _run():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            _complete_steps(p, ["step_s_1", "step_0_1"])
            # Mark step_0_2 as completed with error (triggers re-execution path)
            p.steps["step_0_2"].status = StepStatus.COMPLETED
            p.steps["step_0_2"].error_message = "previous error"
            p.gate_0_passed = True
            p.gate_results["gate_0"] = {"verdict": "PASS"}
            with patch(f'{_PM}.Step0_2_VenueTaste', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):
                await pm.execute_step(p, "step_0_2")
            assert p.gate_0_passed is False
        asyncio.run(_run())


# ═══════════════════════════════════════════════════════════════════
# 6. TestAutoGateChecking (1 test)
# ═══════════════════════════════════════════════════════════════════

class TestAutoGateChecking:
    """Test suite for automatic gate checking after specific steps."""

    def test_auto_gate_check_after_step_1_3b(self):
        """Gate 1.6 is automatically checked after step_1_3b."""
        async def _run():
            pm = _make_pm()
            pm._save_project = AsyncMock()
            p = _make_project()
            _complete_steps(p, [
                "step_s_1", "step_0_1", "step_0_2",
                "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3",
            ])
            mock_gr = GateResult(
                gate_type=GateType.GATE_1_6, verdict=GateVerdict.PASS,
                check_items=[], passed_count=5, total_count=5,
                suggestions=[], project_id=p.project_id,
            )
            pm.gate_checker.check_gate_1_6 = AsyncMock(return_value=mock_gr)
            with patch(f'{_PM}.Step1_3b_ReferenceQA', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):
                await pm.execute_step(p, "step_1_3b")
            pm.gate_checker.check_gate_1_6.assert_awaited_once()
        asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

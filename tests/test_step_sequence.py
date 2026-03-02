"""
Integration tests for step sequencing and transitions.
Tests the flow between steps, gate enforcement, and step re-execution behavior.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.project_manager import ProjectManager
from app.models.project import Project, ProjectConfig, StepStatus
from app.models.gate import GateResult, GateType


@pytest.fixture
def project_manager():
    """Create a ProjectManager instance for testing."""
    pm = ProjectManager()
    pm._save_project = AsyncMock()  # Prevent filesystem writes
    return pm


@pytest.fixture
def sample_config():
    """Create a sample project configuration."""
    return ProjectConfig(
        topic="Test ML Project",
        target_venue="NeurIPS 2026",
        research_type="ml",
        data_status="available",
        hard_constraints=["Must use PyTorch"],
        keywords=["machine learning", "deep learning"]
    )


@pytest.fixture
def mock_project(sample_config):
    """Create a mock project with some completed steps."""
    return Project(project_id="test_project", project_name="Test Project", config=sample_config)


def _complete_bootloader(project):
    """Helper: mark step_s_1 as completed."""
    project.steps["step_s_1"].status = StepStatus.COMPLETED


def _complete_step0(project):
    """Helper: mark bootloader + Step 0 as completed."""
    _complete_bootloader(project)
    for sid in ["step_0_1", "step_0_2"]:
        project.steps[sid].status = StepStatus.COMPLETED


def _complete_step1(project):
    """Helper: mark all through Step 1 as completed."""
    _complete_step0(project)
    for sid in ["step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5"]:
        project.steps[sid].status = StepStatus.COMPLETED


def _complete_step2(project):
    """Helper: mark all through Step 2 as completed."""
    _complete_step1(project)
    project.gate_1_5_passed = True
    for sid in ["step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5"]:
        project.steps[sid].status = StepStatus.COMPLETED


def _mock_step_class():
    """Create a mock step class whose instances have an async execute()."""
    mock_cls = MagicMock()
    mock_instance = AsyncMock()
    mock_instance.execute = AsyncMock()
    mock_instance.ai_model = "test-model"
    mock_cls.return_value = mock_instance
    return mock_cls


# Patch targets matching actual imports in project_manager.py
_PM = "app.services.project_manager"


class TestStep0ToStep1Transition:
    """Test suite for transitions from Step 0 to Step 1."""

    def test_step_0_to_step_1_transition(self, project_manager, mock_project):
        """Test smooth transition from Step 0 to Step 1."""
        async def _run():
            _complete_bootloader(mock_project)

            with patch(f'{_PM}.Step0_1_IntakeCard', _mock_step_class()), \
                 patch(f'{_PM}.Step0_2_VenueTaste', _mock_step_class()), \
                 patch(f'{_PM}.Step1_1a_SearchPlan', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                await project_manager.execute_step(mock_project, "step_0_1")
                await project_manager.execute_step(mock_project, "step_0_2")

                assert mock_project.steps["step_0_1"].status == StepStatus.COMPLETED
                assert mock_project.steps["step_0_2"].status == StepStatus.COMPLETED

                await project_manager.execute_step(mock_project, "step_1_1a")
                assert mock_project.steps["step_1_1a"].status == StepStatus.COMPLETED
        asyncio.run(_run())

    def test_step_1_cannot_start_without_step_0(self, project_manager, mock_project):
        """Test that Step 1 cannot start without completing Step 0."""
        async def _run():
            _complete_bootloader(mock_project)

            with pytest.raises(ValueError) as exc_info:
                await project_manager.execute_step(mock_project, "step_1_1a")

            assert "前置步骤" in str(exc_info.value) or "prerequisite" in str(exc_info.value).lower()
        asyncio.run(_run())


class TestGate15BlocksStep2:
    """Test suite for Gate 1.5 enforcement before Step 2."""

    def test_gate_1_5_blocks_step_2(self, project_manager, mock_project):
        """Test that Gate 1.5 must pass before Step 2 can begin."""
        async def _run():
            _complete_step1(mock_project)
            mock_project.gate_1_5_passed = False

            with pytest.raises(ValueError) as exc_info:
                await project_manager.execute_step(mock_project, "step_2_0")

            error_msg = str(exc_info.value).lower()
            assert "gate" in error_msg and "1.5" in error_msg
        asyncio.run(_run())

    def test_gate_1_5_allows_step_2_when_passed(self, project_manager, mock_project):
        """Test that Step 2 can proceed when Gate 1.5 passes."""
        async def _run():
            _complete_step1(mock_project)
            mock_project.gate_1_5_passed = True

            with patch(f'{_PM}.Step2_0_FigureTableList', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                await project_manager.execute_step(mock_project, "step_2_0")
                assert mock_project.steps["step_2_0"].status == StepStatus.COMPLETED
        asyncio.run(_run())

    def test_gate_1_5_is_mandatory(self, project_manager, mock_project):
        """Test that Gate 1.5 is enforced as mandatory checkpoint."""
        _complete_step1(mock_project)

        mock_project.gate_1_5_passed = False
        assert mock_project.can_proceed_to_step_2() == False

        mock_project.gate_1_5_passed = True
        assert mock_project.can_proceed_to_step_2() == True


class TestStepReExecutionClearsGates:
    """Test suite for gate clearing when re-executing steps."""

    def test_step_1_3_re_execution_clears_gate_1_5(self, project_manager, mock_project):
        """Test that re-executing step_1_3 clears Gate 1.5."""
        async def _run():
            _complete_bootloader(mock_project)
            for sid in ["step_0_1", "step_0_2", "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2"]:
                mock_project.steps[sid].status = StepStatus.COMPLETED
            mock_project.steps["step_1_3"].status = StepStatus.COMPLETED
            mock_project.gate_1_5_passed = True

            with patch(f'{_PM}.Step1_3_KillerPriorCheck', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                # Force re-execution by setting error_message
                mock_project.steps["step_1_3"].error_message = "previous error"
                await project_manager.execute_step(mock_project, "step_1_3")

                assert mock_project.gate_1_5_passed == False
        asyncio.run(_run())

    def test_step_1_3b_re_execution_clears_gate_1_6(self, project_manager, mock_project):
        """Test that re-executing step_1_3b clears Gate 1.6."""
        async def _run():
            _complete_bootloader(mock_project)
            for sid in ["step_0_1", "step_0_2", "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3"]:
                mock_project.steps[sid].status = StepStatus.COMPLETED
            mock_project.steps["step_1_3b"].status = StepStatus.COMPLETED
            mock_project.gate_1_6_passed = True

            with patch(f'{_PM}.Step1_3b_ReferenceQA', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                mock_project.steps["step_1_3b"].error_message = "previous error"
                await project_manager.execute_step(mock_project, "step_1_3b")

                assert mock_project.gate_1_6_passed == False
        asyncio.run(_run())

    def test_step_2_4b_re_execution_clears_gate_2_only(self, project_manager, mock_project):
        """Test that re-executing step_2_4b clears only Gate 2."""
        async def _run():
            _complete_step2(mock_project)
            mock_project.gate_0_passed = True
            mock_project.gate_1_passed = True
            mock_project.gate_1_6_passed = True
            mock_project.gate_2_passed = True

            with patch(f'{_PM}.Step2_4b_PatchPropagation', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                mock_project.steps["step_2_4b"].error_message = "previous error"
                await project_manager.execute_step(mock_project, "step_2_4b")

                assert mock_project.gate_2_passed == False
                assert mock_project.gate_0_passed == True
                assert mock_project.gate_1_5_passed == True
        asyncio.run(_run())

# PLACEHOLDER_REST

class TestAutoGateCheckAfterSteps:
    """Test suite for automatic gate checking after specific steps."""

    def test_auto_gate_check_after_step_1_3b(self, project_manager, mock_project):
        """Test that Gate 1.6 is automatically checked after step_1_3b but requires human approval."""
        async def _run():
            _complete_bootloader(mock_project)
            for sid in ["step_0_1", "step_0_2", "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3"]:
                mock_project.steps[sid].status = StepStatus.COMPLETED

            mock_gate_result = GateResult(
                gate_type=GateType.GATE_1_6,
                verdict="PASS",
                check_items=[],
                passed_count=0,
                total_count=0,
                suggestions=[],
                project_id="test_project",
            )

            mock_gc = AsyncMock()
            mock_gc.check_gate_1_6 = AsyncMock(return_value=mock_gate_result)
            project_manager.gate_checker = mock_gc

            with patch(f'{_PM}.Step1_3b_ReferenceQA', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                await project_manager.execute_step(mock_project, "step_1_3b")

                mock_gc.check_gate_1_6.assert_called_once()
                # Gate 1.6 requires human approval — auto-check does NOT set passed
                assert mock_project.gate_1_6_passed == False
                assert mock_project.gate_results["gate_1_6"]["requires_human_approval"] == True
        asyncio.run(_run())

    def test_auto_gate_check_after_step_1_2(self, project_manager, mock_project):
        """Test that Gate 1 is automatically checked after step_1_2 (v7.0: alignment merged into Gate 1)."""
        async def _run():
            _complete_bootloader(mock_project)
            for sid in ["step_0_1", "step_0_2", "step_1_1a", "step_1_1b", "step_1_1c"]:
                mock_project.steps[sid].status = StepStatus.COMPLETED

            mock_gate_result = GateResult(
                gate_type=GateType.GATE_1,
                verdict="PASS",
                check_items=[],
                passed_count=0,
                total_count=0,
                suggestions=[],
                project_id="test_project",
            )

            mock_gc = AsyncMock()
            mock_gc.check_gate_1 = AsyncMock(return_value=mock_gate_result)
            project_manager.gate_checker = mock_gc

            with patch(f'{_PM}.Step1_2_TopicDecision', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                await project_manager.execute_step(mock_project, "step_1_2")

                mock_gc.check_gate_1.assert_called_once()
                # v7 SOP 3.4: Gate 1 requires human approval, auto-check does NOT set passed
                assert mock_project.gate_1_passed == False
                assert mock_project.gate_results["gate_1"]["requires_human_approval"] == True
        asyncio.run(_run())

    def test_auto_gate_check_failure_updates_status(self, project_manager, mock_project):
        """Test that failed auto gate check updates project status correctly."""
        async def _run():
            _complete_bootloader(mock_project)
            for sid in ["step_0_1", "step_0_2", "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3"]:
                mock_project.steps[sid].status = StepStatus.COMPLETED

            mock_gate_result = GateResult(
                gate_type=GateType.GATE_1_6,
                verdict="FAIL",
                check_items=[],
                passed_count=0,
                total_count=0,
                suggestions=["Fix DOI validation issues"],
                project_id="test_project",
            )

            mock_gc = AsyncMock()
            mock_gc.check_gate_1_6 = AsyncMock(return_value=mock_gate_result)
            project_manager.gate_checker = mock_gc

            with patch(f'{_PM}.Step1_3b_ReferenceQA', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                await project_manager.execute_step(mock_project, "step_1_3b")

                assert mock_project.gate_1_6_passed == False
        asyncio.run(_run())


class TestCompleteStepSequence:
    """Test suite for complete step sequence execution."""

    def test_complete_step_0_sequence(self, project_manager, mock_project):
        """Test executing all Step 0 steps in sequence."""
        async def _run():
            _complete_bootloader(mock_project)

            with patch(f'{_PM}.Step0_1_IntakeCard', _mock_step_class()), \
                 patch(f'{_PM}.Step0_2_VenueTaste', _mock_step_class()), \
                 patch('asyncio.sleep', new_callable=AsyncMock):

                await project_manager.execute_step(mock_project, "step_0_1")
                await project_manager.execute_step(mock_project, "step_0_2")

                for sid in ["step_0_1", "step_0_2"]:
                    assert mock_project.steps[sid].status == StepStatus.COMPLETED
        asyncio.run(_run())

    def test_step_execution_order_enforced(self, project_manager, mock_project):
        """Test that steps must be executed in order."""
        async def _run():
            # Try to execute steps out of order (bootloader not done)
            with pytest.raises(ValueError):
                await project_manager.execute_step(mock_project, "step_1_5")

            with pytest.raises(ValueError):
                await project_manager.execute_step(mock_project, "step_2_5")
        asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

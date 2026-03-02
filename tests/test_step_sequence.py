"""
Integration tests for step sequencing and transitions.
Tests the flow between steps, gate enforcement, and step re-execution behavior.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.project_manager import ProjectManager
from app.models.project import Project, ProjectConfig, StepStatus
from app.models.gate import GateResult


@pytest.fixture
def project_manager():
    """Create a ProjectManager instance for testing."""
    return ProjectManager()


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
    project = Project(project_id="test_project", config=sample_config)
    return project


class TestStep0ToStep1Transition:
    """Test suite for transitions from Step 0 to Step 1."""

    @pytest.mark.asyncio
    async def test_step_0_to_step_1_transition(self, project_manager, mock_project):
        """Test smooth transition from Step 0 to Step 1."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step01') as mock_step01, \
             patch('app.services.project_manager.Step02') as mock_step02, \
             patch('app.services.project_manager.Step11') as mock_step11:

            # Mock step execution
            for mock_step in [mock_step01, mock_step02, mock_step11]:
                mock_instance = AsyncMock()
                mock_instance.execute = AsyncMock()
                mock_step.return_value = mock_instance

            # Execute Step 0 steps
            await project_manager.execute_step(mock_project, "step_0_1")
            await project_manager.execute_step(mock_project, "step_0_2")

            # Verify both Step 0 steps are completed
            step_0_1 = next(s for s in mock_project.steps if s.step_id == "step_0_1")
            step_0_2 = next(s for s in mock_project.steps if s.step_id == "step_0_2")
            assert step_0_1.status == StepStatus.COMPLETED
            assert step_0_2.status == StepStatus.COMPLETED

            # Should be able to execute Step 1.1
            await project_manager.execute_step(mock_project, "step_1_1")
            step_1_1 = next(s for s in mock_project.steps if s.step_id == "step_1_1")
            assert step_1_1.status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_step_1_cannot_start_without_step_0(self, project_manager, mock_project):
        """Test that Step 1 cannot start without completing Step 0."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'):

            # Try to execute step_1_1 without completing Step 0
            with pytest.raises(ValueError) as exc_info:
                await project_manager.execute_step(mock_project, "step_1_1")

            assert "前置步骤未完成" in str(exc_info.value) or "prerequisite" in str(exc_info.value).lower()


class TestGate15BlocksStep2:
    """Test suite for Gate 1.5 enforcement before Step 2."""

    @pytest.mark.asyncio
    async def test_gate_1_5_blocks_step_2(self, project_manager, mock_project):
        """Test that Gate 1.5 must pass before Step 2 can begin."""
        # Complete all Step 0 and Step 1 steps
        for step in mock_project.steps:
            if step.step_id.startswith("step_0_") or step.step_id.startswith("step_1_"):
                step.status = StepStatus.COMPLETED

        # Ensure Gate 1.5 is not passed
        mock_project.gate_1_5_passed = False

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'):

            # Try to execute step_2_0 without Gate 1.5 passing
            with pytest.raises(ValueError) as exc_info:
                await project_manager.execute_step(mock_project, "step_2_0")

            error_msg = str(exc_info.value).lower()
            assert "gate" in error_msg and "1" in error_msg and "5" in error_msg

    @pytest.mark.asyncio
    async def test_gate_1_5_allows_step_2_when_passed(self, project_manager, mock_project):
        """Test that Step 2 can proceed when Gate 1.5 passes."""
        # Complete all Step 0 and Step 1 steps
        for step in mock_project.steps:
            if step.step_id.startswith("step_0_") or step.step_id.startswith("step_1_"):
                step.status = StepStatus.COMPLETED

        # Mark Gate 1.5 as passed
        mock_project.gate_1_5_passed = True

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step20') as mock_step20:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step20.return_value = mock_instance

            # Should be able to execute step_2_0
            await project_manager.execute_step(mock_project, "step_2_0")

            step_2_0 = next(s for s in mock_project.steps if s.step_id == "step_2_0")
            assert step_2_0.status == StepStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_gate_1_5_is_mandatory(self, project_manager, mock_project):
        """Test that Gate 1.5 is enforced as mandatory checkpoint."""
        # Complete Step 0 and Step 1
        for step in mock_project.steps:
            if step.step_id.startswith("step_0_") or step.step_id.startswith("step_1_"):
                step.status = StepStatus.COMPLETED

        # Gate 1.5 not passed
        mock_project.gate_1_5_passed = False

        # Verify can_proceed_to_step_2 returns False
        can_proceed = mock_project.can_proceed_to_step_2()
        assert can_proceed == False

        # Mark Gate 1.5 as passed
        mock_project.gate_1_5_passed = True
        can_proceed = mock_project.can_proceed_to_step_2()
        assert can_proceed == True


class TestStepReExecutionClearsGates:
    """Test suite for gate clearing when re-executing steps."""

    @pytest.mark.asyncio
    async def test_step_re_execution_clears_gates(self, project_manager, mock_project):
        """Test that re-executing a step clears related gate statuses."""
        # Complete step_0_1 and pass Gate 0
        step_0_1 = next(s for s in mock_project.steps if s.step_id == "step_0_1")
        step_0_1.status = StepStatus.COMPLETED
        mock_project.gate_0_passed = True

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step01') as mock_step01:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step01.return_value = mock_instance

            # Re-execute step_0_1
            await project_manager.execute_step(mock_project, "step_0_1")

            # Gate 0 should be cleared
            assert mock_project.gate_0_passed == False

    @pytest.mark.asyncio
    async def test_step_1_re_execution_clears_step_1_gates(self, project_manager, mock_project):
        """Test that re-executing Step 1 steps clears Step 1 gates."""
        # Complete all Step 0 and Step 1 steps
        for step in mock_project.steps:
            if step.step_id.startswith("step_0_") or step.step_id.startswith("step_1_"):
                step.status = StepStatus.COMPLETED

        # Pass all Step 1 gates
        mock_project.gate_1_passed = True
        mock_project.gate_1_25_passed = True
        mock_project.gate_1_5_passed = True
        mock_project.gate_1_6_passed = True

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step13') as mock_step13:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step13.return_value = mock_instance

            # Re-execute step_1_3
            await project_manager.execute_step(mock_project, "step_1_3")

            # All Step 1 gates should be cleared
            assert mock_project.gate_1_passed == False
            assert mock_project.gate_1_25_passed == False
            assert mock_project.gate_1_5_passed == False
            assert mock_project.gate_1_6_passed == False

    @pytest.mark.asyncio
    async def test_step_2_re_execution_clears_gate_2_only(self, project_manager, mock_project):
        """Test that re-executing Step 2 clears only Gate 2."""
        # Complete all steps
        for step in mock_project.steps:
            step.status = StepStatus.COMPLETED

        # Pass all gates
        mock_project.gate_0_passed = True
        mock_project.gate_1_passed = True
        mock_project.gate_1_25_passed = True
        mock_project.gate_1_5_passed = True
        mock_project.gate_1_6_passed = True
        mock_project.gate_2_passed = True

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step23') as mock_step23:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step23.return_value = mock_instance

            # Re-execute step_2_3
            await project_manager.execute_step(mock_project, "step_2_3")

            # Gate 2 should be cleared
            assert mock_project.gate_2_passed == False

            # Earlier gates should remain passed
            assert mock_project.gate_0_passed == True
            assert mock_project.gate_1_5_passed == True


class TestAutoGateCheckAfterSteps:
    """Test suite for automatic gate checking after specific steps."""

    @pytest.mark.asyncio
    async def test_auto_gate_check_after_step_1_1b(self, project_manager, mock_project):
        """Test that Gate 1.6 is automatically checked after step_1_1b."""
        # Complete prerequisites
        for step in mock_project.steps:
            if step.step_id in ["step_0_1", "step_0_2", "step_1_1"]:
                step.status = StepStatus.COMPLETED

        mock_gate_result = GateResult(
            gate_name="gate_1_6",
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at="2024-01-01T00:00:00"
        )

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step11b') as mock_step11b, \
             patch('app.services.project_manager.GateChecker') as mock_gc_class:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step11b.return_value = mock_instance

            # Mock gate checker
            mock_gc = Mock()
            mock_gc.check_gate_1_6 = Mock(return_value=mock_gate_result)
            mock_gc_class.return_value = mock_gc

            # Execute step_1_1b
            await project_manager.execute_step(mock_project, "step_1_1b")

            # Verify Gate 1.6 was checked automatically
            mock_gc.check_gate_1_6.assert_called_once()
            assert mock_project.gate_1_6_passed == True

    @pytest.mark.asyncio
    async def test_auto_gate_check_after_step_1_2b(self, project_manager, mock_project):
        """Test that Gate 1.25 is automatically checked after step_1_2b."""
        # Complete prerequisites
        for step in mock_project.steps:
            if step.step_id in ["step_0_1", "step_0_2", "step_1_1", "step_1_1b", "step_1_2"]:
                step.status = StepStatus.COMPLETED

        mock_gate_result = GateResult(
            gate_name="gate_1_25",
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at="2024-01-01T00:00:00"
        )

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step12b') as mock_step12b, \
             patch('app.services.project_manager.GateChecker') as mock_gc_class:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step12b.return_value = mock_instance

            # Mock gate checker
            mock_gc = Mock()
            mock_gc.check_gate_1_25 = Mock(return_value=mock_gate_result)
            mock_gc_class.return_value = mock_gc

            # Execute step_1_2b
            await project_manager.execute_step(mock_project, "step_1_2b")

            # Verify Gate 1.25 was checked automatically
            mock_gc.check_gate_1_25.assert_called_once()
            assert mock_project.gate_1_25_passed == True

    @pytest.mark.asyncio
    async def test_auto_gate_check_failure_updates_status(self, project_manager, mock_project):
        """Test that failed auto gate check updates project status correctly."""
        # Complete prerequisites
        for step in mock_project.steps:
            if step.step_id in ["step_0_1", "step_0_2", "step_1_1"]:
                step.status = StepStatus.COMPLETED

        mock_gate_result = GateResult(
            gate_name="gate_1_6",
            verdict="FAIL",
            check_items=[],
            suggestions=["Fix DOI validation issues"],
            checked_at="2024-01-01T00:00:00"
        )

        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step11b') as mock_step11b, \
             patch('app.services.project_manager.GateChecker') as mock_gc_class:

            # Mock step execution
            mock_instance = AsyncMock()
            mock_instance.execute = AsyncMock()
            mock_step11b.return_value = mock_instance

            # Mock gate checker
            mock_gc = Mock()
            mock_gc.check_gate_1_6 = Mock(return_value=mock_gate_result)
            mock_gc_class.return_value = mock_gc

            # Execute step_1_1b
            await project_manager.execute_step(mock_project, "step_1_1b")

            # Gate should remain not passed
            assert mock_project.gate_1_6_passed == False


class TestCompleteStepSequence:
    """Test suite for complete step sequence execution."""

    @pytest.mark.asyncio
    async def test_complete_step_0_sequence(self, project_manager, mock_project):
        """Test executing all Step 0 steps in sequence."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step01') as mock_step01, \
             patch('app.services.project_manager.Step02') as mock_step02:

            # Mock step execution
            for mock_step in [mock_step01, mock_step02]:
                mock_instance = AsyncMock()
                mock_instance.execute = AsyncMock()
                mock_step.return_value = mock_instance

            # Execute Step 0 sequence
            await project_manager.execute_step(mock_project, "step_0_1")
            await project_manager.execute_step(mock_project, "step_0_2")

            # Verify all Step 0 steps are completed
            step_0_steps = [s for s in mock_project.steps if s.step_id.startswith("step_0_")]
            assert all(s.status == StepStatus.COMPLETED for s in step_0_steps)

    @pytest.mark.asyncio
    async def test_step_execution_order_enforced(self, project_manager, mock_project):
        """Test that steps must be executed in order."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'):

            # Try to execute steps out of order
            with pytest.raises(ValueError):
                await project_manager.execute_step(mock_project, "step_1_5")

            with pytest.raises(ValueError):
                await project_manager.execute_step(mock_project, "step_2_5")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

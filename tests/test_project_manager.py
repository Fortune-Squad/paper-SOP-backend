"""
Unit tests for ProjectManager service.
Tests project creation, step prerequisites, gate clearing, and step execution.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from app.services.project_manager import ProjectManager
from app.models.project import Project, ProjectConfig, StepStatus
from app.models.gate import GateResult


class TestProjectCreation:
    """Test suite for project creation."""

    @pytest.fixture
    def project_manager(self):
        """Create a ProjectManager instance for testing."""
        return ProjectManager()

    @pytest.fixture
    def sample_config(self):
        """Create a sample project configuration."""
        return ProjectConfig(
            topic="Test ML Project",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["Must use PyTorch", "Must be reproducible"],
            keywords=["machine learning", "deep learning", "neural networks"]
        )

    @pytest.mark.asyncio
    async def test_create_project(self, project_manager, sample_config):
        """Test creating a new project with valid configuration."""
        with patch('app.services.project_manager.FileManager') as mock_fm, \
             patch('app.services.project_manager.GitManager') as mock_gm:

            mock_fm.return_value.ensure_project_dir = Mock()
            mock_gm.return_value.init_repo = Mock()
            mock_gm.return_value.commit = Mock()

            project = await project_manager.create_project(sample_config)

            assert project is not None
            assert project.config.topic == sample_config.topic
            assert project.config.target_venue == sample_config.target_venue
            assert len(project.steps) == 16  # v4.0 has 16 steps

            # Verify all steps are initialized with PENDING status
            for step in project.steps:
                assert step.status == StepStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_project_initializes_all_steps(self, project_manager, sample_config):
        """Test that project creation initializes all 16 steps correctly."""
        with patch('app.services.project_manager.FileManager') as mock_fm, \
             patch('app.services.project_manager.GitManager') as mock_gm:

            mock_fm.return_value.ensure_project_dir = Mock()
            mock_gm.return_value.init_repo = Mock()
            mock_gm.return_value.commit = Mock()

            project = await project_manager.create_project(sample_config)

            # Check that all expected step IDs are present
            expected_step_ids = {
                "step_0_1", "step_0_2",
                "step_1_1", "step_1_1b", "step_1_2", "step_1_2b", "step_1_3", "step_1_4", "step_1_5",
                "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
            }
            step_ids = {step.step_id for step in project.steps}
            assert step_ids == expected_step_ids

    @pytest.mark.asyncio
    async def test_create_project_initializes_gates(self, project_manager, sample_config):
        """Test that project creation initializes all 6 gates as not passed."""
        with patch('app.services.project_manager.FileManager') as mock_fm, \
             patch('app.services.project_manager.GitManager') as mock_gm:

            mock_fm.return_value.ensure_project_dir = Mock()
            mock_gm.return_value.init_repo = Mock()
            mock_gm.return_value.commit = Mock()

            project = await project_manager.create_project(sample_config)

            # All gates should be False initially
            assert project.gate_0_passed == False
            assert project.gate_1_passed == False
            assert project.gate_1_25_passed == False
            assert project.gate_1_5_passed == False
            assert project.gate_1_6_passed == False
            assert project.gate_2_passed == False


class TestStepPrerequisites:
    """Test suite for step prerequisite validation."""

    @pytest.fixture
    def project_manager(self):
        return ProjectManager()

    @pytest.fixture
    def mock_project(self):
        """Create a mock project with some completed steps."""
        config = ProjectConfig(
            topic="Test",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["test"],
            keywords=["test"]
        )
        project = Project(project_id="test_project", config=config)
        return project

    def test_validate_step_prerequisites_first_step(self, project_manager, mock_project):
        """Test that step_0_1 has no prerequisites."""
        is_valid, message = project_manager._validate_step_prerequisites(mock_project, "step_0_1")
        assert is_valid == True
        assert message == ""

    def test_validate_step_prerequisites_sequential_steps(self, project_manager, mock_project):
        """Test that steps require previous steps to be completed."""
        # Try to execute step_0_2 without completing step_0_1
        is_valid, message = project_manager._validate_step_prerequisites(mock_project, "step_0_2")
        assert is_valid == False
        assert "step_0_1" in message

    def test_validate_step_prerequisites_with_completed_prerequisite(self, project_manager, mock_project):
        """Test that step can proceed when prerequisite is completed."""
        # Mark step_0_1 as completed
        for step in mock_project.steps:
            if step.step_id == "step_0_1":
                step.status = StepStatus.COMPLETED
                break

        is_valid, message = project_manager._validate_step_prerequisites(mock_project, "step_0_2")
        assert is_valid == True

    def test_validate_step_prerequisites_gate_1_5_blocks_step_2(self, project_manager, mock_project):
        """Test that Gate 1.5 must pass before entering Step 2."""
        # Complete all Step 0 and Step 1 steps
        for step in mock_project.steps:
            if step.step_id.startswith("step_0_") or step.step_id.startswith("step_1_"):
                step.status = StepStatus.COMPLETED

        # Try to execute step_2_0 without Gate 1.5 passing
        mock_project.gate_1_5_passed = False
        is_valid, message = project_manager._validate_step_prerequisites(mock_project, "step_2_0")

        assert is_valid == False
        assert "Gate 1.5" in message or "gate_1_5" in message

    def test_validate_step_prerequisites_gate_1_5_allows_step_2(self, project_manager, mock_project):
        """Test that Step 2 can proceed when Gate 1.5 passes."""
        # Complete all Step 0 and Step 1 steps
        for step in mock_project.steps:
            if step.step_id.startswith("step_0_") or step.step_id.startswith("step_1_"):
                step.status = StepStatus.COMPLETED

        # Mark Gate 1.5 as passed
        mock_project.gate_1_5_passed = True

        is_valid, message = project_manager._validate_step_prerequisites(mock_project, "step_2_0")
        assert is_valid == True


class TestGateClearing:
    """Test suite for gate clearing on step re-execution."""

    @pytest.fixture
    def project_manager(self):
        return ProjectManager()

    @pytest.fixture
    def mock_project(self):
        """Create a mock project with gates passed."""
        config = ProjectConfig(
            topic="Test",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["test"],
            keywords=["test"]
        )
        project = Project(project_id="test_project", config=config)
        # Set all gates as passed
        project.gate_0_passed = True
        project.gate_1_passed = True
        project.gate_1_25_passed = True
        project.gate_1_5_passed = True
        project.gate_1_6_passed = True
        project.gate_2_passed = True
        return project

    def test_clear_related_gates_step_0(self, project_manager, mock_project):
        """Test that re-executing Step 0 clears Gate 0."""
        project_manager._clear_related_gates(mock_project, "step_0_1")

        assert mock_project.gate_0_passed == False
        # Other gates should remain unchanged
        assert mock_project.gate_1_passed == True

    def test_clear_related_gates_step_1(self, project_manager, mock_project):
        """Test that re-executing Step 1 clears related gates."""
        project_manager._clear_related_gates(mock_project, "step_1_3")

        # Should clear Gate 1, 1.25, 1.5, 1.6
        assert mock_project.gate_1_passed == False
        assert mock_project.gate_1_25_passed == False
        assert mock_project.gate_1_5_passed == False
        assert mock_project.gate_1_6_passed == False
        # Gate 0 should remain unchanged
        assert mock_project.gate_0_passed == True

    def test_clear_related_gates_step_2(self, project_manager, mock_project):
        """Test that re-executing Step 2 clears Gate 2."""
        project_manager._clear_related_gates(mock_project, "step_2_3")

        assert mock_project.gate_2_passed == False
        # Earlier gates should remain unchanged
        assert mock_project.gate_1_5_passed == True


class TestGetNextStep:
    """Test suite for getting the next available step."""

    @pytest.fixture
    def project_manager(self):
        return ProjectManager()

    @pytest.fixture
    def mock_project(self):
        config = ProjectConfig(
            topic="Test",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["test"],
            keywords=["test"]
        )
        return Project(project_id="test_project", config=config)

    def test_get_next_step_at_start(self, project_manager, mock_project):
        """Test that the first next step is step_0_1."""
        next_step = project_manager.get_next_step(mock_project)
        assert next_step is not None
        assert next_step.step_id == "step_0_1"

    def test_get_next_step_after_completion(self, project_manager, mock_project):
        """Test that get_next_step returns the next uncompleted step."""
        # Complete step_0_1
        for step in mock_project.steps:
            if step.step_id == "step_0_1":
                step.status = StepStatus.COMPLETED
                break

        next_step = project_manager.get_next_step(mock_project)
        assert next_step is not None
        assert next_step.step_id == "step_0_2"

    def test_get_next_step_all_completed(self, project_manager, mock_project):
        """Test that get_next_step returns None when all steps are completed."""
        # Complete all steps
        for step in mock_project.steps:
            step.status = StepStatus.COMPLETED

        next_step = project_manager.get_next_step(mock_project)
        assert next_step is None


class TestExecuteStepValidation:
    """Test suite for step execution validation."""

    @pytest.fixture
    def project_manager(self):
        return ProjectManager()

    @pytest.fixture
    def mock_project(self):
        config = ProjectConfig(
            topic="Test ML Project",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["constraint"],
            keywords=["test"]
        )
        return Project(project_id="test_project", config=config)

    @pytest.mark.asyncio
    async def test_execute_step_validation_fails_prerequisite(self, project_manager, mock_project):
        """Test that step execution fails when prerequisites are not met."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'):

            # Try to execute step_0_2 without completing step_0_1
            with pytest.raises(ValueError) as exc_info:
                await project_manager.execute_step(mock_project, "step_0_2")

            assert "前置步骤未完成" in str(exc_info.value) or "prerequisite" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_execute_step_validation_clears_gates(self, project_manager, mock_project):
        """Test that step execution clears related gates."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step01') as mock_step_class:

            # Mock the step execution
            mock_step_instance = AsyncMock()
            mock_step_instance.execute = AsyncMock()
            mock_step_class.return_value = mock_step_instance

            # Set Gate 0 as passed
            mock_project.gate_0_passed = True

            # Execute step_0_1 (should clear Gate 0)
            await project_manager.execute_step(mock_project, "step_0_1")

            # Gate 0 should be cleared
            assert mock_project.gate_0_passed == False


class TestAutoGateChecking:
    """Test suite for automatic gate checking after specific steps."""

    @pytest.fixture
    def project_manager(self):
        return ProjectManager()

    @pytest.fixture
    def mock_project(self):
        config = ProjectConfig(
            topic="Test",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["test"],
            keywords=["test"]
        )
        project = Project(project_id="test_project", config=config)
        # Mark step_1_1 as completed so we can execute step_1_1b
        for step in project.steps:
            if step.step_id in ["step_0_1", "step_0_2", "step_1_1"]:
                step.status = StepStatus.COMPLETED
        return project

    @pytest.mark.asyncio
    async def test_auto_gate_check_after_step_1_1b(self, project_manager, mock_project):
        """Test that Gate 1.6 is automatically checked after step_1_1b."""
        with patch('app.services.project_manager.FileManager'), \
             patch('app.services.project_manager.GitManager'), \
             patch('app.services.project_manager.Step11b') as mock_step_class, \
             patch('app.services.project_manager.GateChecker') as mock_gate_checker_class:

            # Mock step execution
            mock_step_instance = AsyncMock()
            mock_step_instance.execute = AsyncMock()
            mock_step_class.return_value = mock_step_instance

            # Mock gate checker
            mock_gate_checker = Mock()
            mock_gate_result = GateResult(
                gate_name="gate_1_6",
                verdict="PASS",
                check_items=[],
                suggestions=[],
                checked_at="2024-01-01T00:00:00"
            )
            mock_gate_checker.check_gate_1_6 = Mock(return_value=mock_gate_result)
            mock_gate_checker_class.return_value = mock_gate_checker

            await project_manager.execute_step(mock_project, "step_1_1b")

            # Verify Gate 1.6 was checked
            mock_gate_checker.check_gate_1_6.assert_called_once()
            assert mock_project.gate_1_6_passed == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

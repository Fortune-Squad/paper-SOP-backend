"""
Integration tests for API endpoints.
Tests the FastAPI endpoints for project management, step execution, and gate checking.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from app.main import app
from app.models.project import Project, ProjectConfig, StepStatus
from app.models.gate import GateResult


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_project_config():
    """Sample project configuration for testing."""
    return {
        "topic": "Test ML Project for API Integration",
        "target_venue": "NeurIPS 2026",
        "research_type": "ml",
        "data_status": "available",
        "hard_constraints": ["Must use PyTorch", "Must complete in 3 months"],
        "keywords": ["machine learning", "neural networks", "computer vision"]
    }


@pytest.fixture
def mock_project():
    """Create a mock project object."""
    config = ProjectConfig(
        topic="Test Project",
        target_venue="NeurIPS 2026",
        research_type="ml",
        data_status="available",
        hard_constraints=["test"],
        keywords=["test"]
    )
    project = Project(project_id="test_project_123", config=config)
    # Mark first step as completed
    project.steps[0].status = StepStatus.COMPLETED
    return project


class TestHealthEndpoint:
    """Test suite for health check endpoint."""

    def test_health_endpoint(self, client):
        """Test that the health endpoint returns 200 OK."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Paper SOP" in data["message"]


class TestVersionEndpoint:
    """Test suite for version endpoint."""

    def test_version_endpoint(self, client):
        """Test that the version endpoint returns correct version info."""
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()
        assert "app_version" in data
        assert "api_version" in data
        assert "sop_version" in data
        assert data["sop_version"] == "v4.0"


class TestCreateProjectEndpoint:
    """Test suite for project creation endpoint."""

    def test_create_project_endpoint(self, client, sample_project_config, mock_project):
        """Test creating a project via API endpoint."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            # Mock ProjectManager.create_project
            mock_pm = AsyncMock()
            mock_pm.create_project = AsyncMock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.post("/api/projects", json=sample_project_config)

            assert response.status_code == 200
            data = response.json()
            assert "project_id" in data
            assert "config" in data
            assert data["config"]["topic"] == mock_project.config.topic

    def test_create_project_endpoint_validation_error(self, client):
        """Test that invalid project config returns 422 error."""
        invalid_config = {
            "topic": "",  # Empty topic should fail validation
            "target_venue": "NeurIPS 2026",
            "research_type": "ml",
            "data_status": "available",
            "hard_constraints": [],
            "keywords": []
        }

        response = client.post("/api/projects", json=invalid_config)
        assert response.status_code == 422  # Validation error

    def test_create_project_endpoint_missing_fields(self, client):
        """Test that missing required fields returns 422 error."""
        incomplete_config = {
            "topic": "Test Project"
            # Missing other required fields
        }

        response = client.post("/api/projects", json=incomplete_config)
        assert response.status_code == 422


class TestGetProjectEndpoint:
    """Test suite for get project endpoint."""

    def test_get_project_endpoint(self, client, mock_project):
        """Test retrieving a project via API endpoint."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = Mock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.get(f"/api/projects/{mock_project.project_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == mock_project.project_id

    def test_get_project_endpoint_not_found(self, client):
        """Test that getting non-existent project returns 404."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = Mock()
            mock_pm.load_project = Mock(side_effect=FileNotFoundError("Project not found"))
            mock_pm_class.return_value = mock_pm

            response = client.get("/api/projects/nonexistent_project")

            assert response.status_code == 404


class TestExecuteStepEndpoint:
    """Test suite for step execution endpoint."""

    def test_execute_step_endpoint(self, client, mock_project):
        """Test executing a step via API endpoint."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = AsyncMock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm.execute_step = AsyncMock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.post(f"/api/projects/{mock_project.project_id}/steps/step_0_1/execute")

            assert response.status_code == 200
            data = response.json()
            assert "project_id" in data
            assert "steps" in data

    def test_execute_step_endpoint_invalid_step_id(self, client, mock_project):
        """Test that invalid step ID returns 400 error."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = Mock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.post(f"/api/projects/{mock_project.project_id}/steps/invalid_step/execute")

            assert response.status_code == 400
            data = response.json()
            assert "无效的步骤 ID" in data["detail"]

    def test_execute_step_endpoint_prerequisite_not_met(self, client, mock_project):
        """Test that executing step without prerequisites returns error."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = AsyncMock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm.execute_step = AsyncMock(side_effect=ValueError("Prerequisites not met"))
            mock_pm_class.return_value = mock_pm

            response = client.post(f"/api/projects/{mock_project.project_id}/steps/step_2_0/execute")

            assert response.status_code == 400


class TestCheckGateEndpoint:
    """Test suite for gate checking endpoint."""

    def test_check_gate_endpoint(self, client, mock_project):
        """Test checking a gate via API endpoint."""
        mock_gate_result = GateResult(
            gate_name="gate_0",
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at="2024-01-01T00:00:00"
        )

        with patch('app.api.projects.ProjectManager') as mock_pm_class, \
             patch('app.api.projects.GateChecker') as mock_gc_class:

            mock_pm = Mock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm.save_project = Mock()
            mock_pm_class.return_value = mock_pm

            mock_gc = Mock()
            mock_gc.check_gate = Mock(return_value=mock_gate_result)
            mock_gc_class.return_value = mock_gc

            response = client.post(f"/api/projects/{mock_project.project_id}/gates/gate_0/check")

            assert response.status_code == 200
            data = response.json()
            assert data["gate_name"] == "gate_0"
            assert data["verdict"] == "PASS"

    def test_check_gate_endpoint_invalid_gate_name(self, client, mock_project):
        """Test that invalid gate name returns 400 error."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = Mock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.post(f"/api/projects/{mock_project.project_id}/gates/invalid_gate/check")

            assert response.status_code == 400
            data = response.json()
            assert "无效的 Gate 名称" in data["detail"]

    def test_check_gate_endpoint_updates_project_status(self, client, mock_project):
        """Test that checking gate updates project gate status."""
        mock_gate_result = GateResult(
            gate_name="gate_1_25",
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at="2024-01-01T00:00:00"
        )

        with patch('app.api.projects.ProjectManager') as mock_pm_class, \
             patch('app.api.projects.GateChecker') as mock_gc_class:

            mock_pm = Mock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm.save_project = Mock()
            mock_pm_class.return_value = mock_pm

            mock_gc = Mock()
            mock_gc.check_gate = Mock(return_value=mock_gate_result)
            mock_gc_class.return_value = mock_gc

            response = client.post(f"/api/projects/{mock_project.project_id}/gates/gate_1_25/check")

            assert response.status_code == 200
            # Verify save_project was called to persist gate status
            mock_pm.save_project.assert_called_once()


class TestGetProjectStatusEndpoint:
    """Test suite for project status endpoint."""

    def test_get_project_status_endpoint(self, client, mock_project):
        """Test retrieving project status via API endpoint."""
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = Mock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.get(f"/api/projects/{mock_project.project_id}")

            assert response.status_code == 200
            data = response.json()
            assert "project_id" in data
            assert "config" in data
            assert "steps" in data
            assert "gate_0_passed" in data
            assert len(data["steps"]) == 16  # v4.0 has 16 steps


class TestInvalidInputHandling:
    """Test suite for invalid input handling across all endpoints."""

    def test_invalid_project_id_format(self, client):
        """Test that invalid project ID format returns 400 error."""
        invalid_project_id = "project@invalid#chars"

        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = Mock()
            mock_pm.load_project = Mock(side_effect=Exception("Invalid ID"))
            mock_pm_class.return_value = mock_pm

            response = client.get(f"/api/projects/{invalid_project_id}")

            assert response.status_code == 400

    def test_empty_project_id(self, client):
        """Test that empty project ID returns 404."""
        response = client.get("/api/projects/")
        # This should return 404 (not found) since the route doesn't match
        assert response.status_code == 404

    def test_invalid_json_payload(self, client):
        """Test that malformed JSON returns 422 error."""
        response = client.post(
            "/api/projects",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422

    def test_extra_fields_in_config(self, client, sample_project_config, mock_project):
        """Test that extra fields in config are handled gracefully."""
        config_with_extra = sample_project_config.copy()
        config_with_extra["extra_field"] = "should be ignored"

        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = AsyncMock()
            mock_pm.create_project = AsyncMock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            response = client.post("/api/projects", json=config_with_extra)

            # Should succeed (extra fields ignored by Pydantic)
            assert response.status_code == 200


class TestConcurrentRequests:
    """Test suite for handling concurrent requests."""

    def test_concurrent_step_execution(self, client, mock_project):
        """Test that concurrent step executions are handled correctly."""
        # This is a basic test - real concurrency testing would require
        # multiple threads/processes
        with patch('app.api.projects.ProjectManager') as mock_pm_class:
            mock_pm = AsyncMock()
            mock_pm.load_project = Mock(return_value=mock_project)
            mock_pm.execute_step = AsyncMock(return_value=mock_project)
            mock_pm_class.return_value = mock_pm

            # Simulate two requests for same step
            response1 = client.post(f"/api/projects/{mock_project.project_id}/steps/step_0_1/execute")
            response2 = client.post(f"/api/projects/{mock_project.project_id}/steps/step_0_1/execute")

            assert response1.status_code == 200
            assert response2.status_code == 200


class TestErrorResponseFormat:
    """Test suite for error response format consistency."""

    def test_error_response_has_detail(self, client):
        """Test that error responses include 'detail' field."""
        response = client.get("/api/projects/nonexistent")

        assert response.status_code in [400, 404, 500]
        data = response.json()
        assert "detail" in data

    def test_validation_error_response_format(self, client):
        """Test that validation errors have proper format."""
        invalid_config = {"topic": ""}  # Missing required fields

        response = client.post("/api/projects", json=invalid_config)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

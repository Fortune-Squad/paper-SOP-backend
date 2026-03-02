"""
Integration tests for API endpoints.
Tests the FastAPI endpoints for project management, step execution, and gate checking.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock, MagicMock
from app.main import app
from app.models.project import Project, ProjectConfig, StepStatus, ResearchType, DataStatus
from app.models.gate import GateResult, GateType, GateVerdict
from app.middleware.auth import get_current_active_user


# --- Auth bypass (scoped to this module's fixtures) ---
def _fake_user():
    user = MagicMock()
    user.id = 1
    user.username = "testuser"
    user.role = "admin"
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def _override_auth():
    """Override auth for this module only, restore after."""
    app.dependency_overrides[get_current_active_user] = lambda: _fake_user()
    yield
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_project_config():
    return {
        "topic": "Test ML Project for API Integration",
        "target_venue": "NeurIPS 2026",
        "research_type": "ml",
        "data_status": "available",
        "hard_constraints": ["Must use PyTorch", "Must complete in 3 months"],
        "keywords": ["machine learning", "neural networks", "computer vision"],
    }


def _make_config():
    return ProjectConfig(
        topic="Test Project",
        target_venue="NeurIPS 2026",
        research_type=ResearchType.ML,
        data_status=DataStatus.AVAILABLE,
        hard_constraints=["test"],
        keywords=["test"],
    )


def _make_project(**overrides):
    defaults = dict(project_id="test_project_123", project_name="Test Project", config=_make_config())
    defaults.update(overrides)
    return Project(**defaults)


@pytest.fixture
def mock_project():
    return _make_project()


# ═══════════════════════════════════════════════════════════════════
# Health / Version
# ═══════════════════════════════════════════════════════════════════

class TestHealthEndpoint:
    def test_health_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data

class TestVersionEndpoint:
    def test_version_endpoint(self, client):
        response = client.get("/api/version")
        assert response.status_code == 200
        data = response.json()
        assert "app_version" in data
        assert "api_version" in data


# ═══════════════════════════════════════════════════════════════════
# Create Project
# ═══════════════════════════════════════════════════════════════════

class TestCreateProjectEndpoint:

    def test_create_project_endpoint(self, client, sample_project_config, mock_project):
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm.create_project = AsyncMock(return_value=mock_project)

            # P1-1: skip_bootloader and skip_reason are now Body parameters
            request_body = {
                "config": sample_project_config,
                "skip_bootloader": False,
                "skip_reason": None
            }
            response = client.post("/api/projects/", json=request_body)
            assert response.status_code == 201
            data = response.json()
            assert "project_id" in data

    def test_create_project_endpoint_missing_fields(self, client):
        incomplete_config = {"topic": "Test Project"}
        response = client.post("/api/projects/", json=incomplete_config)
        assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════════
# Get Project
# ═══════════════════════════════════════════════════════════════════

class TestGetProjectEndpoint:

    def test_get_project_endpoint(self, client, mock_project):
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm._load_project = AsyncMock(return_value=mock_project)
            mock_pm.check_project_access = Mock(return_value=True)
            mock_pm.get_project_status = AsyncMock(return_value={
                "project_id": mock_project.project_id,
                "status": "created",
            })

            response = client.get(f"/api/projects/{mock_project.project_id}")
            assert response.status_code == 200

    def test_get_project_endpoint_not_found(self, client):
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm._load_project = AsyncMock(side_effect=FileNotFoundError("Not found"))

            response = client.get("/api/projects/nonexistent_project")
            assert response.status_code in [404, 500]


# ═══════════════════════════════════════════════════════════════════
# Execute Step
# ═══════════════════════════════════════════════════════════════════

class TestExecuteStepEndpoint:

    def test_execute_step_endpoint(self, client, mock_project):
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm._load_project = AsyncMock(return_value=mock_project)
            mock_pm.execute_step = AsyncMock(return_value=mock_project)
            mock_pm.check_project_access = Mock(return_value=True)

            response = client.post(f"/api/projects/{mock_project.project_id}/steps/step_0_1/execute")
            assert response.status_code == 200

    def test_execute_step_endpoint_invalid_step_id(self, client, mock_project):
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm._load_project = AsyncMock(return_value=mock_project)
            mock_pm.check_project_access = Mock(return_value=True)

            response = client.post(f"/api/projects/{mock_project.project_id}/steps/invalid_step/execute")
            assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# Check Gate
# ═══════════════════════════════════════════════════════════════════

class TestCheckGateEndpoint:

    def test_check_gate_endpoint(self, client, mock_project):
        mock_gate_result = {
            "gate_type": "gate_0", "verdict": "PASS",
            "check_items": [], "passed_count": 3, "total_count": 3,
            "suggestions": [], "project_id": mock_project.project_id,
        }
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm._load_project = AsyncMock(return_value=mock_project)
            mock_pm.check_gate = AsyncMock(return_value=mock_gate_result)

            response = client.post(f"/api/projects/{mock_project.project_id}/gates/gate_0/check")
            assert response.status_code == 200

    def test_check_gate_endpoint_invalid_gate_name(self, client, mock_project):
        with patch('app.api.projects.project_manager') as mock_pm:
            mock_pm._load_project = AsyncMock(return_value=mock_project)

            response = client.post(f"/api/projects/{mock_project.project_id}/gates/invalid_gate/check")
            assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# Error Responses
# ═══════════════════════════════════════════════════════════════════

class TestErrorResponseFormat:

    def test_validation_error_response_format(self, client):
        invalid_config = {"topic": ""}
        response = client.post("/api/projects", json=invalid_config)
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


# ═══════════════════════════════════════════════════════════════════
# Input Handling
# ═══════════════════════════════════════════════════════════════════

class TestInvalidInputHandling:

    def test_malformed_json(self, client):
        response = client.post(
            "/api/projects",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

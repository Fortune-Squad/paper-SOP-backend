"""
Unit tests for input validation functions in the API layer.
Tests the validation of project_id, step_id, and gate_name parameters.
"""

import pytest
from fastapi import HTTPException
from app.api.projects import (
    validate_project_id,
    validate_step_id,
    validate_gate_name,
    VALID_STEP_IDS,
    VALID_GATE_NAMES,
)


class TestProjectIdValidation:
    """Test suite for project ID validation."""

    def test_validate_project_id_valid(self):
        """Test validation with valid project IDs."""
        valid_ids = [
            "project_123",
            "my-project",
            "test_project_2024",
            "proj-456-test",
        ]
        for project_id in valid_ids:
            # Should not raise exception
            validate_project_id(project_id)

    def test_validate_project_id_invalid_empty(self):
        """Test validation with empty project ID."""
        with pytest.raises(HTTPException) as exc_info:
            validate_project_id("")
        assert exc_info.value.status_code == 400
        assert "不能为空" in str(exc_info.value.detail)

    def test_validate_project_id_invalid_whitespace(self):
        """Test validation with whitespace-only project ID."""
        with pytest.raises(HTTPException) as exc_info:
            validate_project_id("   ")
        assert exc_info.value.status_code == 400
        assert "不能为空" in str(exc_info.value.detail)

    def test_validate_project_id_invalid_special_chars(self):
        """Test validation with invalid special characters."""
        invalid_ids = [
            "project@123",
            "my project",  # space
            "test#project",
            "proj/test",
            "proj\\test",
        ]
        for project_id in invalid_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_id(project_id)
            assert exc_info.value.status_code == 400
            assert "只能包含" in str(exc_info.value.detail)


class TestStepIdValidation:
    """Test suite for step ID validation."""

    def test_validate_step_id_valid(self):
        """Test validation with all valid step IDs."""
        # Test all valid step IDs from VALID_STEP_IDS
        for step_id in VALID_STEP_IDS:
            validate_step_id(step_id)

    def test_validate_step_id_invalid_empty(self):
        """Test validation with empty step ID."""
        with pytest.raises(HTTPException) as exc_info:
            validate_step_id("")
        assert exc_info.value.status_code == 400
        assert "不能为空" in str(exc_info.value.detail)

    def test_validate_step_id_invalid_format(self):
        """Test validation with invalid step ID formats."""
        invalid_ids = [
            "step_3_1",  # Non-existent step
            "step_0",    # Missing sub-step
            "step_1_6",  # Non-existent sub-step
            "invalid",   # Completely wrong format
            "step_2_10", # Out of range
        ]
        for step_id in invalid_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_step_id(step_id)
            assert exc_info.value.status_code == 400
            assert "无效的步骤 ID" in str(exc_info.value.detail)

    def test_validate_step_id_case_sensitive(self):
        """Test that step ID validation is case-sensitive."""
        with pytest.raises(HTTPException) as exc_info:
            validate_step_id("STEP_0_1")
        assert exc_info.value.status_code == 400


class TestGateNameValidation:
    """Test suite for gate name validation."""

    def test_validate_gate_name_valid(self):
        """Test validation with all valid gate names."""
        # Test all valid gate names from VALID_GATE_NAMES
        for gate_name in VALID_GATE_NAMES:
            validate_gate_name(gate_name)

    def test_validate_gate_name_invalid_empty(self):
        """Test validation with empty gate name."""
        with pytest.raises(HTTPException) as exc_info:
            validate_gate_name("")
        assert exc_info.value.status_code == 400
        assert "不能为空" in str(exc_info.value.detail)

    def test_validate_gate_name_invalid_format(self):
        """Test validation with invalid gate name formats."""
        invalid_names = [
            "gate_3",     # Non-existent gate
            "gate_0_5",   # Wrong format
            "invalid",    # Completely wrong format
            "Gate_0",     # Wrong case
        ]
        for gate_name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                validate_gate_name(gate_name)
            assert exc_info.value.status_code == 400
            assert "无效的 Gate 名称" in str(exc_info.value.detail)

    def test_validate_gate_name_case_sensitive(self):
        """Test that gate name validation is case-sensitive."""
        with pytest.raises(HTTPException) as exc_info:
            validate_gate_name("GATE_0")
        assert exc_info.value.status_code == 400


class TestValidationConstants:
    """Test suite for validation constant definitions."""

    def test_valid_step_ids_count(self):
        """Test that all 16 steps are defined in VALID_STEP_IDS."""
        expected_count = 16  # v4.0 has 16 steps
        assert len(VALID_STEP_IDS) == expected_count

    def test_valid_step_ids_content(self):
        """Test that VALID_STEP_IDS contains expected step IDs."""
        expected_steps = {
            # Step 0
            "step_0_1", "step_0_2",
            # Step 1
            "step_1_1", "step_1_1b", "step_1_2", "step_1_2b", "step_1_3", "step_1_4", "step_1_5",
            # Step 2
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
        }
        assert VALID_STEP_IDS == expected_steps

    def test_valid_gate_names_count(self):
        """Test that all 6 gates are defined in VALID_GATE_NAMES."""
        expected_count = 6  # v4.0 has 6 gates
        assert len(VALID_GATE_NAMES) == expected_count

    def test_valid_gate_names_content(self):
        """Test that VALID_GATE_NAMES contains expected gate names."""
        expected_gates = {
            "gate_0", "gate_1", "gate_1_25", "gate_1_5", "gate_1_6", "gate_2"
        }
        assert VALID_GATE_NAMES == expected_gates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

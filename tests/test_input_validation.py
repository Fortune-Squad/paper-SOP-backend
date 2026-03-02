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
        valid_ids = ["project_123", "my-project", "test_project_2024", "proj-456-test"]
        for project_id in valid_ids:
            validate_project_id(project_id)

    def test_validate_project_id_invalid_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_project_id("")
        assert exc_info.value.status_code == 400

    def test_validate_project_id_invalid_whitespace(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_project_id("   ")
        assert exc_info.value.status_code == 400

    def test_validate_project_id_invalid_special_chars(self):
        invalid_ids = ["project@123", "my project", "test#project", "proj/test", "proj\\test"]
        for project_id in invalid_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_id(project_id)
            assert exc_info.value.status_code == 400


class TestStepIdValidation:
    """Test suite for step ID validation."""

    def test_validate_step_id_valid(self):
        for step_id in VALID_STEP_IDS:
            validate_step_id(step_id)

    def test_validate_step_id_invalid_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_step_id("")
        assert exc_info.value.status_code == 400

    def test_validate_step_id_invalid_format(self):
        invalid_ids = ["step_3_1", "step_0", "step_1_6", "invalid", "step_2_10"]
        for step_id in invalid_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_step_id(step_id)
            assert exc_info.value.status_code == 400

    def test_validate_step_id_case_sensitive(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_step_id("STEP_0_1")
        assert exc_info.value.status_code == 400


class TestGateNameValidation:
    """Test suite for gate name validation."""

    def test_validate_gate_name_valid(self):
        for gate_name in VALID_GATE_NAMES:
            validate_gate_name(gate_name)

    def test_validate_gate_name_invalid_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_gate_name("")
        assert exc_info.value.status_code == 400

    def test_validate_gate_name_invalid_format(self):
        invalid_names = ["gate_3", "gate_0_5", "invalid", "Gate_0"]
        for gate_name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                validate_gate_name(gate_name)
            assert exc_info.value.status_code == 400

    def test_validate_gate_name_case_sensitive(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_gate_name("GATE_0")
        assert exc_info.value.status_code == 400


class TestValidationConstants:
    """Test suite for validation constant definitions."""

    def test_valid_step_ids_count(self):
        """v7 has 25 steps + v1.2 adds step_4_repro = 26."""
        assert len(VALID_STEP_IDS) == 26

    def test_valid_step_ids_content(self):
        expected_steps = {
            "step_s_1",
            "step_0_1", "step_0_2",
            "step_1_1a", "step_1_1b", "step_1_1c", "step_1_2", "step_1_3", "step_1_3b", "step_1_4", "step_1_5",
            "step_2_0", "step_2_1", "step_2_2", "step_2_3", "step_2_4", "step_2_4b", "step_2_5",
            "step_3_init", "step_3_exec",
            "step_4_collect", "step_4_figure_polish", "step_4_assembly", "step_4_citation_qa", "step_4_repro", "step_4_package",
        }
        assert VALID_STEP_IDS == expected_steps

    def test_valid_gate_names_count(self):
        """v7 has 9 gates."""
        assert len(VALID_GATE_NAMES) == 8  # v7: gate_1_25 removed

    def test_valid_gate_names_content(self):
        expected_gates = {
            "gate_0", "gate_1", "gate_1_5", "gate_1_6", "gate_2",
            "gate_wp", "gate_freeze", "gate_delivery",
        }
        assert VALID_GATE_NAMES == expected_gates


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

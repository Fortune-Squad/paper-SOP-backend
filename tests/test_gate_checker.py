"""
Unit tests for GateChecker service.
Tests gate checking logic, caching mechanism, and gate validation.
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from app.services.gate_checker import GateChecker, GATE_CHECK_CACHE_TTL
from app.models.gate import GateResult, GateCheckItem
from app.models.document import Document, DocumentType
from app.models.project import Project, ProjectConfig


class TestGateCheckerBasics:
    """Test suite for basic gate checker functionality."""

    @pytest.fixture
    def gate_checker(self):
        """Create a GateChecker instance for testing."""
        return GateChecker()

    @pytest.fixture
    def mock_project(self):
        """Create a mock project for testing."""
        config = ProjectConfig(
            topic="Test Topic",
            target_venue="NeurIPS 2026",
            research_type="ml",
            data_status="available",
            hard_constraints=["Constraint 1"],
            keywords=["keyword1", "keyword2"]
        )
        project = Project(project_id="test_project", config=config)
        return project

    def test_gate_checker_initialization(self, gate_checker):
        """Test that GateChecker initializes correctly."""
        assert gate_checker is not None
        assert hasattr(gate_checker, '_cache')
        assert len(gate_checker._cache) == 0


class TestGate0Check:
    """Test suite for Gate 0 checks."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    @pytest.fixture
    def mock_file_manager(self):
        """Create a mock file manager."""
        mock_fm = Mock()
        return mock_fm

    def test_gate_0_check_with_valid_documents(self, gate_checker, mock_file_manager):
        """Test Gate 0 check when all required documents exist."""
        # Mock documents
        intake_doc = Document(
            doc_type=DocumentType.PROJECT_INTAKE_CARD,
            content="# Project Intake Card\n\nTopic: Test\nVenue: NeurIPS 2026",
            project_id="test_project"
        )
        venue_doc = Document(
            doc_type=DocumentType.VENUE_TASTE_NOTES,
            content="# Venue Taste Notes\n\nVenue analysis...",
            project_id="test_project"
        )

        mock_file_manager.load_document.side_effect = [intake_doc, venue_doc]

        with patch('app.services.gate_checker.FileManager', return_value=mock_file_manager):
            result = gate_checker.check_gate_0("test_project")

        assert result.verdict == "PASS"
        assert result.gate_name == "gate_0"
        assert len(result.check_items) == 2

    def test_gate_0_check_with_missing_documents(self, gate_checker, mock_file_manager):
        """Test Gate 0 check when required documents are missing."""
        # Mock missing documents (return None)
        mock_file_manager.load_document.side_effect = [None, None]

        with patch('app.services.gate_checker.FileManager', return_value=mock_file_manager):
            result = gate_checker.check_gate_0("test_project")

        assert result.verdict == "FAIL"
        assert len(result.suggestions) > 0
        # Should have check items that failed
        failed_items = [item for item in result.check_items if not item.passed]
        assert len(failed_items) > 0


class TestGate125Check:
    """Test suite for Gate 1.25 (Topic Alignment) checks."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_1_25_field_validation(self, gate_checker):
        """Test Gate 1.25 checks topic alignment document fields."""
        mock_fm = Mock()

        # Mock topic alignment document with all required fields
        alignment_doc = Document(
            doc_type=DocumentType.TOPIC_ALIGNMENT_CHECK,
            content="""# Topic Alignment Check

venue_alignment_score: 85
constraints_satisfied: true
keyword_coverage: 90
final_verdict: ALIGNED
recommendation: Proceed with confidence
""",
            project_id="test_project"
        )

        mock_fm.load_document.return_value = alignment_doc

        with patch('app.services.gate_checker.FileManager', return_value=mock_fm):
            result = gate_checker.check_gate_1_25("test_project")

        # Should pass if document exists and contains required fields
        assert result.gate_name == "gate_1_25"
        assert isinstance(result, GateResult)


class TestGate16Check:
    """Test suite for Gate 1.6 (Reference QA) checks."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_1_6_doi_parsing(self, gate_checker):
        """Test Gate 1.6 checks DOI validation in Reference QA report."""
        mock_fm = Mock()

        # Mock Reference QA report with DOI information
        ref_qa_doc = Document(
            doc_type=DocumentType.REFERENCE_QA_REPORT,
            content="""# Reference QA Report

## DOI Validation Results
- Total References: 10
- Valid DOIs: 8
- Invalid DOIs: 2
- DOI Coverage: 80%

## Quality Score
Overall Score: 75/100
""",
            project_id="test_project"
        )

        mock_fm.load_document.return_value = ref_qa_doc

        with patch('app.services.gate_checker.FileManager', return_value=mock_fm):
            result = gate_checker.check_gate_1_6("test_project")

        assert result.gate_name == "gate_1_6"
        assert isinstance(result, GateResult)


class TestGateCacheMechanism:
    """Test suite for gate check caching."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_cache_mechanism(self, gate_checker):
        """Test that gate check results are cached."""
        project_id = "test_project"
        gate_name = "gate_0"

        # Create a mock result
        result = GateResult(
            gate_name=gate_name,
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at=datetime.now().isoformat()
        )

        # Cache the result
        gate_checker._cache_result(project_id, gate_name, result)

        # Retrieve from cache
        cached_result = gate_checker._get_cached_result(project_id, gate_name)

        assert cached_result is not None
        assert cached_result.gate_name == gate_name
        assert cached_result.verdict == "PASS"

    def test_gate_cache_expiration(self, gate_checker):
        """Test that cached results expire after TTL."""
        project_id = "test_project"
        gate_name = "gate_0"

        # Create a result with old timestamp (beyond TTL)
        old_time = datetime.now() - timedelta(seconds=GATE_CHECK_CACHE_TTL + 10)
        result = GateResult(
            gate_name=gate_name,
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at=old_time.isoformat()
        )

        # Manually add to cache with old timestamp
        cache_key = f"{project_id}:{gate_name}"
        gate_checker._cache[cache_key] = result

        # Should return None because it's expired
        cached_result = gate_checker._get_cached_result(project_id, gate_name)
        assert cached_result is None

    def test_gate_cache_within_ttl(self, gate_checker):
        """Test that cached results are valid within TTL."""
        project_id = "test_project"
        gate_name = "gate_0"

        # Create a recent result (within TTL)
        result = GateResult(
            gate_name=gate_name,
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at=datetime.now().isoformat()
        )

        gate_checker._cache_result(project_id, gate_name, result)

        # Should return the cached result
        cached_result = gate_checker._get_cached_result(project_id, gate_name)
        assert cached_result is not None
        assert cached_result.verdict == "PASS"

    def test_clear_cache_all(self, gate_checker):
        """Test clearing all cache entries."""
        # Add multiple cache entries
        for i in range(3):
            result = GateResult(
                gate_name=f"gate_{i}",
                verdict="PASS",
                check_items=[],
                suggestions=[],
                checked_at=datetime.now().isoformat()
            )
            gate_checker._cache_result(f"project_{i}", f"gate_{i}", result)

        assert len(gate_checker._cache) == 3

        # Clear all cache
        gate_checker.clear_cache()

        assert len(gate_checker._cache) == 0

    def test_clear_cache_by_project(self, gate_checker):
        """Test clearing cache entries for a specific project."""
        project_id = "test_project"

        # Add cache entries for different projects
        for i in range(3):
            result = GateResult(
                gate_name="gate_0",
                verdict="PASS",
                check_items=[],
                suggestions=[],
                checked_at=datetime.now().isoformat()
            )
            gate_checker._cache_result(f"project_{i}", "gate_0", result)

        # Add entries for target project with different gates
        for gate in ["gate_0", "gate_1"]:
            result = GateResult(
                gate_name=gate,
                verdict="PASS",
                check_items=[],
                suggestions=[],
                checked_at=datetime.now().isoformat()
            )
            gate_checker._cache_result(project_id, gate, result)

        initial_count = len(gate_checker._cache)

        # Clear cache for specific project
        gate_checker.clear_cache(project_id=project_id)

        # Should have removed 2 entries (gate_0 and gate_1 for test_project)
        assert len(gate_checker._cache) == initial_count - 2

    def test_clear_cache_by_gate(self, gate_checker):
        """Test clearing cache entries for a specific gate across all projects."""
        gate_name = "gate_0"

        # Add cache entries for different gates
        for i in range(3):
            for gate in ["gate_0", "gate_1"]:
                result = GateResult(
                    gate_name=gate,
                    verdict="PASS",
                    check_items=[],
                    suggestions=[],
                    checked_at=datetime.now().isoformat()
                )
                gate_checker._cache_result(f"project_{i}", gate, result)

        initial_count = len(gate_checker._cache)

        # Clear cache for specific gate
        gate_checker.clear_cache(gate_name=gate_name)

        # Should have removed 3 entries (gate_0 for all 3 projects)
        assert len(gate_checker._cache) == initial_count - 3

    def test_clear_cache_by_project_and_gate(self, gate_checker):
        """Test clearing cache for a specific project and gate combination."""
        project_id = "test_project"
        gate_name = "gate_0"

        # Add multiple cache entries
        for proj in ["test_project", "other_project"]:
            for gate in ["gate_0", "gate_1"]:
                result = GateResult(
                    gate_name=gate,
                    verdict="PASS",
                    check_items=[],
                    suggestions=[],
                    checked_at=datetime.now().isoformat()
                )
                gate_checker._cache_result(proj, gate, result)

        initial_count = len(gate_checker._cache)

        # Clear cache for specific project and gate
        gate_checker.clear_cache(project_id=project_id, gate_name=gate_name)

        # Should have removed only 1 entry
        assert len(gate_checker._cache) == initial_count - 1


class TestGateCheckIntegration:
    """Integration tests for complete gate checking workflow."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_check_gate_uses_cache(self, gate_checker):
        """Test that check_gate() method uses caching."""
        project_id = "test_project"
        gate_name = "gate_0"

        # Pre-populate cache
        cached_result = GateResult(
            gate_name=gate_name,
            verdict="PASS",
            check_items=[],
            suggestions=[],
            checked_at=datetime.now().isoformat()
        )
        gate_checker._cache_result(project_id, gate_name, cached_result)

        # Mock the actual gate check methods to ensure they're not called
        with patch.object(gate_checker, 'check_gate_0') as mock_check:
            result = gate_checker.check_gate(project_id, gate_name)

            # Should return cached result without calling check_gate_0
            mock_check.assert_not_called()
            assert result.verdict == "PASS"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

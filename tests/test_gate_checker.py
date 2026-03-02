"""
Unit tests for GateChecker service.
Tests gate checking logic, caching mechanism, and gate validation.
Updated for v7 SOP gate alignment.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from app.services.gate_checker import GateChecker, GATE_CHECK_CACHE_TTL
from app.models.gate import GateResult, GateType, GateVerdict, CheckItem
from app.models.document import DocumentType
from app.models.project import Project, ProjectConfig, StepStatus


def _make_config():
    return ProjectConfig(
        topic="Test Topic",
        target_venue="NeurIPS 2026",
        research_type="ml",
        data_status="available",
        hard_constraints=["Constraint 1"],
        keywords=["keyword1", "keyword2"]
    )


def _make_project(**overrides):
    defaults = dict(project_id="test_project", project_name="Test Project", config=_make_config())
    defaults.update(overrides)
    return Project(**defaults)


def _make_gate_result(gate_type=GateType.GATE_0, verdict=GateVerdict.PASS, project_id="test_project"):
    return GateResult(
        gate_type=gate_type,
        verdict=verdict,
        check_items=[],
        passed_count=0,
        total_count=0,
        suggestions=[],
        project_id=project_id,
    )


# ── Gate 0 Tests (v7: 5 items) ──

class TestGateCheckerBasics:
    """Test suite for basic gate checker functionality."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_checker_initialization(self, gate_checker):
        """Test that GateChecker initializes correctly."""
        assert gate_checker is not None
        assert hasattr(gate_checker, '_cache')
        assert len(gate_checker._cache) == 0


class TestGate0Check:
    """Test suite for Gate 0 checks (v7: 5 items AND)."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_0_v7_all_pass(self, gate_checker):
        """Test Gate 0 with all v7 items passing."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()

            intake_doc = MagicMock()
            intake_doc.content = """# Project Intake Card

## Hard Constraints
1. Must use public datasets
2. Must complete within 6 months
3. Must target top-tier venue

## Definition of Done
1. Paper accepted at NeurIPS
2. Code released on GitHub
3. Reproducible results

## North-Star Question
How can we improve few-shot learning accuracy by 10% on standard benchmarks?
"""
            intake_doc.metadata = MagicMock()
            intake_doc.metadata.doc_type = "ProjectIntake"
            intake_doc.metadata.status = "completed"
            intake_doc.metadata.version = "1.0"

            venue_doc = MagicMock()
            venue_doc.content = "# Venue Taste Notes\n\nVenue analysis..."

            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.PROJECT_INTAKE_CARD:
                    return intake_doc
                elif doc_type == DocumentType.VENUE_TASTE_NOTES:
                    return venue_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_0(project)
            assert isinstance(result, GateResult)
            assert result.gate_type == GateType.GATE_0
            assert result.total_count == 5
            # Check all 5 v7 items present
            item_names = [item.item_name for item in result.check_items]
            assert "Target Venue Specified" in item_names
            assert "Hard Constraints >= 3" in item_names
            assert "DoD >= 3" in item_names
            assert "North-Star Question Exists" in item_names
            assert "Front-Matter Valid" in item_names
        asyncio.run(_run())

    def test_gate_0_check_with_missing_documents(self, gate_checker):
        """Test Gate 0 check when required documents are missing."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()
            mock_fm.load_document = AsyncMock(return_value=None)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_0(project)
            assert isinstance(result, GateResult)
            assert result.verdict == GateVerdict.FAIL
            assert result.total_count == 5
        asyncio.run(_run())


# ── Gate 1 Tests (v7: 8 items) ──

class TestGate1V7Check:
    """Test suite for Gate 1 checks (v7: 8 items AND, includes alignment)."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_1_v7_eight_items(self, gate_checker):
        """Test Gate 1 produces 8 check items per v7 spec."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()

            topic_doc = MagicMock()
            topic_doc.content = """# Selected Topic

## Backup
Top-2 alternative: Transfer learning approach

## Claims
1. C1: Our method improves accuracy
2. C2: Our method is efficient
3. C3: Our method generalizes
4. C4: Our method is robust
5. C5: Our method scales
6. C6: Our method is interpretable

## Non-Claims
1. NC1: We do not claim SOTA on all tasks
2. NC2: We do not address video data
3. NC3: We do not handle multi-modal
4. NC4: We do not target real-time
5. NC5: We do not claim theoretical optimality
6. NC6: We do not address privacy

## Minimal Figure Set
- Figure 1: Main architecture
- Figure 2: Comparison table
- Table 1: Ablation results
"""
            alignment_doc = MagicMock()
            alignment_doc.content = """# Topic Alignment Check

North-Star Question: covered and addressed
Core keywords present: "few-shot", "meta-learning", "benchmark" (3 keywords)
Scope: within bounded limits, clear non-claims defined
"""
            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.SELECTED_TOPIC:
                    return topic_doc
                elif doc_type == DocumentType.TOPIC_ALIGNMENT_CHECK:
                    return alignment_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_1(project)
            assert isinstance(result, GateResult)
            assert result.gate_type == GateType.GATE_1
            # v7.1: 8 core items + optional term validity items
            assert result.total_count >= 8
            item_names = [item.item_name for item in result.check_items]
            assert "Top-1 Topic Selected" in item_names
            assert "Top-2 Backup Defined" in item_names
            assert "Draft Claims >= 6" in item_names
            assert "Non-Claims >= 6" in item_names
            assert "Minimal Figure/Table Set <= 4" in item_names
            assert "North-Star Question Covered" in item_names
            assert "Core Keywords Present >= 3" in item_names
            assert "Scope Boundaries in Non-Claims" in item_names
        asyncio.run(_run())

    def test_gate_1_no_alignment_doc(self, gate_checker):
        """Test Gate 1 still has 8 items when alignment doc is missing (all alignment FAIL)."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()

            topic_doc = MagicMock()
            topic_doc.content = "# Selected Topic\nSome topic content"

            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.SELECTED_TOPIC:
                    return topic_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_1(project)
            # v7.1: 8 core items + optional term validity items
            assert result.total_count >= 8
            assert result.verdict == GateVerdict.FAIL
        asyncio.run(_run())


# ── Gate 1.5 Tests (v7: 5 items, rigor-aware) ──

class TestGate15V7Check:
    """Test suite for Gate 1.5 checks (v7: 5 items AND, rigor-aware)."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_1_5_v7_five_items(self, gate_checker):
        """Test Gate 1.5 produces 5 check items per v7 spec."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()

            kp_doc = MagicMock()
            kp_doc.content = """# Killer Prior Check

## Similar Works
1. Smith et al. (2024) - DOI: 10.1234/abc
2. Jones et al. (2024) - arXiv:2401.12345
3. Wang et al. (2023) - DOI: 10.5678/def
4. Lee et al. (2023) - DOI: 10.9012/ghi
5. Chen et al. (2024) - arXiv:2402.54321
6. Brown et al. (2023) - DOI: 10.3456/jkl
7. Kim et al. (2024) - DOI: 10.7890/mno
8. Zhang et al. (2023) - DOI: 10.1111/pqr
9. Liu et al. (2024) - arXiv:2403.11111
10. Park et al. (2023) - DOI: 10.2222/stu
11. Yang et al. (2024) - DOI: 10.3333/vwx
12. Wu et al. (2023) - DOI: 10.4444/yza
13. Zhao et al. (2024) - arXiv:2404.22222
14. Xu et al. (2023) - DOI: 10.5555/bcd
15. Sun et al. (2024) - DOI: 10.6666/efg

## Collision Map
| Prior | Claim |
|-------|-------|
| Smith et al. | C1, C3 |
| Jones et al. | C2 |

## Required Edits
1. Strengthen C1 differentiation
2. Add ablation for C3

## Verdict: PASS
"""
            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.KILLER_PRIOR_CHECK:
                    return kp_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_1_5(project)
            assert isinstance(result, GateResult)
            assert result.gate_type == GateType.GATE_1_5
            assert result.total_count == 5
            item_names = [item.item_name for item in result.check_items]
            # Check v7 items present (similar works threshold is rigor-aware)
            assert any("Similar Works" in n for n in item_names)
            assert "References Verifiable" in item_names
            assert "Collision Map Exists" in item_names
            assert "Required Edits <= 5" in item_names
            assert "Verdict is PASS" in item_names
        asyncio.run(_run())

    def test_gate_1_5_missing_doc(self, gate_checker):
        """Test Gate 1.5 fails when Killer Prior doc is missing."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()
            mock_fm.load_document = AsyncMock(return_value=None)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_1_5(project)
            assert result.verdict == GateVerdict.FAIL
        asyncio.run(_run())


# ── Gate 1.6 Tests (v7: 4 items, rigor-aware) ──

class TestGate16Check:
    """Test suite for Gate 1.6 (Reference QA) checks (v7: 4 items, rigor-aware)."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_1_6_v7_four_items(self, gate_checker):
        """Test Gate 1.6 produces 4 check items per v7 spec with rigor-aware thresholds."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()

            ref_qa_doc = MagicMock()
            ref_qa_doc.content = """# Reference QA Report

## Summary
- Total References: 30
- Valid DOIs: 29
- DOI Coverage: 97%

All unparseable references are background only, not used in key arguments.
"""
            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.REFERENCE_QA_REPORT:
                    return ref_qa_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_1_6(project)
            assert isinstance(result, GateResult)
            assert result.gate_type == GateType.GATE_1_6
            assert result.total_count == 4
            item_names = [item.item_name for item in result.check_items]
            # Check v7 items (thresholds are rigor-aware)
            assert any("Literature Matrix" in n for n in item_names)
            assert any("DOI Parseability" in n for n in item_names)
            assert "Unparseable Refs Not Critical" in item_names
            assert any("Manual Verification" in n for n in item_names)
        asyncio.run(_run())

    def test_gate_1_6_missing_doc(self, gate_checker):
        """Test Gate 1.6 fails when Reference QA doc is missing."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()
            mock_fm.load_document = AsyncMock(return_value=None)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_1_6(project)
            assert result.verdict == GateVerdict.FAIL
        asyncio.run(_run())


# ── Gate 2 Tests (v7: 7 items, rigor-aware) ──

class TestGate2V7Check:
    """Test suite for Gate 2 checks (v7: 7 items AND, rigor-aware)."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_2_v7_seven_items(self, gate_checker):
        """Test Gate 2 produces 7 check items per v7 spec."""
        async def _run():
            project = _make_project()
            mock_fm = AsyncMock()

            proposal_doc = MagicMock()
            proposal_doc.content = """# Full Proposal
Claims mapped to figure and table evidence.
Claim C1 -> Figure 1, Table 2, test T1.
"""
            eng_doc = MagicMock()
            eng_doc.content = """# Engineering Spec
## Module 1
Input: data, Output: features, Verification: unit test
## Module 2
Input: features, Output: predictions, Verification: integration test
"""
            plan_doc = MagicMock()
            plan_doc.content = """# Research Plan FROZEN

Killer Prior PASS referenced.

## Baselines
1. Baseline A: Standard CNN
2. Baseline B: ResNet-50

## Robustness Checks
1. Random seed variation
2. Data augmentation sensitivity
3. Hyperparameter sweep
4. Cross-dataset evaluation
5. Noise injection
6. Distribution shift

## Stop/Pivot Checkpoints
1. Week 2: Data quality check
2. Week 4: Baseline reproduction
3. Week 6: Main result significance
"""
            test_doc = MagicMock()
            test_doc.content = "# Test Plan\nBaseline and robustness tests defined."

            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.FULL_PROPOSAL:
                    return proposal_doc
                elif doc_type == DocumentType.ENGINEERING_SPEC:
                    return eng_doc
                elif doc_type == DocumentType.RESEARCH_PLAN_FROZEN:
                    return plan_doc
                elif doc_type == DocumentType.TEST_PLAN:
                    return test_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm

            result = await gate_checker.check_gate_2(project)
            assert isinstance(result, GateResult)
            assert result.gate_type == GateType.GATE_2
            assert result.total_count == 7
            item_names = [item.item_name for item in result.check_items]
            assert "Claims Mapped to Evidence" in item_names
            assert "Consistency Lint Passed" in item_names
            assert "Baselines >= 2" in item_names
            assert any("Robustness Checks" in n for n in item_names)
            assert "Stop/Pivot Checkpoints >= 3" in item_names
            assert "Killer Prior PASS Referenced" in item_names
            assert "Modules Have I/O + Verification" in item_names
        asyncio.run(_run())


# ── Cache Tests ──

class TestGateCacheMechanism:
    """Test suite for gate check caching."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_gate_cache_mechanism(self, gate_checker):
        """Test that gate check results are cached."""
        project_id = "test_project"
        gate_name = "gate_0"
        result = _make_gate_result()

        gate_checker._cache_result(project_id, gate_name, result)
        cached_result = gate_checker._get_cached_result(project_id, gate_name)

        assert cached_result is not None
        assert cached_result.verdict == GateVerdict.PASS

    def test_gate_cache_expiration(self, gate_checker):
        """Test that cached results expire after TTL."""
        project_id = "test_project"
        gate_name = "gate_0"
        result = _make_gate_result()

        cache_key = (project_id, gate_name)
        old_time = datetime.now() - timedelta(seconds=GATE_CHECK_CACHE_TTL + 10)
        gate_checker._cache[cache_key] = (result, old_time)

        cached_result = gate_checker._get_cached_result(project_id, gate_name)
        assert cached_result is None

    def test_gate_cache_within_ttl(self, gate_checker):
        """Test that cached results are valid within TTL."""
        project_id = "test_project"
        gate_name = "gate_0"
        result = _make_gate_result()

        gate_checker._cache_result(project_id, gate_name, result)
        cached_result = gate_checker._get_cached_result(project_id, gate_name)

        assert cached_result is not None
        assert cached_result.verdict == GateVerdict.PASS

    def test_clear_cache_all(self, gate_checker):
        """Test clearing all cache entries."""
        for i in range(3):
            gate_checker._cache_result(f"project_{i}", f"gate_{i}", _make_gate_result())

        assert len(gate_checker._cache) == 3
        gate_checker.clear_cache()
        assert len(gate_checker._cache) == 0

    def test_clear_cache_by_project(self, gate_checker):
        """Test clearing cache for a specific project."""
        for i in range(3):
            gate_checker._cache_result(f"project_{i}", "gate_0", _make_gate_result())

        gate_checker.clear_cache(project_id="project_0")
        assert len(gate_checker._cache) == 2

    def test_clear_cache_by_gate(self, gate_checker):
        """Test clearing cache for a specific gate across all projects."""
        for i in range(3):
            for gate in ["gate_0", "gate_1"]:
                gate_checker._cache_result(f"project_{i}", gate, _make_gate_result())

        initial_count = len(gate_checker._cache)
        gate_checker.clear_cache(gate_name="gate_0")
        assert len(gate_checker._cache) == initial_count - 3

    def test_clear_cache_by_project_and_gate(self, gate_checker):
        """Test clearing cache for a specific project and gate combination."""
        for proj in ["test_project", "other_project"]:
            for gate in ["gate_0", "gate_1"]:
                gate_checker._cache_result(proj, gate, _make_gate_result())

        initial_count = len(gate_checker._cache)
        gate_checker.clear_cache(project_id="test_project", gate_name="gate_0")
        assert len(gate_checker._cache) == initial_count - 1


class TestGateCheckIntegration:
    """Integration tests for complete gate checking workflow."""

    @pytest.fixture
    def gate_checker(self):
        return GateChecker()

    def test_check_gate_uses_cache(self, gate_checker):
        """Test that check_gate_0 uses caching."""
        async def _run():
            project = _make_project()
            cached_result = _make_gate_result()

            gate_checker._cache_result(project.project_id, "gate_0", cached_result)

            result = await gate_checker.check_gate_0(project)
            assert result.verdict == GateVerdict.PASS
        asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

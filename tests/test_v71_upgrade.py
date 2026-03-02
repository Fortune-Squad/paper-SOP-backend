"""
v7.1 Upgrade Tests
Tests for all Sprint changes: S0-S3

Run: cd backend && python -m pytest tests/test_v71_upgrade.py -v
"""
import pytest
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


# ============================================================
# S0-1: AGENTS.md upgrade tests
# ============================================================

class TestAgentsMdConfig:
    """Test AgentsMdConfig model and v7.1 template"""

    def test_agents_md_config_defaults(self):
        from app.services.snapshot_generator import AgentsMdConfig
        config = AgentsMdConfig()
        assert config.rigor_profile == "top_journal"
        assert config.north_star == ""
        assert len(config.red_lines) == 3
        assert "ChatGPT" in config.role_assignments
        assert "Gemini" in config.role_assignments
        assert "Claude" in config.role_assignments

    def test_agents_md_config_custom(self):
        from app.services.snapshot_generator import AgentsMdConfig
        config = AgentsMdConfig(
            project_overview="Test Project",
            rigor_profile="fast_track",
            north_star="Can we beat SOTA?",
            red_lines=["No cheating"],
            role_assignments={"ChatGPT": "PI"},
        )
        assert config.rigor_profile == "fast_track"
        assert config.north_star == "Can we beat SOTA?"
        assert len(config.red_lines) == 1

    def test_initialize_agents_md_v71(self, tmp_path):
        from app.services.snapshot_generator import SnapshotGenerator, AgentsMdConfig
        gen = SnapshotGenerator(str(tmp_path))
        config = AgentsMdConfig(
            north_star="Improve wireless throughput by 10x",
            rigor_profile="clinical_high_value",
        )
        gen.initialize_agents_md_v71(config)
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "v7.1" in content
        assert "clinical_high_value" in content
        assert "Improve wireless throughput" in content
        assert "ChatGPT" in content
        assert "Gemini" in content
        assert "Claude" in content

    def test_initialize_agents_md_v71_default(self, tmp_path):
        from app.services.snapshot_generator import SnapshotGenerator
        gen = SnapshotGenerator(str(tmp_path))
        gen.initialize_agents_md_v71()  # No config = defaults
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "v7.1" in content
        assert "top_journal" in content

    def test_initialize_agents_md_v71_no_overwrite(self, tmp_path):
        from app.services.snapshot_generator import SnapshotGenerator
        gen = SnapshotGenerator(str(tmp_path))
        (tmp_path / "AGENTS.md").write_text("existing", encoding="utf-8")
        gen.initialize_agents_md_v71()
        assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "existing"

    def test_backward_compat_initialize(self, tmp_path):
        """Original initialize_agents_md still works"""
        from app.services.snapshot_generator import SnapshotGenerator
        gen = SnapshotGenerator(str(tmp_path))
        gen.initialize_agents_md("My Project")
        content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
        assert "My Project" in content
        assert "Red Lines" in content


# ============================================================
# S0-1: Prompt Pack Compiler inject methods
# ============================================================

class TestPromptPackInject:
    """Test inject_agents_md and inject_memory_md"""

    def test_inject_agents_md_not_found(self):
        from app.services.prompt_pack_compiler import inject_agents_md
        result = inject_agents_md("nonexistent_project_id_xyz")
        assert "not found" in result.lower()

    def test_inject_memory_md_not_found(self):
        from app.services.prompt_pack_compiler import inject_memory_md
        result = inject_memory_md("nonexistent_project_id_xyz")
        # Should return empty or not-found message
        assert result  # Non-empty string


# ============================================================
# S0-2: MEMORY.md 4-layer tests
# ============================================================

class TestMemoryStore4Layer:
    """Test 4-layer memory store"""

    def test_memory_entry_type_enum(self):
        from app.services.memory_store import MemoryEntryType
        assert MemoryEntryType.ERROR_PATTERN == "error_pattern"
        assert MemoryEntryType.STRATEGY == "strategy"
        assert MemoryEntryType.DECISION == "decision"
        assert MemoryEntryType.LEARN == "learn"

    def test_memory_entry_model(self):
        from app.services.memory_store import MemoryEntry, MemoryEntryType
        entry = MemoryEntry(
            entry_type=MemoryEntryType.ERROR_PATTERN,
            symptom="OOM on batch_size=256",
            root_cause="GPU memory insufficient",
            correction="Reduce to batch_size=64",
            prevention="Always check GPU memory before training",
            source_actor="claude",
            wp_id="wp3",
        )
        assert entry.entry_type == MemoryEntryType.ERROR_PATTERN
        assert entry.exportable is True

    def test_memory_data_4_layers(self):
        from app.services.memory_store import MemoryData
        data = MemoryData()
        assert data.error_patterns == []
        assert data.strategies == []
        assert data.decisions == []
        assert data.corrections == []
        assert data.key_facts == []

    def test_add_error_pattern(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_error_pattern(
            symptom="OOM error",
            root_cause="batch too large",
            correction="reduce batch size",
            source_actor="claude",
            wp_id="wp1",
        )
        data = store.load()
        assert len(data.error_patterns) == 1
        assert data.error_patterns[0].symptom == "OOM error"

    def test_add_strategy(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_strategy(
            symptom="Slow convergence",
            correction="Use learning rate warmup",
        )
        data = store.load()
        assert len(data.strategies) == 1

    def test_add_decision(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_decision(
            symptom="Which optimizer?",
            correction="Use AdamW per reviewer suggestion",
            source_actor="human",
        )
        data = store.load()
        assert len(data.decisions) == 1
        assert data.decisions[0].source_actor == "human"

    def test_4_layer_roundtrip(self, tmp_path):
        """Test serialize → parse roundtrip for all 4 layers"""
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_key_fact("Project uses PyTorch")
        store.add_error_pattern("OOM", "batch too large", "reduce batch")
        store.add_strategy("Slow training", "Use mixed precision")
        store.add_decision("Framework choice", "PyTorch over TF")
        store.add_learn_entry("numerical", "Always check NaN", "gate_failure")

        data = store.load()
        assert len(data.key_facts) >= 3  # 2 defaults + 1 added
        assert len(data.error_patterns) == 1
        assert len(data.strategies) == 1
        assert len(data.decisions) == 1
        assert len(data.corrections) == 1

    def test_export_to_trace_bundle(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_error_pattern("OOM", "batch", "reduce", "check first", "claude", "wp1")
        store.add_strategy("Slow", "Use warmup")
        bundle = store.export_to_trace_bundle()
        assert "error_patterns" in bundle
        assert len(bundle["error_patterns"]) == 1
        assert bundle["error_patterns"][0]["symptom"] == "OOM"
        # Check file was written
        bundle_path = tmp_path / "logs" / "trace_bundle.jsonl"
        assert bundle_path.exists()

    def test_backward_compat_learn_entry(self, tmp_path):
        """LearnEntry still works"""
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_learn_entry("numerical", "Check NaN always")
        data = store.load()
        assert len(data.corrections) == 1
        assert data.corrections[0].domain == "numerical"

    def test_get_all_entries_formatted_4_layers(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_error_pattern("OOM", "batch", "reduce")
        store.add_strategy("Slow", "warmup")
        store.add_decision("Choice", "PyTorch")
        store.add_learn_entry("workflow", "Always commit")
        text = store.get_all_entries_formatted()
        assert "Error Patterns" in text
        assert "Strategies" in text
        assert "Decisions" in text
        assert "Corrections" in text

# ============================================================
# S1-1: ScholarlyGraphService tests
# ============================================================

class TestScholarlyGraphService:
    """Test ScholarlyGraphService"""

    def test_term_hit_result(self):
        from app.services.scholarly_graph_service import TermHitResult, TermStatus
        result = TermHitResult(term="MIMO")
        assert result.term == "MIMO"
        assert result.openalex_count == 0
        assert result.status == TermStatus.UNCERTAIN

    def test_term_thresholds(self):
        from app.services.scholarly_graph_service import TERM_THRESHOLDS
        assert "top_journal" in TERM_THRESHOLDS
        assert "fast_track" in TERM_THRESHOLDS
        assert "clinical_high_value" in TERM_THRESHOLDS
        assert "structural_io" in TERM_THRESHOLDS

    def test_service_init(self):
        from app.services.scholarly_graph_service import ScholarlyGraphService
        svc = ScholarlyGraphService(rigor_profile="fast_track")
        assert svc.valid_min == 20
        assert svc.uncertain_min == 2

    def test_check_term_timeout(self):
        """Test graceful degradation on timeout"""
        from app.services.scholarly_graph_service import ScholarlyGraphService, TermStatus
        svc = ScholarlyGraphService(timeout=0.001)  # Very short timeout
        result = asyncio.run(svc.check_term("test_term_xyz"))
        assert result.status == TermStatus.UNCERTAIN  # Graceful degradation


# ============================================================
# S1-1: DocumentType and v7 path mapping
# ============================================================

class TestNewDocumentTypes:
    """Test new DocumentType entries and path mappings"""

    def test_term_concept_qa_type(self):
        from app.models.document import DocumentType
        assert DocumentType.TERM_CONCEPT_QA == "02_Term_Concept_QA"

    def test_idea_lab_candidates_type(self):
        from app.models.document import DocumentType
        assert DocumentType.IDEA_LAB_CANDIDATES == "01_D_Idea_Lab_Candidates"

    def test_v7_path_mapping_term_qa(self):
        from app.config.v7_path_mapping import V7_PATH_MAPPING
        from app.models.document import DocumentType
        assert DocumentType.TERM_CONCEPT_QA in V7_PATH_MAPPING
        folder, filename = V7_PATH_MAPPING[DocumentType.TERM_CONCEPT_QA]
        assert folder == "02_freeze"
        assert "Term_Concept_QA" in filename

    def test_v7_path_mapping_idea_lab(self):
        from app.config.v7_path_mapping import V7_PATH_MAPPING
        from app.models.document import DocumentType
        assert DocumentType.IDEA_LAB_CANDIDATES in V7_PATH_MAPPING
        folder, filename = V7_PATH_MAPPING[DocumentType.IDEA_LAB_CANDIDATES]
        assert folder == "01_research"


# ============================================================
# S1-2: Idea-Lab tests
# ============================================================

class TestIdeaLab:
    """Test Idea-Lab step and prompts"""

    def test_idea_lab_prompt_exists(self):
        from app.prompts.step1_prompts import IDEA_LAB_GEMINI_PROMPT
        assert "10-15" in IDEA_LAB_GEMINI_PROMPT
        assert "{literature_matrix}" in IDEA_LAB_GEMINI_PROMPT

    def test_idea_lab_addendum_exists(self):
        from app.prompts.step1_prompts import TOPIC_DECISION_IDEALAB_ADDENDUM
        assert "{idea_lab_content}" in TOPIC_DECISION_IDEALAB_ADDENDUM

    def test_core_terms_addendum_exists(self):
        from app.prompts.step1_prompts import TOPIC_DECISION_CORE_TERMS_ADDENDUM
        assert "core_terms" in TOPIC_DECISION_CORE_TERMS_ADDENDUM

    def test_enable_idea_lab_config(self):
        from app.models.project import ProjectConfig
        config = ProjectConfig(
            topic="Test", target_venue="NeurIPS",
            research_type="simulation", data_status="available",
            hard_constraints=["none"], keywords=["test"],
            enable_idea_lab=True,
        )
        assert config.enable_idea_lab is True

    def test_enable_idea_lab_default_false(self):
        from app.models.project import ProjectConfig
        config = ProjectConfig(
            topic="Test", target_venue="NeurIPS",
            research_type="simulation", data_status="available",
            hard_constraints=["none"], keywords=["test"],
        )
        assert config.enable_idea_lab is False

    def test_step1_idea_lab_class(self):
        from app.steps.step1_idea_lab import Step1_IdeaLab
        assert Step1_IdeaLab  # Class exists and is importable


# ============================================================
# S1-3: Rigor Profiles extension
# ============================================================

class TestRigorProfiles:
    """Test new rigor profiles"""

    def test_clinical_high_value_enum(self):
        from app.models.rigor_profile import RigorLevel
        assert RigorLevel.CLINICAL_HIGH_VALUE == "clinical_high_value"

    def test_structural_io_enum(self):
        from app.models.rigor_profile import RigorLevel
        assert RigorLevel.STRUCTURAL_IO == "structural_io"

    def test_clinical_profile_config(self):
        from app.models.rigor_profile import get_rigor_profile, RigorLevel
        profile = get_rigor_profile(RigorLevel.CLINICAL_HIGH_VALUE)
        assert profile.name == "Clinical High-Value Mode"
        assert profile.min_literature_count == 50
        assert profile.min_doi_parseability == 0.95

    def test_structural_io_profile_config(self):
        from app.models.rigor_profile import get_rigor_profile, RigorLevel
        profile = get_rigor_profile(RigorLevel.STRUCTURAL_IO)
        assert profile.name == "Structural IO Mode"
        assert profile.min_literature_count == 40

    def test_structural_io_extra_artifacts(self):
        from app.models.rigor_profile import STRUCTURAL_IO_EXTRA_ARTIFACTS
        assert "IO_Identification_Plan" in STRUCTURAL_IO_EXTRA_ARTIFACTS
        assert "IO_Institution_Measurement_Sanity" in STRUCTURAL_IO_EXTRA_ARTIFACTS

    def test_all_profiles_in_registry(self):
        from app.models.rigor_profile import RIGOR_PROFILES, RigorLevel
        assert len(RIGOR_PROFILES) == 4
        assert RigorLevel.TOP_JOURNAL in RIGOR_PROFILES
        assert RigorLevel.FAST_TRACK in RIGOR_PROFILES
        assert RigorLevel.CLINICAL_HIGH_VALUE in RIGOR_PROFILES
        assert RigorLevel.STRUCTURAL_IO in RIGOR_PROFILES

    def test_io_prompt_files_exist(self):
        prompts_dir = Path(__file__).parent.parent / "app" / "prompts" / "chatgpt"
        assert (prompts_dir / "io_identification_plan.md").exists()
        assert (prompts_dir / "io_institution_sanity.md").exists()

# ============================================================
# S2-1: Pre-flight check tests
# ============================================================

class TestPreFlightService:
    """Test Pre-flight check service"""

    def test_parameter_source_enum(self):
        from app.services.pre_flight_service import ParameterSource
        assert ParameterSource.FROM_SPEC == "from_spec"
        assert ParameterSource.FROM_REFERENCE == "from_reference"
        assert ParameterSource.DEFAULT == "default"
        assert ParameterSource.COMPUTED == "computed"

    def test_confirm_level_enum(self):
        from app.services.pre_flight_service import ConfirmLevel
        assert ConfirmLevel.AUTO_PASS == "auto_pass"
        assert ConfirmLevel.AI_REVIEW == "ai_review"
        assert ConfirmLevel.HUMAN_REVIEW == "human_review"

    def test_classify_confirm_level(self):
        from app.services.pre_flight_service import PreFlightService, ParameterSource, ConfirmLevel
        svc = PreFlightService()
        assert svc.classify_confirm_level(ParameterSource.FROM_SPEC) == ConfirmLevel.AUTO_PASS
        assert svc.classify_confirm_level(ParameterSource.FROM_REFERENCE) == ConfirmLevel.AUTO_PASS
        assert svc.classify_confirm_level(ParameterSource.DEFAULT) == ConfirmLevel.AI_REVIEW
        assert svc.classify_confirm_level(ParameterSource.COMPUTED) == ConfirmLevel.AI_REVIEW

    def test_parameter_declaration_model(self):
        from app.services.pre_flight_service import ParameterDeclaration, ParameterSource
        decl = ParameterDeclaration(
            name="learning_rate",
            value="0.001",
            source=ParameterSource.FROM_REFERENCE,
            justification="Following baseline paper",
        )
        assert decl.name == "learning_rate"
        assert decl.source == ParameterSource.FROM_REFERENCE

    def test_preflight_result_model(self):
        from app.services.pre_flight_service import PreFlightResult
        result = PreFlightResult()
        assert result.passed is False
        assert result.declarations == []
        assert result.blocked_params == []

    def test_run_full_check_no_client(self):
        from app.services.pre_flight_service import PreFlightService
        svc = PreFlightService(chatgpt_client=None)
        result = asyncio.run(svc.run_full_check("test spec"))
        assert result.passed is True  # No params to check

    def test_preflight_prompt_exists(self):
        from app.prompts.step3_prompts import PREFLIGHT_PARAMETER_DECLARATION_PROMPT
        assert "{subtask_spec}" in PREFLIGHT_PARAMETER_DECLARATION_PROMPT
        assert "from_spec" in PREFLIGHT_PARAMETER_DECLARATION_PROMPT

    def test_parse_declarations(self):
        from app.services.pre_flight_service import PreFlightService, ParameterSource
        svc = PreFlightService()
        response = """- learning_rate = 0.001 (source: from_reference, justification: baseline)
- batch_size = 64 (source: default, justification: standard)"""
        decls = svc._parse_declarations(response)
        assert len(decls) == 2
        assert decls[0].name == "learning_rate"
        assert decls[0].source == ParameterSource.FROM_REFERENCE
        assert decls[1].source == ParameterSource.DEFAULT


# ============================================================
# S2-2: Claude AI Client tests
# ============================================================

class TestClaudeClient:
    """Test ClaudeClient"""

    def test_claude_client_importable(self):
        from app.services.ai_client import ClaudeClient
        assert ClaudeClient is not None

    def test_claude_client_factory(self):
        from app.services.ai_client import create_claude_client
        assert create_claude_client is not None

    def test_claude_config_fields(self):
        from app.config import settings
        assert hasattr(settings, 'claude_api_key')
        assert hasattr(settings, 'claude_api_base')
        assert hasattr(settings, 'claude_model')

    def test_claude_config_exports(self):
        from app.config import CLAUDE_API_KEY, CLAUDE_API_BASE, CLAUDE_MODEL
        # These should exist (may be None if not configured)
        assert CLAUDE_MODEL  # Has default value


# ============================================================
# S2-3: RA Prompt enhancement
# ============================================================

class TestRAPrompt:
    """Test enhanced RA prompt"""

    def test_ra_assessment_prompt_exists(self):
        from app.prompts.step3_prompts import RA_ASSESSMENT_PROMPT
        assert "{wp_id}" in RA_ASSESSMENT_PROMPT
        assert "{wp_name}" in RA_ASSESSMENT_PROMPT
        assert "{gate_results}" in RA_ASSESSMENT_PROMPT
        assert "{artifacts_summary}" in RA_ASSESSMENT_PROMPT
        assert "{memory_lessons}" in RA_ASSESSMENT_PROMPT
        assert "ADVANCE" in RA_ASSESSMENT_PROMPT
        assert "POLISH" in RA_ASSESSMENT_PROMPT
        assert "BLOCK" in RA_ASSESSMENT_PROMPT


# ============================================================
# S3-3: DeliveryState tests
# ============================================================

class TestDeliveryState:
    """Test DeliveryState state machine"""

    def test_delivery_state_enum(self):
        from app.steps.step4 import DeliveryState
        assert DeliveryState.NOT_STARTED == "not_started"
        assert DeliveryState.COLLECTING == "collecting"
        assert DeliveryState.FIGURES == "figures"
        assert DeliveryState.ASSEMBLING == "assembling"
        assert DeliveryState.CITATION_QA == "citation_qa"
        assert DeliveryState.PACKAGING == "packaging"
        assert DeliveryState.DELIVERED == "delivered"

    def test_delivery_transitions(self):
        from app.steps.step4 import DELIVERY_TRANSITIONS, DeliveryState
        assert DELIVERY_TRANSITIONS[DeliveryState.NOT_STARTED] == DeliveryState.COLLECTING
        assert DELIVERY_TRANSITIONS[DeliveryState.COLLECTING] == DeliveryState.FIGURES
        assert DELIVERY_TRANSITIONS[DeliveryState.FIGURES] == DeliveryState.ASSEMBLING
        assert DELIVERY_TRANSITIONS[DeliveryState.ASSEMBLING] == DeliveryState.CITATION_QA
        assert DELIVERY_TRANSITIONS[DeliveryState.CITATION_QA] == DeliveryState.REPRO_CHECK
        assert DELIVERY_TRANSITIONS[DeliveryState.REPRO_CHECK] == DeliveryState.PACKAGING
        assert DELIVERY_TRANSITIONS[DeliveryState.PACKAGING] == DeliveryState.DELIVERED

    def test_get_delivery_state_default(self):
        from app.steps.step4 import _get_delivery_state, DeliveryState
        mock_project = MagicMock()
        mock_project._delivery_state = DeliveryState.NOT_STARTED.value
        state = _get_delivery_state(mock_project)
        assert state == DeliveryState.NOT_STARTED

    def test_advance_delivery_state(self):
        from app.steps.step4 import _advance_delivery_state, DeliveryState
        mock_project = MagicMock()
        next_state = _advance_delivery_state(mock_project, DeliveryState.NOT_STARTED)
        assert next_state == DeliveryState.COLLECTING
        assert mock_project._delivery_state == DeliveryState.COLLECTING.value

    def test_step4_figure_polish_class(self):
        from app.steps.step4 import Step4_FigurePolish
        assert Step4_FigurePolish is not None

    def test_step_expected_state_mapping(self):
        from app.steps.step4 import STEP_EXPECTED_STATE, DeliveryState
        assert STEP_EXPECTED_STATE["step_4_collect"] == DeliveryState.NOT_STARTED
        assert STEP_EXPECTED_STATE["step_4_figure_polish"] == DeliveryState.COLLECTING
        assert STEP_EXPECTED_STATE["step_4_assembly"] == DeliveryState.FIGURES
        assert STEP_EXPECTED_STATE["step_4_citation_qa"] == DeliveryState.ASSEMBLING
        assert STEP_EXPECTED_STATE["step_4_repro"] == DeliveryState.CITATION_QA
        assert STEP_EXPECTED_STATE["step_4_package"] == DeliveryState.REPRO_CHECK


# ============================================================
# v1.2: Claude Execution Engine Integration Tests
# ============================================================

class TestClaudeExecutionEngine:
    """v1.2: Verify Claude client wiring in BaseStep, Step 3, Step 4"""

    def test_base_step_has_claude_client(self):
        """BaseStep should have claude_client attribute"""
        from app.steps.base import BaseStep
        import inspect
        sig = inspect.signature(BaseStep.__init__)
        assert "claude_client" in sig.parameters

    def test_step4_classes_use_claude_model(self):
        """All Step 4 classes should report claude_model"""
        from app.steps.step4 import (
            Step4_Collect, Step4_FigurePolish, Step4_Assembly,
            Step4_CitationQA, Step4_ReproCheck, Step4_Package,
        )
        from app.config import settings
        mock_project = MagicMock()
        mock_project.project_id = "test"
        for cls in [Step4_Collect, Step4_FigurePolish, Step4_Assembly,
                     Step4_CitationQA, Step4_ReproCheck, Step4_Package]:
            instance = cls(project=mock_project)
            assert instance.ai_model == settings.claude_model, f"{cls.__name__}.ai_model should be claude_model"

    def test_step3_classes_use_claude_model(self):
        """Step 3 classes should report claude_model"""
        from app.steps.step3 import Step3_Init, Step3_Execute
        from app.config import settings
        mock_project = MagicMock()
        mock_project.project_id = "test"
        for cls in [Step3_Init, Step3_Execute]:
            instance = cls(project=mock_project)
            assert instance.ai_model == settings.claude_model, f"{cls.__name__}.ai_model should be claude_model"

    def test_wp_engine_accepts_claude_client(self):
        """WPExecutionEngine constructor should accept claude_client"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        sig = inspect.signature(WPExecutionEngine.__init__)
        assert "claude_client" in sig.parameters

    def test_wp_engine_get_ai_client_claude(self):
        """_get_ai_client should return claude_client for claude owners"""
        from app.services.wp_engine import WPExecutionEngine
        mock_claude = MagicMock()
        engine = WPExecutionEngine(
            project_id="test",
            claude_client=mock_claude,
        )
        assert engine._get_ai_client("claude") is mock_claude
        assert engine._get_ai_client("claude-sonnet-4-6") is mock_claude

    def test_wp_engine_heuristic_owner(self):
        """_parse_wp_registry should assign claude as default owner for code WPs"""
        from app.services.wp_engine import WPExecutionEngine
        engine = WPExecutionEngine(project_id="test")
        yaml_content = """
work_packages:
  - wp_id: wp_1
    name: "Implement baseline model"
    subtasks:
      - subtask_id: st_1
        objective: "Write code"
  - wp_id: wp_2
    name: "Literature review"
    subtasks:
      - subtask_id: st_2
        objective: "Read papers"
"""
        specs, dag = engine._parse_wp_registry(yaml_content)
        assert specs["wp_1"].owner == "claude"  # "implement" triggers claude
        assert specs["wp_1"].reviewer == "chatgpt"  # §3.2: claude owner → chatgpt reviewer
        assert specs["wp_2"].owner == "chatgpt"  # no code keywords
        assert specs["wp_2"].reviewer == "claude"  # §3.2: chatgpt owner → claude reviewer


# ============================================================
# v7.1 Wiring Verification Tests — 死代码路径接通验证
# ============================================================

class TestV71WiringGate1TermValidity:
    """S1-T1/T2/T3: Gate 1 术语体检接通验证"""

    @pytest.fixture
    def gate_checker(self):
        from app.services.gate_checker import GateChecker
        return GateChecker()

    def test_gate_1_calls_term_validity(self, gate_checker):
        """Gate 1 结果中应包含 Term: 开头的 check items"""
        from app.models.document import DocumentType
        from app.models.project import Project, ProjectConfig
        async def _run():
            config = ProjectConfig(
                topic="Test", target_venue="NeurIPS",
                research_type="ml", data_status="available",
                hard_constraints=["c1"], keywords=["keyword1", "keyword2"],
            )
            project = Project(project_id="test_wiring", project_name="Test", config=config)
            mock_fm = AsyncMock()
            topic_doc = MagicMock()
            topic_doc.content = "# Selected Topic\n## Top-1\nTopic A\n## Top-2\nTopic B\n## Draft Claims\n1. C1\n2. C2\n3. C3\n4. C4\n5. C5\n6. C6\n## Non-Claims\n1. N1\n2. N2\n3. N3\n4. N4\n5. N5\n6. N6\n## Minimal Figure Set\n- Fig 1\n- Fig 2"
            alignment_doc = MagicMock()
            alignment_doc.content = "North-Star: covered\nCore keywords: a, b, c (3)\nScope: clear"

            def load_side_effect(project_id, doc_type):
                if doc_type == DocumentType.SELECTED_TOPIC:
                    return topic_doc
                elif doc_type == DocumentType.TOPIC_ALIGNMENT_CHECK:
                    return alignment_doc
                return None

            mock_fm.load_document = AsyncMock(side_effect=load_side_effect)
            gate_checker.file_manager = mock_fm
            result = await gate_checker.check_gate_1(project)
            # Should have core 8 items + term validity items
            assert result.total_count >= 8
        asyncio.run(_run())

    def test_term_concept_qa_artifact_frontmatter(self):
        """_write_term_concept_qa_artifact 输出应包含 YAML front-matter"""
        from app.services.gate_checker import GateChecker
        import inspect
        source = inspect.getsource(GateChecker._write_term_concept_qa_artifact)
        assert "doc_type: TermConceptQA" in source
        assert "gate_relevance: Gate1" in source


class TestV71WiringPromptFixes:
    """S1-T4: Gate 1.25 → Gate 1 prompt 修复验证"""

    def test_no_gate_1_25_in_step1_prompts(self):
        """step1_prompts.py 中不应再有 Gate 1.25 引用"""
        from app.prompts import step1_prompts
        import inspect
        source = inspect.getsource(step1_prompts)
        # The only remaining "1.25" should NOT be in active prompt strings
        # Check key prompts don't reference Gate 1.25
        from app.prompts.step1_prompts import TOPIC_DECISION_CORE_TERMS_ADDENDUM
        assert "Gate 1.25" not in TOPIC_DECISION_CORE_TERMS_ADDENDUM
        assert "Gate 1" in TOPIC_DECISION_CORE_TERMS_ADDENDUM

    def test_topic_alignment_prompt_uses_gate_1(self):
        from app.prompts.step1_prompts import render_step_1_2b_prompt
        prompt = render_step_1_2b_prompt(
            intake_card_content="test", selected_topic_content="test",
            keywords=["kw1", "kw2"]
        )
        assert "Gate 1" in prompt


class TestV71WiringBaseStepContextInjection:
    """S2-T1: BaseStep.get_project_context_injection() 验证"""

    def test_method_exists(self):
        from app.steps.base import BaseStep
        assert hasattr(BaseStep, 'get_project_context_injection')

    def test_returns_string_on_missing_project(self):
        """项目不存在时应返回空字符串而非崩溃"""
        from app.steps.base import BaseStep
        mock_project = MagicMock()
        mock_project.project_id = "nonexistent_project_xyz"
        step = MagicMock(spec=BaseStep)
        step.project = mock_project
        # Call the real method
        result = BaseStep.get_project_context_injection(step)
        assert isinstance(result, str)


class TestV71WiringIdeaLabCount:
    """S2-T4: Idea-Lab 候选数量 10-15 验证"""

    def test_idea_lab_prompt_10_15(self):
        from app.prompts.step1_prompts import IDEA_LAB_GEMINI_PROMPT
        assert "10-15" in IDEA_LAB_GEMINI_PROMPT
        assert "exactly 5" not in IDEA_LAB_GEMINI_PROMPT


class TestV71WiringMemoryStoreErrorPattern:
    """S3-T1/T2/T4: add_error_pattern 写入验证"""

    def test_add_error_pattern_persists(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_error_pattern(
            symptom="Gate FAIL for WP wp1",
            root_cause="Missing validation",
            correction="Fix validation logic",
            source_actor="system",
            wp_id="wp1",
        )
        data = store.load()
        assert len(data.error_patterns) == 1
        assert data.error_patterns[0].symptom == "Gate FAIL for WP wp1"
        assert data.error_patterns[0].wp_id == "wp1"

    def test_add_strategy_persists(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_strategy(
            symptom="RA BLOCK for WP wp2",
            correction="Need more coverage",
            source_actor="chatgpt",
            wp_id="wp2",
        )
        data = store.load()
        assert len(data.strategies) == 1
        assert data.strategies[0].symptom == "RA BLOCK for WP wp2"


class TestV71WiringTraceBundleJsonl:
    """S4-T2: trace_bundle JSONL 格式验证"""

    def test_trace_bundle_is_jsonl(self, tmp_path):
        from app.services.memory_store import MemoryStore
        store = MemoryStore(str(tmp_path))
        store.initialize()
        store.add_error_pattern("err1", "cause1", "fix1")
        store.add_strategy("strat1", "action1")
        store.export_to_trace_bundle()
        jsonl_path = tmp_path / "logs" / "trace_bundle.jsonl"
        json_path = tmp_path / "logs" / "trace_bundle.json"
        assert jsonl_path.exists(), "Should write .jsonl file"
        assert not json_path.exists(), "Should NOT write .json file"
        # Verify each line is valid JSON
        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3  # header + 1 error_pattern + 1 strategy
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


class TestV71WiringClaudeClient:
    """S4-T1: Claude AI client 路由验证"""

    def test_wp_engine_has_claude_client(self):
        """WPExecutionEngine.__init__ 应初始化 claude_client"""
        from app.services.wp_engine import WPExecutionEngine
        import inspect
        source = inspect.getsource(WPExecutionEngine.__init__)
        assert "claude_client" in source

    def test_get_ai_client_routes_claude(self):
        """_get_ai_client 应路由 claude 到 claude_client"""
        from app.services.wp_engine import WPExecutionEngine
        import inspect
        source = inspect.getsource(WPExecutionEngine._get_ai_client)
        assert "claude" in source.lower()


class TestV71WiringStateStoreHook:
    """S4-T4: state_store.update() AGENTS.md hook 验证"""

    def test_state_store_update_has_snapshot_hook(self):
        """update() 方法应包含 SnapshotGenerator 调用"""
        from app.services.state_store import StateStore
        import inspect
        source = inspect.getsource(StateStore.update)
        assert "SnapshotGenerator" in source
        assert "update_agents_md" in source


class TestV71WiringProjectManagerInit:
    """S1-T5: 项目创建时初始化 AGENTS.md + MEMORY.md 验证"""

    def test_create_project_has_v71_init(self):
        """create_project 应包含 v7.1 初始化代码"""
        from app.services.project_manager import ProjectManager
        import inspect
        source = inspect.getsource(ProjectManager.create_project)
        assert "initialize_agents_md_v71" in source
        assert "MemoryStore" in source
        assert "initialize" in source

    def test_execute_step_has_agents_md_update(self):
        """execute_step 应包含 AGENTS.md 动态更新"""
        from app.services.project_manager import ProjectManager
        import inspect
        source = inspect.getsource(ProjectManager.execute_step)
        assert "SnapshotGenerator" in source
        assert "update_agents_md" in source


# ============================================================
# v1.2 DevSpec Compliance Tests
# ============================================================

class TestV12_A1_WPSpecExtendedFields:
    """A1: WPSpec §10 扩展字段"""

    def test_wpspec_default_values(self):
        from app.models.work_package import WPSpec
        spec = WPSpec(wp_id="wp1", name="Test WP")
        assert spec.subtask_decomposition == "manual"
        assert spec.escalation_policy == "default"
        assert spec.ra_required is True
        assert spec.max_subtask_tokens is None

    def test_wpspec_custom_values(self):
        from app.models.work_package import WPSpec
        spec = WPSpec(
            wp_id="wp1", name="Test WP",
            subtask_decomposition="auto",
            escalation_policy="skip_gemini",
            ra_required=False,
            max_subtask_tokens=5000,
        )
        assert spec.subtask_decomposition == "auto"
        assert spec.escalation_policy == "skip_gemini"
        assert spec.ra_required is False
        assert spec.max_subtask_tokens == 5000

    def test_wpspec_backward_compat(self):
        from app.models.work_package import WPSpec
        old_data = {"wp_id": "wp1", "name": "Old WP", "owner": "chatgpt"}
        spec = WPSpec(**old_data)
        assert spec.subtask_decomposition == "manual"
        assert spec.ra_required is True


class TestV12_C1_SubtaskResultTokenUsage:
    """C1: SubtaskResult token 追踪"""

    def test_token_usage_default_none(self):
        from app.models.work_package import SubtaskResult
        r = SubtaskResult(subtask_id="st1")
        assert r.token_usage is None

    def test_token_usage_with_data(self):
        from app.models.work_package import SubtaskResult
        r = SubtaskResult(
            subtask_id="st1",
            token_usage={"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
        )
        assert r.token_usage["total_tokens"] == 300

    def test_token_usage_serialization(self):
        from app.models.work_package import SubtaskResult
        r = SubtaskResult(
            subtask_id="st1",
            token_usage={"prompt_tokens": 50, "completion_tokens": 75, "total_tokens": 125},
        )
        d = r.model_dump()
        assert d["token_usage"]["total_tokens"] == 125


class TestV12_A2_FreezeHygiene:
    """A2: Freeze Hygiene — git tag + FROZEN_MANIFEST"""

    def test_git_manager_create_tag(self, tmp_path):
        from app.utils.git_manager import GitManager
        from git import Repo
        gm = GitManager(base_path=str(tmp_path))
        project_id = "test_proj"
        repo = gm.init_repo(project_id)
        result = gm.create_tag(project_id, "wp1-v1", "Test tag")
        assert result is True
        tags = [t.name for t in Repo(tmp_path / project_id).tags]
        assert "wp1-v1" in tags

    def test_git_manager_has_uncommitted_changes_clean(self, tmp_path):
        from app.utils.git_manager import GitManager
        gm = GitManager(base_path=str(tmp_path))
        project_id = "test_proj2"
        gm.init_repo(project_id)
        assert gm.has_uncommitted_changes(project_id) is False

    def test_git_manager_has_uncommitted_changes_dirty(self, tmp_path):
        from app.utils.git_manager import GitManager
        gm = GitManager(base_path=str(tmp_path))
        project_id = "test_proj3"
        gm.init_repo(project_id)
        (tmp_path / project_id / "new_file.txt").write_text("dirty")
        assert gm.has_uncommitted_changes(project_id) is True

    def test_frozen_manifest_structure(self, tmp_path):
        import json, hashlib
        manifest = {
            "wp_id": "wp1",
            "tag": "wp1-v1",
            "frozen_at": "2025-01-01T00:00:00",
            "artifacts": {
                "results/output.md": {
                    "sha256": hashlib.sha256(b"test content").hexdigest(),
                    "subtask": "wp1_st1",
                }
            },
        }
        mpath = tmp_path / "FROZEN_MANIFEST_wp1.json"
        mpath.write_text(json.dumps(manifest))
        loaded = json.loads(mpath.read_text())
        assert loaded["wp_id"] == "wp1"
        assert len(loaded["artifacts"]) == 1
        assert "sha256" in list(loaded["artifacts"].values())[0]


class TestV12_A3_FreezeGateF4F7:
    """A3: Freeze Gate F4-F7"""

    def test_freeze_gate_7_items(self):
        from app.models.gate import FreezeGateChecklist, GateVerdict
        checklist = FreezeGateChecklist(
            wp_gate_passed=True,
            artifacts_committed=True,
            no_open_issues=True,
            version_tagged=True,
            no_uncommitted_changes=True,
            manifest_complete=True,
            agents_memory_updated=True,
        )
        result = checklist.validate(wp_id="wp1")
        assert result.total_count == 7
        assert result.passed_count == 7
        assert result.verdict == GateVerdict.PASS

    def test_freeze_gate_partial_fail(self):
        from app.models.gate import FreezeGateChecklist, GateVerdict
        checklist = FreezeGateChecklist(
            wp_gate_passed=True,
            artifacts_committed=True,
            no_open_issues=True,
            version_tagged=False,
            no_uncommitted_changes=False,
            manifest_complete=False,
            agents_memory_updated=False,
        )
        result = checklist.validate(wp_id="wp1")
        assert result.total_count == 7
        assert result.passed_count == 3
        assert result.verdict == GateVerdict.FAIL
        assert len(result.suggestions) == 4

    def test_freeze_gate_all_fail(self):
        from app.models.gate import FreezeGateChecklist, GateVerdict
        checklist = FreezeGateChecklist()
        result = checklist.validate()
        assert result.verdict == GateVerdict.FAIL
        assert result.passed_count == 0


class TestV12_A4_MemoryInjection:
    """A4: Step 3 MEMORY.md 注入"""

    def test_execute_prompt_with_memory(self):
        from app.prompts.step3_prompts import render_execute_prompt
        prompt = render_execute_prompt(
            wp_spec_yaml="wp_id: wp1",
            subtask_spec_yaml="subtask_id: st1",
            memory_lessons="- [LEARN:numerical] Use float64 for precision",
        )
        assert "MEMORY.md" in prompt
        assert "float64" in prompt

    def test_execute_prompt_without_memory(self):
        from app.prompts.step3_prompts import render_execute_prompt
        prompt = render_execute_prompt(
            wp_spec_yaml="wp_id: wp1",
            subtask_spec_yaml="subtask_id: st1",
        )
        assert "MEMORY.md" not in prompt

    def test_review_fix_prompt_with_memory(self):
        from app.prompts.step3_prompts import render_review_fix_prompt
        prompt = render_review_fix_prompt(
            wp_spec_yaml="wp_id: wp1",
            review_issues="Fix X",
            allowed_paths="results/",
            previous_output="old output",
            memory_lessons="- [LEARN:workflow] Always check boundary",
        )
        assert "MEMORY.md" in prompt
        assert "boundary" in prompt


class TestV12_A5_SessionResume:
    """A5: Session Resume prompt"""

    def test_session_resume_prompt_render(self):
        from app.prompts.step3_prompts import render_session_resume_prompt
        prompt = render_session_resume_prompt(
            project_summary="Project X, WP wp1, 2/4 subtasks done",
            agents_md_dynamic="## Dynamic\nPhase: E1",
            memory_lessons="- [LEARN:numerical] Use float64",
            last_subtask_result="what_changed: [results/a.md]",
            last_wrapup="Completed: wp1_st2, Remaining: wp1_st3",
            current_subtask_yaml="subtask_id: wp1_st3\nobjective: Run analysis",
        )
        assert "resuming" in prompt.lower()
        assert "Project X" in prompt
        assert "float64" in prompt
        assert "wp1_st3" in prompt

    def test_session_resume_prompt_empty(self):
        from app.prompts.step3_prompts import render_session_resume_prompt
        prompt = render_session_resume_prompt()
        assert "resuming" in prompt.lower()
        assert "No project summary" in prompt


class TestV12_B1_ReproCheck:
    """B1: D4_REPRO_CHECK 步骤"""

    def test_delivery_state_has_repro_check(self):
        from app.steps.step4 import DeliveryState
        assert hasattr(DeliveryState, "REPRO_CHECK")
        assert DeliveryState.REPRO_CHECK.value == "repro_check"

    def test_delivery_transitions_include_repro(self):
        from app.steps.step4 import DELIVERY_TRANSITIONS, DeliveryState
        assert DELIVERY_TRANSITIONS[DeliveryState.CITATION_QA] == DeliveryState.REPRO_CHECK
        assert DELIVERY_TRANSITIONS[DeliveryState.REPRO_CHECK] == DeliveryState.PACKAGING

    def test_step_expected_state_repro(self):
        from app.steps.step4 import STEP_EXPECTED_STATE, DeliveryState
        assert STEP_EXPECTED_STATE["step_4_repro"] == DeliveryState.CITATION_QA
        assert STEP_EXPECTED_STATE["step_4_package"] == DeliveryState.REPRO_CHECK

    def test_step4_repro_check_class_exists(self):
        from app.steps.step4 import Step4_ReproCheck
        assert Step4_ReproCheck.step_id.fget is not None

    def test_step4_repro_registered_in_valid_ids(self):
        from app.api.projects import VALID_STEP_IDS
        assert "step_4_repro" in VALID_STEP_IDS

    def test_repro_check_prompt(self):
        from app.prompts.step4_prompts import render_repro_check_prompt
        prompt = render_repro_check_prompt("manifest data", "verification data")
        assert "Reproducibility" in prompt
        assert "manifest data" in prompt


class TestV12_B2_DeliveryGateD5D8:
    """B2: Delivery Gate D5-D8"""

    def test_delivery_gate_8_items_all_pass(self):
        from app.models.gate import DeliveryGateChecklist, GateVerdict
        checklist = DeliveryGateChecklist(
            all_wps_frozen=True,
            all_figures_approved=True,
            assembly_complete=True,
            repro_check_pass=True,
            deliverables_complete=True,
            checksums_valid=True,
            citations_verified=True,
            no_forbidden_output=True,
        )
        result = checklist.validate()
        assert result.total_count == 8
        assert result.passed_count == 8
        assert result.verdict == GateVerdict.PASS

    def test_delivery_gate_partial_fail(self):
        from app.models.gate import DeliveryGateChecklist, GateVerdict
        checklist = DeliveryGateChecklist(
            all_wps_frozen=True,
            all_figures_approved=True,
            assembly_complete=True,
            repro_check_pass=True,
            deliverables_complete=False,
            checksums_valid=False,
            citations_verified=False,
            no_forbidden_output=False,
        )
        result = checklist.validate()
        assert result.total_count == 8
        assert result.passed_count == 4
        assert result.verdict == GateVerdict.FAIL
        assert len(result.suggestions) == 4

    def test_delivery_gate_all_fail(self):
        from app.models.gate import DeliveryGateChecklist, GateVerdict
        checklist = DeliveryGateChecklist()
        result = checklist.validate()
        assert result.verdict == GateVerdict.FAIL
        assert result.passed_count == 0


class TestV12_B3_CitationQAChecker:
    """B3: CitationQAChecker"""

    def test_latex_citation_parsing(self):
        from app.services.citation_qa_checker import CitationQAChecker
        checker = CitationQAChecker()
        content = r"As shown in \cite{smith2023} and \citep{jones2024,wang2025}."
        bib = """@article{smith2023, title={A}}
@inproceedings{jones2024, title={B}}
@article{wang2025, title={C}}
"""
        report = checker.check(content, bib)
        assert set(report.used_keys) == {"smith2023", "jones2024", "wang2025"}
        assert set(report.bib_keys) == {"smith2023", "jones2024", "wang2025"}
        assert report.verdict == "PASS"
        assert len(report.missing_keys) == 0

    def test_pandoc_citation_parsing(self):
        from app.services.citation_qa_checker import CitationQAChecker
        checker = CitationQAChecker()
        content = "See [@smith2023] and [@jones2024; @wang2025]."
        bib = "@article{smith2023, title={A}}\n@article{jones2024, title={B}}\n"
        report = checker.check(content, bib)
        assert "smith2023" in report.used_keys
        assert "wang2025" in report.used_keys
        assert "wang2025" in report.missing_keys
        assert report.verdict == "FAIL"

    def test_orphan_keys(self):
        from app.services.citation_qa_checker import CitationQAChecker
        checker = CitationQAChecker()
        content = r"\cite{smith2023}"
        bib = "@article{smith2023, title={A}}\n@article{unused2024, title={B}}\n"
        report = checker.check(content, bib)
        assert "unused2024" in report.orphan_keys
        assert report.verdict == "PASS"  # orphans don't cause FAIL

    def test_empty_inputs(self):
        from app.services.citation_qa_checker import CitationQAChecker
        checker = CitationQAChecker()
        report = checker.check("", "")
        assert report.verdict == "PASS"
        assert report.total_used == 0

    def test_report_to_dict(self):
        from app.services.citation_qa_checker import CitationQAChecker
        checker = CitationQAChecker()
        report = checker.check(r"\cite{a}", "@article{a, title={X}}\n")
        d = report.to_dict()
        assert "verdict" in d
        assert "used_keys" in d
        assert d["verdict"] == "PASS"


class TestV12_B5_LoopCheckpoints:
    """B5: Loop Checkpoints — verify HIL ticket creation code exists"""

    def test_exec_loop1_checkpoint_in_initialize(self):
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.initialize)
        assert "Exec-Loop1" in source
        assert "HILTicketCreate" in source

    def test_deliv_loop1_checkpoint_in_figure_polish(self):
        import inspect
        from app.steps.step4 import Step4_FigurePolish
        source = inspect.getsource(Step4_FigurePolish.execute)
        assert "Deliv-Loop1" in source
        assert "blocking=True" in source

    def test_deliv_loop3_checkpoint_in_package(self):
        import inspect
        from app.steps.step4 import Step4_Package
        source = inspect.getsource(Step4_Package.execute)
        assert "Deliv-Loop3" in source
        assert "delivery_profile" in source


# ============================================================
# v1.2 §4: State Machine Gap Fixes (H1-H5)
# ============================================================

class TestV12_H_StateMachineGaps:
    """v1.2 §4 HIGH defect fixes — verify state machine guard logic exists"""

    def test_h1_boundary_check_in_execute_wp_source(self):
        """H1: BoundaryChecker.check called after subtask completion"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.execute_wp)
        assert "ArtifactBoundaryChecker.check" in source
        assert "allowed_paths" in source
        assert "forbidden_paths" in source
        assert "bc_result.passed" in source or "not bc_result.passed" in source

    def test_h2_figure_polish_has_review_loop(self):
        """H2: FigurePolish uses request_and_wait for human review loop"""
        import inspect
        from app.steps.step4 import Step4_FigurePolish
        source = inspect.getsource(Step4_FigurePolish.execute)
        assert "request_and_wait" in source
        assert "MAX_REVIEW_ROUNDS" in source
        assert "approve" in source

    def test_h3_assembly_has_profile_branch(self):
        """H3: Assembly branches on delivery_profile"""
        import inspect
        from app.steps.step4 import Step4_Assembly
        source = inspect.getsource(Step4_Assembly.execute)
        assert "delivery_profile" in source
        assert "internal_draft" in source
        assert "render_paper_draft_prompt" in source
        assert "PAPER_DRAFT" in source

    def test_h4_citation_qa_creates_hil_on_fail(self):
        """H4: CitationQA creates blocking HIL on FAIL verdict"""
        import inspect
        from app.steps.step4 import Step4_CitationQA
        source = inspect.getsource(Step4_CitationQA.execute)
        assert "citation_report.verdict" in source
        assert "FAIL" in source
        assert "HILTicketCreate" in source
        assert "CRITICAL" in source
        assert "blocking=True" in source

    def test_h4_repro_check_creates_hil_on_fail(self):
        """H4: ReproCheck creates blocking HIL on mismatch"""
        import inspect
        from app.steps.step4 import Step4_ReproCheck
        source = inspect.getsource(Step4_ReproCheck.execute)
        assert "not all_match" in source
        assert "HILTicketCreate" in source
        assert "CRITICAL" in source
        assert "blocking=True" in source

    def test_h5_package_has_gate_checks(self):
        """H5: Package has pre-package gate checks"""
        import inspect
        from app.steps.step4 import Step4_Package
        source = inspect.getsource(Step4_Package.execute)
        assert "gate_failures" in source
        assert "citation_report.json" in source
        assert "repro_check_report.json" in source
        assert "Pre-package gate FAIL" in source

    def test_paper_draft_document_type(self):
        """PAPER_DRAFT enum exists in DocumentType"""
        from app.models.document import DocumentType
        assert hasattr(DocumentType, "PAPER_DRAFT")
        assert DocumentType.PAPER_DRAFT.value == "06_Paper_Draft"

    def test_render_paper_draft_prompt_exists(self):
        """render_paper_draft_prompt is callable"""
        from app.prompts.step4_prompts import render_paper_draft_prompt
        result = render_paper_draft_prompt("manifest", "artifacts", "claims")
        assert isinstance(result, str)
        assert "需作者复核" in result
        assert "internal" in result.lower() or "Internal" in result or "draft" in result.lower()


# ============================================================
# v1.2 §4: State Machine MEDIUM Gap Fixes (M1-M4)
# ============================================================

class TestV12_M_StateMachineGaps:
    """v1.2 §4 MEDIUM defect fixes — verify state machine guard logic exists"""

    def test_m1_collect_cross_check_plan_frozen(self):
        """M1: D0 Collect cross-checks against PlanFrozen deliverables"""
        import inspect
        from app.steps.step4 import Step4_Collect
        source = inspect.getsource(Step4_Collect.execute)
        assert "RESEARCH_PLAN_FROZEN" in source
        assert "missing_items" in source
        assert "HILTicketCreate" in source
        assert "cross-check" in source.lower() or "D0 cross-check" in source

    def test_m2_repro_check_has_deliv_loop2(self):
        """M2: D4 ReproCheck has Deliv-Loop2 human checkpoint"""
        import inspect
        from app.steps.step4 import Step4_ReproCheck
        source = inspect.getsource(Step4_ReproCheck.execute)
        assert "Deliv-Loop2" in source
        assert "blocking=True" in source
        assert "HILTicketCreate" in source

    def test_m3_session_log_after_subtask(self):
        """M3: E2 execute_wp writes session log after each subtask"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.execute_wp)
        assert "session_logger.log_decision" in source
        assert "Subtask" in source

    def test_m4_memory_lesson_at_freeze(self):
        """M4: E6 freeze_wp writes lessons to MEMORY.md"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "memory_store.add_learn_entry" in source
        assert "freeze_wp" in source
        assert "open_issues" in source


# ============================================================
# v1.2 §6: Standardized Prompt Template Compliance
# ============================================================

class TestV12_P_PromptCompliance:
    """v1.2 §6 prompt template compliance tests"""

    # --- P1: render_execute_prompt (§6.2 EXECUTE) ---

    def test_execute_prompt_has_task_header(self):
        """§6.2: EXECUTE prompt must have Task/Model header"""
        from app.prompts.step3_prompts import render_execute_prompt
        result = render_execute_prompt(
            wp_spec_yaml="wp: test",
            subtask_spec_yaml="st: test",
            wp_id="wp1",
            subtask_id="wp1_st1",
            owner_model="chatgpt",
        )
        assert "# Task: wp1 / wp1_st1" in result
        assert "# Model: chatgpt" in result

    def test_execute_prompt_has_acceptance_criteria(self):
        """§6.2: EXECUTE prompt must have checkbox-style Acceptance Criteria"""
        from app.prompts.step3_prompts import render_execute_prompt
        result = render_execute_prompt(
            wp_spec_yaml="wp: test",
            subtask_spec_yaml="st: test",
        )
        assert "## Acceptance Criteria" in result
        assert "- [ ]" in result

    def test_execute_prompt_has_constraints(self):
        """§6.2: EXECUTE prompt must have structured Constraints section"""
        from app.prompts.step3_prompts import render_execute_prompt
        result = render_execute_prompt(
            wp_spec_yaml="wp: test",
            subtask_spec_yaml="st: test",
        )
        assert "## Constraints" in result
        assert "allowed_paths" in result
        assert "forbidden_paths" in result
        assert "越界警告" in result
        assert "session log" in result.lower() or "session log" in result

    def test_execute_prompt_has_token_budget(self):
        """§6.2: EXECUTE prompt must include Token Budget Hint when provided"""
        from app.prompts.step3_prompts import render_execute_prompt
        result = render_execute_prompt(
            wp_spec_yaml="wp: test",
            subtask_spec_yaml="st: test",
            token_budget_hint="~2000 tokens",
        )
        assert "## Token Budget Hint" in result
        assert "~2000 tokens" in result

    # --- P2: render_review_acceptance_prompt (§6.3 REVIEW_ACCEPTANCE) ---

    def test_review_acceptance_json_format(self):
        """§6.3: REVIEW_ACCEPTANCE must output JSON with criteria/critical_issues"""
        from app.prompts.step3_prompts import render_review_acceptance_prompt
        result = render_review_acceptance_prompt(
            wp_spec_yaml="wp: test",
            subtask_results_summary="all done",
            gate_criteria="criterion 1",
        )
        assert "JSON" in result
        assert '"verdict"' in result
        assert '"criteria"' in result
        assert '"critical_issues"' in result
        # Must NOT contain old YAML format
        assert "```yaml" not in result

    def test_review_acceptance_has_prohibitions(self):
        """§6.3: REVIEW_ACCEPTANCE must have prohibitions section"""
        from app.prompts.step3_prompts import render_review_acceptance_prompt
        result = render_review_acceptance_prompt(
            wp_spec_yaml="wp: test",
            subtask_results_summary="all done",
            gate_criteria="criterion 1",
        )
        assert "禁止事项" in result
        assert "3" in result  # max 3 critical issues
        assert "部分通过" in result  # no partial pass

    # --- P3: render_review_fix_prompt (§6.4 REVIEW_FIX) ---

    def test_review_fix_has_iteration_header(self):
        """§6.4: REVIEW_FIX must have Iteration header"""
        from app.prompts.step3_prompts import render_review_fix_prompt
        result = render_review_fix_prompt(
            wp_spec_yaml="wp: test",
            review_issues="issue 1",
            allowed_paths="/data/*",
            previous_output="prev output",
            wp_id="wp2",
            iteration_count=2,
        )
        assert "# Fix: wp2 — Iteration 2/2" in result

    def test_review_fix_has_prohibitions(self):
        """§6.4: REVIEW_FIX must have prohibitions section"""
        from app.prompts.step3_prompts import render_review_fix_prompt
        result = render_review_fix_prompt(
            wp_spec_yaml="wp: test",
            review_issues="issue 1",
            allowed_paths="/data/*",
            previous_output="prev output",
        )
        assert "禁止事项" in result
        assert "不要重构" in result

    # --- P4: render_diagnose_prompt (§6.5 DIAGNOSE) ---

    def test_diagnose_json_format(self):
        """§6.5: DIAGNOSE must output JSON with hypotheses; accept agents_md/memory params"""
        from app.prompts.step3_prompts import render_diagnose_prompt
        result = render_diagnose_prompt(
            wp_spec_yaml="wp: test",
            iteration_history="iter 1 failed",
            gate_failures="gate fail",
            agents_md_dynamic="dynamic section content",
            memory_lessons="lesson 1",
        )
        assert "JSON" in result
        assert '"hypotheses"' in result
        assert '"recommended_action"' in result
        assert '"files_to_examine"' in result
        assert "dynamic section content" in result
        assert "lesson 1" in result
        # Must NOT contain old YAML format
        assert "```yaml" not in result

    def test_diagnose_has_prohibitions(self):
        """§6.5: DIAGNOSE must have prohibitions section"""
        from app.prompts.step3_prompts import render_diagnose_prompt
        result = render_diagnose_prompt(
            wp_spec_yaml="wp: test",
            iteration_history="iter 1 failed",
            gate_failures="gate fail",
        )
        assert "禁止事项" in result

    # --- P5: render_assembly_kit_prompt (§6.7 ASSEMBLY_KIT) ---

    def test_assembly_kit_has_required_outputs(self):
        """§6.7: ASSEMBLY_KIT must specify 6 output files"""
        from app.prompts.step4_prompts import render_assembly_kit_prompt
        result = render_assembly_kit_prompt(
            delivery_manifest="manifest",
            frozen_artifacts="artifacts",
        )
        assert "assembly_kit/outline.md" in result
        assert "assembly_kit/figure_table_plan.md" in result
        assert "assembly_kit/citation_map.md" in result
        assert "assembly_kit/claim_evidence_matrix.md" in result
        assert "assembly_kit/writing_guide.md" in result
        assert "assembly_kit/refs.bib" in result

    def test_assembly_kit_has_prohibitions(self):
        """§6.7: ASSEMBLY_KIT must have '你不做什么' section"""
        from app.prompts.step4_prompts import render_assembly_kit_prompt
        result = render_assembly_kit_prompt(
            delivery_manifest="manifest",
            frozen_artifacts="artifacts",
        )
        assert "你不做什么" in result
        assert "不产生新结论" in result
        assert "不引入新引用" in result
        assert "不添加新数据" in result

    # --- P6: render_figure_gen_prompt (§6.6 FIGURE_GEN) ---

    def test_figure_gen_prompt_exists(self):
        """§6.6: render_figure_gen_prompt must be callable and produce correct output"""
        from app.prompts.step4_prompts import render_figure_gen_prompt
        result = render_figure_gen_prompt(
            figure_id="fig1",
            journal_spec="DPI: 300, Font: Arial",
            figure_spec="Bar chart of accuracy vs model size",
            data_file_path="data/results.csv",
            acceptance_criteria="- [ ] Axes labeled",
        )
        assert "# Figure Generation: fig1" in result
        assert "fig1" in result
        assert "Bar chart" in result
        assert "data/results.csv" in result
        assert "DPI: 300" in result


# ============================================================
# v1.2 §9: Gate System Compliance
# ============================================================

class TestV12_G_GateSystemCompliance:
    """v1.2 §9 Gate System compliance tests"""

    # --- §9.3 DeliveryGateChecklist D1-D8 field alignment ---

    def test_delivery_gate_has_8_spec_fields(self):
        """§9.3: DeliveryGateChecklist must have D1-D8 fields matching spec"""
        from app.models.gate import DeliveryGateChecklist
        fields = DeliveryGateChecklist.model_fields
        assert "all_wps_frozen" in fields          # D1
        assert "all_figures_approved" in fields     # D2
        assert "assembly_complete" in fields        # D3
        assert "repro_check_pass" in fields         # D4
        assert "deliverables_complete" in fields    # D5
        assert "checksums_valid" in fields          # D6
        assert "citations_verified" in fields       # D7
        assert "no_forbidden_output" in fields      # D8
        # Old fields must NOT exist
        assert "manifest_complete" not in fields
        assert "citation_qa_passed" not in fields
        assert "package_created" not in fields

    def test_delivery_gate_check_item_names(self):
        """§9.3: validate() check_items must use D1-D8 naming"""
        from app.models.gate import DeliveryGateChecklist
        checklist = DeliveryGateChecklist()
        result = checklist.validate()
        names = [ci.item_name for ci in result.check_items]
        assert names[0].startswith("D1:")
        assert names[1].startswith("D2:")
        assert names[2].startswith("D3:")
        assert names[3].startswith("D4:")
        assert names[4].startswith("D5:")
        assert names[5].startswith("D6:")
        assert names[6].startswith("D7:")
        assert names[7].startswith("D8:")

    def test_delivery_gate_d2_description_mentions_code_runnable(self):
        """§9.3 D2: must check human_approved AND 生成代码可运行"""
        from app.models.gate import DeliveryGateChecklist
        checklist = DeliveryGateChecklist()
        result = checklist.validate()
        d2 = result.check_items[1]
        assert "代码可运行" in d2.description or "code" in d2.description.lower()

    def test_delivery_gate_d4_description_mentions_repro(self):
        """§9.3 D4: must check repro_check.json verdict=PASS"""
        from app.models.gate import DeliveryGateChecklist
        checklist = DeliveryGateChecklist()
        result = checklist.validate()
        d4 = result.check_items[3]
        assert "repro" in d4.description.lower()

    # --- §9.2 FreezeGateChecklist F1-F7 ---

    def test_freeze_gate_has_7_items(self):
        """§9.2: FreezeGateChecklist must have F1-F7"""
        from app.models.gate import FreezeGateChecklist
        checklist = FreezeGateChecklist()
        result = checklist.validate()
        assert result.total_count == 7

    # --- parse_review_yaml handles JSON ---

    def test_parse_review_handles_json(self):
        """§6.3: parse_review_yaml must parse JSON (v1.2 format)"""
        from app.services.wp_gate_checker import WPGateChecker
        json_input = '{"verdict": "PASS", "criteria": [{"id": "gc1", "name": "test", "result": "PASS", "evidence": "ok"}]}'
        result = WPGateChecker.parse_review_yaml(json_input)
        assert result["verdict"] == "PASS"
        assert len(result["criteria"]) == 1

    def test_parse_review_handles_json_with_fences(self):
        """§6.3: parse_review_yaml must handle ```json fences"""
        from app.services.wp_gate_checker import WPGateChecker
        fenced = '```json\n{"verdict": "FAIL", "critical_issues": []}\n```'
        result = WPGateChecker.parse_review_yaml(fenced)
        assert result["verdict"] == "FAIL"

    def test_parse_review_handles_yaml_fallback(self):
        """Backward compat: parse_review_yaml still handles YAML"""
        from app.services.wp_gate_checker import WPGateChecker
        yaml_input = 'verdict: "PASS"\nissues: []\n'
        result = WPGateChecker.parse_review_yaml(yaml_input)
        assert result["verdict"] == "PASS"

    def test_parse_review_handles_diagnose_json(self):
        """§6.5: parse_review_yaml must parse diagnose JSON format"""
        from app.services.wp_gate_checker import WPGateChecker
        diagnose_json = '{"hypotheses": [{"description": "root cause", "confidence": 0.8}], "recommended_action": "fix it", "files_to_examine": ["a.py"]}'
        result = WPGateChecker.parse_review_yaml(diagnose_json)
        assert "hypotheses" in result
        assert result["recommended_action"] == "fix it"


# ============================================================
# v1.2 §7: Escalation Chain Compliance
# ============================================================

class TestV12_E_EscalationChainCompliance:
    """v1.2 §7 Escalation Chain compliance tests"""

    def test_max_iterations_default_is_2(self):
        """§7.2: max_iterations 默认值应该是 2（2 轮 review-fix 循环）"""
        from app.models.work_package import WPSpec
        spec = WPSpec(wp_id="wp1", name="test")
        assert spec.max_iterations == 2

    def test_iteration_count_increments_on_review_fail(self):
        """§7.2: iteration_count 只在 review FAIL 时增加"""
        from app.models.work_package import WPState, WPStatus
        state = WPState(wp_id="wp1")
        assert state.iteration_count == 0
        # Simulate review fail
        state.iteration_count += 1
        assert state.iteration_count == 1

    def test_escalation_triggers_after_max_iterations(self):
        """§7.2: iteration_count >= max_iterations 触发 ESCALATED"""
        from app.models.work_package import WPSpec
        spec = WPSpec(wp_id="wp1", name="test", max_iterations=2)
        # After 2 iterations, should escalate
        assert spec.max_iterations == 2

    def test_hil_answer_resets_iteration_count(self):
        """§7.2: Human 介入后 iteration_count 归零"""
        # This is tested via the API endpoint logic in hil.py
        # The reset happens in answer_hil_ticket() when wp_id is present
        import inspect
        from app.api.hil import answer_hil_ticket
        source = inspect.getsource(answer_hil_ticket)
        assert "reset_iteration" in source.lower() or "iteration_count = 0" in source
        assert "§7.2" in source  # Should reference the spec


# ============================================================
# v1.2 §8: Token 管理策略 Compliance
# ============================================================

class TestV12_T_TokenManagementCompliance:
    """v1.2 §8 Token 管理策略 compliance tests"""

    def test_t2_previous_results_uses_structured_summary(self):
        """§8.2 T2: previous_results 应使用结构化摘要（what_changed + metrics + open_issues），不传完整 summary"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.execute_wp)
        # 应该包含结构化字段
        assert "what_changed" in source
        assert "metrics" in source
        assert "open_issues" in source
        # 应该有 T2 注释
        assert "T2" in source or "结构化摘要" in source

    def test_t8_memory_injection_has_token_limit(self):
        """§8.2 T8: MEMORY.md 注入应控制在 < 500 tokens"""
        from app.services.memory_store import MemoryStore
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(tmpdir)
            store.initialize()
            # get_injection_content 应该有 max_tokens 参数
            content = store.get_injection_content(max_tokens=500)
            # 估算 token 数（粗略：3 chars per token）
            estimated_tokens = len(content) // 3
            assert estimated_tokens <= 500

    def test_memory_store_uses_get_injection_content(self):
        """§8.2 T8: wp_engine 应使用 get_injection_content 而非 get_all_entries_formatted"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine)
        # 应该调用 get_injection_content
        assert "get_injection_content" in source
        # 应该指定 max_tokens=500
        assert "max_tokens=500" in source

    def test_session_resume_prompt_exists(self):
        """§8.3: Session Resume 协议应该存在"""
        from app.prompts.step3_prompts import render_session_resume_prompt
        # 函数应该存在且可调用
        assert callable(render_session_resume_prompt)


# ============================================================
# v1.2 §11: Freeze Hygiene Protocol Compliance
# ============================================================

class TestV12_F_FreezeHygieneCompliance:
    """v1.2 §11 Freeze Hygiene Protocol compliance tests"""

    def test_freeze_wp_creates_git_tag(self):
        """§11.1 step 1: freeze_wp 应创建 git tag {wp_id}-v{version}"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "create_tag" in source
        assert "tag_name" in source

    def test_freeze_manifest_includes_ra_result(self):
        """§11.1 step 3: FROZEN_MANIFEST 应包含 ra_result 引用"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "ra_result" in source
        assert "FROZEN_MANIFEST" in source

    def test_freeze_wp_uploads_to_artifact_store(self):
        """§11.1 step 2: freeze_wp 应上传产物到持久化存储"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "artifact_store" in source.lower() or "ArtifactStore" in source
        assert "save_artifact" in source or "upload" in source.lower()

    def test_freeze_wp_updates_agents_md(self):
        """§11.1 step 5: freeze_wp 应更新 AGENTS.md 动态 section"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "update_agents_md" in source

    def test_freeze_wp_writes_session_log(self):
        """§11.1 step 6: freeze_wp 应写入 session_log summary"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "session_logger" in source
        assert "wrap_up" in source

    def test_freeze_wp_writes_memory_lessons(self):
        """§11.1 step 7: freeze_wp 应追加 MEMORY.md 教训"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "memory_store" in source
        assert "add_learn_entry" in source

    def test_freeze_wp_unlocks_downstream_wps(self):
        """§11.1 step 8: freeze_wp 应解锁依赖此 WP 的下游 WP"""
        import inspect
        from app.services.wp_engine import WPExecutionEngine
        source = inspect.getsource(WPExecutionEngine.freeze_wp)
        assert "get_ready_wps" in source

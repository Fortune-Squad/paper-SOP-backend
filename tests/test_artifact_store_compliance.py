"""
v1.2 §5 Artifact Store 合规测试

验证 state.json schema、DocumentType、SubtaskResult、RA 模型、路径映射、目录结构
均符合 DevSpec v1.2 §5.1-§5.10 的要求。
"""
import os
import pytest
from datetime import datetime


# ---------------------------------------------------------------------------
# §5.2 state.json — WPState 字段
# ---------------------------------------------------------------------------

class TestWPStateFields:
    """WPState 应包含 v1.2 §5.2 要求的全部字段"""

    def test_wp_state_has_frozen_artifacts(self):
        from app.models.work_package import WPState
        ws = WPState(wp_id="wp1")
        assert hasattr(ws, "frozen_artifacts")
        assert ws.frozen_artifacts == []

    def test_wp_state_has_ra_result(self):
        from app.models.work_package import WPState
        ws = WPState(wp_id="wp1")
        assert hasattr(ws, "ra_result")
        assert ws.ra_result is None

    def test_wp_state_has_ra_polish_todos(self):
        from app.models.work_package import WPState
        ws = WPState(wp_id="wp1")
        assert hasattr(ws, "ra_polish_todos")
        assert ws.ra_polish_todos == []

    def test_wp_state_has_current_subtask(self):
        from app.models.work_package import WPState
        ws = WPState(wp_id="wp1")
        assert hasattr(ws, "current_subtask")
        assert ws.current_subtask is None


# ---------------------------------------------------------------------------
# §5.2 state.json — ExecutionState 字段
# ---------------------------------------------------------------------------

class TestExecutionStateFields:
    """ExecutionState 应包含 v1.2 §5.2 要求的全部字段"""

    def test_execution_state_has_last_writer(self):
        from app.models.work_package import ExecutionState
        es = ExecutionState(project_id="test")
        assert hasattr(es, "last_writer")
        assert es.last_writer is None

    def test_execution_state_has_current_phase(self):
        from app.models.work_package import ExecutionState
        es = ExecutionState(project_id="test")
        assert hasattr(es, "current_phase")
        assert es.current_phase == "step3_execution"

    def test_execution_state_has_plan_frozen_ref(self):
        from app.models.work_package import ExecutionState
        es = ExecutionState(project_id="test")
        assert hasattr(es, "plan_frozen_ref")
        assert es.plan_frozen_ref is None


# ---------------------------------------------------------------------------
# §5.2 state.json — DeliveryState 字段
# ---------------------------------------------------------------------------

class TestDeliveryStateFields:
    """DeliveryState 应包含 v1.2 §5.2 要求的全部字段"""

    def test_delivery_state_has_missing_deliverables(self):
        from app.models.work_package import DeliveryState
        ds = DeliveryState()
        assert hasattr(ds, "missing_deliverables")
        assert ds.missing_deliverables == []

    def test_delivery_state_has_delivery_profile(self):
        from app.models.work_package import DeliveryState, DeliveryProfile
        ds = DeliveryState()
        assert ds.delivery_profile == DeliveryProfile.EXTERNAL_ASSEMBLY_KIT
        # 写入测试
        ds.delivery_profile = DeliveryProfile.INTERNAL_DRAFT
        assert ds.profile == DeliveryProfile.INTERNAL_DRAFT


# ---------------------------------------------------------------------------
# §5.3 SubtaskResult — 结构化四件套
# ---------------------------------------------------------------------------

class TestSubtaskResultStructured:
    """SubtaskResult 四件套应同时接受 str 和 Dict 格式"""

    def test_subtask_result_accepts_structured_what_changed(self):
        from app.models.work_package import SubtaskResult
        sr = SubtaskResult(
            subtask_id="wp1_st1",
            what_changed=[{"path": "src/main.py", "change_type": "modified", "notes": "fix bug"}],
        )
        assert len(sr.what_changed) == 1
        assert sr.what_changed[0]["path"] == "src/main.py"

    def test_subtask_result_accepts_structured_commands_ran(self):
        from app.models.work_package import SubtaskResult
        sr = SubtaskResult(
            subtask_id="wp1_st1",
            commands_ran=[{"cmd": "pytest", "exit_code": 0, "time_sec": 3.2}],
        )
        assert sr.commands_ran[0]["exit_code"] == 0

    def test_subtask_result_accepts_structured_open_issues(self):
        from app.models.work_package import SubtaskResult
        sr = SubtaskResult(
            subtask_id="wp1_st1",
            open_issues=[{
                "id": "issue-1",
                "severity": "high",
                "desc": "missing test",
                "evidence_path": "tests/",
                "suggested_next": "add unit test",
            }],
        )
        assert sr.open_issues[0]["severity"] == "high"

    def test_subtask_result_accepts_structured_artifacts_written(self):
        from app.models.work_package import SubtaskResult
        sr = SubtaskResult(
            subtask_id="wp1_st1",
            artifacts_written=[{"path": "output.md", "sha256": "abc123"}],
        )
        assert sr.artifacts_written[0]["sha256"] == "abc123"

    def test_subtask_result_backward_compat_string_lists(self):
        """旧版 List[str] 格式仍然可用"""
        from app.models.work_package import SubtaskResult
        sr = SubtaskResult(
            subtask_id="wp1_st1",
            what_changed=["file1.py", "file2.py"],
            commands_ran=["pytest -v"],
            open_issues=["need more tests"],
            artifacts_written=["output.md"],
        )
        assert sr.what_changed == ["file1.py", "file2.py"]
        assert sr.commands_ran == ["pytest -v"]
        assert sr.open_issues == ["need more tests"]
        assert sr.artifacts_written == ["output.md"]


# ---------------------------------------------------------------------------
# §5.4 DocumentType — v1.2 新增类型
# ---------------------------------------------------------------------------

class TestDocumentTypeV12:
    """DocumentType 应包含 v1.2 §5.4 新增的 7 个类型"""

    def test_document_type_has_readiness_assessment(self):
        from app.models.document import DocumentType
        assert DocumentType.READINESS_ASSESSMENT.value == "05_Readiness_Assessment"

    def test_document_type_has_session_log(self):
        from app.models.document import DocumentType
        assert DocumentType.SESSION_LOG.value == "05_Session_Log"

    def test_document_type_has_task_plan(self):
        from app.models.document import DocumentType
        assert DocumentType.TASK_PLAN.value == "05_Task_Plan"

    def test_document_type_has_agents_md(self):
        from app.models.document import DocumentType
        assert DocumentType.AGENTS_MD.value == "00_Agents_MD"

    def test_document_type_has_memory_md(self):
        from app.models.document import DocumentType
        assert DocumentType.MEMORY_MD.value == "00_Memory_MD"

    def test_document_type_has_boundary_log(self):
        from app.models.document import DocumentType
        assert DocumentType.BOUNDARY_LOG.value == "05_Boundary_Log"

    def test_document_type_has_frozen_manifest(self):
        from app.models.document import DocumentType
        assert DocumentType.FROZEN_MANIFEST.value == "05_Frozen_Manifest"


# ---------------------------------------------------------------------------
# §5.9 Readiness Assessment — Pydantic 模型
# ---------------------------------------------------------------------------

class TestReadinessAssessmentModel:
    """RA Pydantic 模型应符合 §5.9 JSON schema"""

    def test_readiness_assessment_model(self):
        from app.models.readiness_assessment import ReadinessAssessmentResult
        ra = ReadinessAssessmentResult(
            verdict="ADVANCE",
            reasoning="All criteria met.",
            north_star_alignment="Strong alignment with research question.",
            missing_pieces=[],
            polish_suggestions=[],
            next_wp_readiness="ready",
        )
        assert ra.verdict == "ADVANCE"
        assert ra.reasoning == "All criteria met."
        assert ra.north_star_alignment == "Strong alignment with research question."
        assert ra.missing_pieces == []
        assert ra.polish_suggestions == []
        assert ra.next_wp_readiness == "ready"

    def test_readiness_assessment_polish(self):
        from app.models.readiness_assessment import ReadinessAssessmentResult
        ra = ReadinessAssessmentResult(
            verdict="POLISH",
            reasoning="Minor issues found.",
            north_star_alignment="Partial alignment.",
            missing_pieces=["statistical analysis"],
            polish_suggestions=["Add p-value table", "Rerun simulation"],
            next_wp_readiness="blocked until polish done",
        )
        assert ra.verdict == "POLISH"
        assert len(ra.polish_suggestions) == 2


# ---------------------------------------------------------------------------
# §5.1 目录结构 — quality_rubrics/
# ---------------------------------------------------------------------------

class TestQualityRubricsDir:
    """sop/quality_rubrics/ 目录应存在"""

    def test_quality_rubrics_dir_exists(self):
        rubrics_dir = os.path.join(
            os.path.dirname(__file__), "..", "sop", "quality_rubrics"
        )
        assert os.path.isdir(rubrics_dir), f"quality_rubrics/ 目录不存在: {rubrics_dir}"


# ---------------------------------------------------------------------------
# §5.4 v7 路径映射 — 新类型
# ---------------------------------------------------------------------------

class TestV7PathMappingNewTypes:
    """新增 DocumentType 应有对应的 v7 路径映射"""

    def test_v7_path_mapping_new_types(self):
        from app.models.document import DocumentType
        from app.config.v7_path_mapping import V7_PATH_MAPPING

        new_types = [
            (DocumentType.READINESS_ASSESSMENT, "05_execution", "05_Readiness_Assessment.json"),
            (DocumentType.SESSION_LOG, "05_execution", "05_Session_Log.md"),
            (DocumentType.TASK_PLAN, "05_execution", "05_Task_Plan.md"),
            (DocumentType.AGENTS_MD, ".", "AGENTS.md"),
            (DocumentType.MEMORY_MD, ".", "MEMORY.md"),
            (DocumentType.BOUNDARY_LOG, "05_execution", "05_Boundary_Log.json"),
            (DocumentType.FROZEN_MANIFEST, "05_execution", "05_Frozen_Manifest.json"),
        ]
        for doc_type, expected_dir, expected_file in new_types:
            assert doc_type in V7_PATH_MAPPING, f"{doc_type} 缺少路径映射"
            actual_dir, actual_file = V7_PATH_MAPPING[doc_type]
            assert actual_dir == expected_dir, f"{doc_type}: 目录应为 {expected_dir}，实际 {actual_dir}"
            assert actual_file == expected_file, f"{doc_type}: 文件应为 {expected_file}，实际 {actual_file}"

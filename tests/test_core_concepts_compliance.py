"""
v1.2 §2 核心概念合规测试

验证 5 项合规缺陷修复:
  1. §2.2.4 Escalation Chain 完整实现
  2. §2.2.8 Hook 运行时接线
  3. §2.2.3 Subtask 级 gate
  4. §2.2.7 跨模型冲突仲裁
  5. §2.2.2 last_writer 填充
"""
import os
import json
import asyncio
import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch


def _run(coro):
    """Run async coroutine synchronously (avoids pytest-asyncio dependency)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# §2.2.4 Escalation Chain
# ---------------------------------------------------------------------------

class TestEscalationChain:
    """§2.2.4: Escalation Chain 完整实现"""

    def test_secondary_review_status_exists(self):
        """WPStatus.SECONDARY_REVIEW 枚举存在"""
        from app.models.work_package import WPStatus
        assert hasattr(WPStatus, "SECONDARY_REVIEW")
        assert WPStatus.SECONDARY_REVIEW.value == "secondary_review"

    def test_secondary_review_in_status_values(self):
        """SECONDARY_REVIEW 在所有状态值中"""
        from app.models.work_package import WPStatus
        all_values = [s.value for s in WPStatus]
        assert "secondary_review" in all_values

    def test_escalate_wp_creates_hil_ticket(self):
        """escalate_wp() 后 HIL ticket 被创建"""
        from app.services.wp_engine import WPExecutionEngine
        from app.models.work_package import (
            ExecutionState, WPSpec, WPState, WPStatus,
        )

        engine = WPExecutionEngine(project_id="test_proj")
        wp_spec = WPSpec(
            wp_id="wp1", name="Test WP", owner="chatgpt", reviewer="claude",
            gate_criteria=["test"], subtasks=[],
        )
        wp_state = WPState(wp_id="wp1", status=WPStatus.ESCALATED, iteration_count=2)
        state = ExecutionState(
            project_id="test_proj", wp_specs={"wp1": wp_spec},
            wp_states={"wp1": wp_state}, wp_dag={"wp1": []},
        )

        engine.state_store = MagicMock()
        engine.state_store.load.return_value = state
        engine.state_store.update.return_value = state
        engine.gemini_client = AsyncMock()
        engine.gemini_client.chat.return_value = '{"verdict": "FAIL", "issues": ["test issue"]}'
        engine.memory_store = MagicMock()
        engine.session_logger = MagicMock()
        engine.snapshot_generator = MagicMock()

        mock_hil = AsyncMock()
        with patch("app.services.hil_service.HILService", return_value=mock_hil):
            _run(engine.escalate_wp("wp1"))
            mock_hil.create_ticket.assert_called_once()
            call_args = mock_hil.create_ticket.call_args
            ticket_create = call_args[0][0]
            assert ticket_create.project_id == "test_proj"
            assert "wp1" in ticket_create.question

    def test_escalation_policy_skip_gemini(self):
        """skip_gemini 策略跳过 Gemini 直接 HIL"""
        from app.services.wp_engine import WPExecutionEngine
        from app.models.work_package import (
            ExecutionState, WPSpec, WPState, WPStatus,
        )

        engine = WPExecutionEngine(project_id="test_proj")
        wp_spec = WPSpec(
            wp_id="wp1", name="Test WP", owner="chatgpt", reviewer="claude",
            gate_criteria=["test"], subtasks=[], escalation_policy="skip_gemini",
        )
        wp_state = WPState(wp_id="wp1", status=WPStatus.ESCALATED, iteration_count=2)
        state = ExecutionState(
            project_id="test_proj", wp_specs={"wp1": wp_spec},
            wp_states={"wp1": wp_state}, wp_dag={"wp1": []},
        )

        engine.state_store = MagicMock()
        engine.state_store.load.return_value = state
        engine.gemini_client = AsyncMock()

        mock_hil = AsyncMock()
        with patch("app.services.hil_service.HILService", return_value=mock_hil):
            _run(engine.escalate_wp("wp1"))
            engine.gemini_client.chat.assert_not_called()
            mock_hil.create_ticket.assert_called_once()

    def test_secondary_reviewer_uses_different_model(self):
        """secondary reviewer 与 owner 不同模型"""
        from app.services.wp_engine import WPExecutionEngine
        engine = WPExecutionEngine(project_id="test_proj")
        assert engine._get_secondary_reviewer("claude") == "chatgpt"
        assert engine._get_secondary_reviewer("chatgpt") == "claude"
        assert engine._get_secondary_reviewer("gpt-4") == "claude"
        assert engine._get_secondary_reviewer("claude-sonnet") == "chatgpt"

    def test_wp_engine_has_secondary_review_method(self):
        """WPExecutionEngine 有 secondary_review_wp 方法"""
        from app.services.wp_engine import WPExecutionEngine
        assert hasattr(WPExecutionEngine, "secondary_review_wp")
        assert callable(getattr(WPExecutionEngine, "secondary_review_wp"))


# ---------------------------------------------------------------------------
# §2.2.8 Hook Runner
# ---------------------------------------------------------------------------

class TestHookRunner:
    """§2.2.8: Hook 运行时接线"""

    def test_hook_result_model(self):
        """HookResult 模型字段正确"""
        from app.services.hook_runner import HookResult
        hr = HookResult(hook_name="test", passed=True, message="ok")
        assert hr.hook_name == "test"
        assert hr.passed is True
        assert hr.message == "ok"

    def test_frozen_guard_detects_violation(self):
        """frozen 文件修改被检测"""
        import hashlib
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = Path(tmpdir) / "execution"
            exec_dir.mkdir()
            art_path = "docs/test.md"
            art_full = Path(tmpdir) / art_path
            art_full.parent.mkdir(parents=True, exist_ok=True)
            art_full.write_text("original content", encoding="utf-8")
            original_sha = hashlib.sha256(b"original content").hexdigest()

            manifest = {"artifacts": {art_path: {"sha256": original_sha}}}
            (exec_dir / "FROZEN_MANIFEST_wp1.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            art_full.write_text("modified content", encoding="utf-8")

            result = HookRunner.check_frozen_guard(tmpdir)
            assert result.passed is False
            assert "test.md" in result.message

    def test_frozen_guard_passes_clean(self):
        """无修改时通过"""
        import hashlib
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            exec_dir = Path(tmpdir) / "execution"
            exec_dir.mkdir()
            art_path = "docs/test.md"
            art_full = Path(tmpdir) / art_path
            art_full.parent.mkdir(parents=True, exist_ok=True)
            content = "original content"
            art_full.write_text(content, encoding="utf-8")
            sha = hashlib.sha256(content.encode("utf-8")).hexdigest()

            manifest = {"artifacts": {art_path: {"sha256": sha}}}
            (exec_dir / "FROZEN_MANIFEST_wp1.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )

            result = HookRunner.check_frozen_guard(tmpdir)
            assert result.passed is True

    def test_log_reminder_warns_on_stale(self):
        """session log 过期时警告"""
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            result = HookRunner.check_log_reminder(tmpdir, step_count=10)
            assert result.passed is False
            assert "session" in result.message.lower()

    def test_log_reminder_passes_early(self):
        """step_count < 5 时不警告"""
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            result = HookRunner.check_log_reminder(tmpdir, step_count=2)
            assert result.passed is True

    def test_run_all_post_subtask(self):
        """批量运行返回结果列表"""
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            results = HookRunner.run_all_post_subtask(
                project_path=tmpdir,
                changed_files=["docs/output.md"],
                allowed_paths=["docs/*"],
                forbidden_paths=[],
                step_count=1,
            )
            assert isinstance(results, list)
            assert len(results) == 4
            hook_names = [r.hook_name for r in results]
            assert "frozen_guard" in hook_names
            assert "state_lock" in hook_names
            assert "log_reminder" in hook_names
            assert "boundary_check" in hook_names

    def test_state_lock_valid(self):
        """state.json 版本有效时通过"""
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps({"state_version": 5}), encoding="utf-8")
            result = HookRunner.check_state_lock(tmpdir)
            assert result.passed is True

    def test_state_lock_invalid(self):
        """state.json 版本无效时失败"""
        from app.services.hook_runner import HookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "state.json"
            state_file.write_text(json.dumps({"state_version": 0}), encoding="utf-8")
            result = HookRunner.check_state_lock(tmpdir)
            assert result.passed is False


# ---------------------------------------------------------------------------
# §2.2.8 Rule Injection
# ---------------------------------------------------------------------------

class TestRuleInjection:
    """§2.2.8: sop/rules/ 注入到 prompt"""

    def test_context_injection_includes_rules(self):
        """get_project_context_injection() 包含 rule 内容"""
        from app.steps.base import BaseStep

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project-specific rules dir
            proj_dir = Path(tmpdir) / "test_proj" / "sop" / "rules"
            proj_dir.mkdir(parents=True)
            (proj_dir / "no_plagiarism.md").write_text(
                "# No Plagiarism\nDo not copy.", encoding="utf-8"
            )

            mock_project = MagicMock()
            mock_project.project_id = "test_proj"

            with patch("app.steps.base.BaseStep.__abstractmethods__", set()):
                step = BaseStep(project=mock_project)

                with patch("app.services.prompt_pack_compiler.inject_agents_md", return_value="(AGENTS.md not found)"), \
                     patch("app.services.prompt_pack_compiler.inject_memory_md", return_value="(MEMORY.md empty)"), \
                     patch("app.config.settings") as mock_settings:
                    mock_settings.projects_path = tmpdir
                    result = step.get_project_context_injection()
                    assert "Rule:" in result
                    assert "No Plagiarism" in result


# ---------------------------------------------------------------------------
# §2.2.3 Subtask Gate
# ---------------------------------------------------------------------------

class TestSubtaskGate:
    """§2.2.3: Subtask 级 gate"""

    def test_subtask_gate_checklist_model(self):
        """SubtaskGateChecklist 4 个字段"""
        from app.models.gate import SubtaskGateChecklist
        c = SubtaskGateChecklist()
        assert hasattr(c, "status_completed")
        assert hasattr(c, "boundary_check_passed")
        assert hasattr(c, "acceptance_criteria_met")
        assert hasattr(c, "no_critical_issues")

    def test_subtask_gate_type_exists(self):
        """GateType.GATE_SUBTASK 枚举存在"""
        from app.models.gate import GateType
        assert hasattr(GateType, "GATE_SUBTASK")
        assert GateType.GATE_SUBTASK.value == "gate_subtask"

    def test_subtask_gate_pass(self):
        """全部满足时 PASS"""
        from app.models.gate import SubtaskGateChecklist, GateVerdict
        c = SubtaskGateChecklist(
            status_completed=True,
            boundary_check_passed=True,
            acceptance_criteria_met=True,
            no_critical_issues=True,
        )
        result = c.validate(subtask_id="wp1_st1")
        assert result.verdict == GateVerdict.PASS
        assert result.passed_count == 4

    def test_subtask_gate_fail_on_critical_issue(self):
        """high severity issue 时 FAIL"""
        from app.models.gate import SubtaskGateChecklist, GateVerdict
        c = SubtaskGateChecklist(
            status_completed=True,
            boundary_check_passed=True,
            acceptance_criteria_met=True,
            no_critical_issues=False,
        )
        result = c.validate(subtask_id="wp1_st1")
        assert result.verdict == GateVerdict.FAIL
        assert result.passed_count == 3

    def test_check_subtask_gate_method_exists(self):
        """WPGateChecker 有 check_subtask_gate 方法"""
        from app.services.wp_gate_checker import WPGateChecker
        assert hasattr(WPGateChecker, "check_subtask_gate")
        assert callable(getattr(WPGateChecker, "check_subtask_gate"))

    def test_check_subtask_gate_pass(self):
        """check_subtask_gate 全部满足时 PASS"""
        from app.services.wp_gate_checker import WPGateChecker
        from app.models.work_package import SubtaskSpec, SubtaskResult
        from app.models.gate import GateVerdict

        checker = WPGateChecker()
        spec = SubtaskSpec(
            subtask_id="wp1_st1", wp_id="wp1", objective="Test",
            acceptance_criteria=["test completed"],
            allowed_paths=["docs/*"], forbidden_paths=[],
        )
        result = SubtaskResult(
            subtask_id="wp1_st1", status="completed",
            summary="Test completed successfully",
            what_changed=["docs/output.md"],
            open_issues=[],
        )
        gate = _run(checker.check_subtask_gate(spec, result))
        assert gate.verdict == GateVerdict.PASS

    def test_check_subtask_gate_fail_critical(self):
        """check_subtask_gate high severity issue 时 FAIL"""
        from app.services.wp_gate_checker import WPGateChecker
        from app.models.work_package import SubtaskSpec, SubtaskResult
        from app.models.gate import GateVerdict

        checker = WPGateChecker()
        spec = SubtaskSpec(
            subtask_id="wp1_st1", wp_id="wp1", objective="Test",
            acceptance_criteria=["test completed"],
            allowed_paths=["docs/*"], forbidden_paths=[],
        )
        result = SubtaskResult(
            subtask_id="wp1_st1", status="completed",
            summary="Test completed successfully",
            what_changed=["docs/output.md"],
            open_issues=[{"severity": "high", "desc": "critical bug"}],
        )
        gate = _run(checker.check_subtask_gate(spec, result))
        assert gate.verdict == GateVerdict.FAIL


# ---------------------------------------------------------------------------
# §2.2.7 跨模型冲突仲裁
# ---------------------------------------------------------------------------

class TestConflictArbitration:
    """§2.2.7: 跨模型冲突仲裁"""

    def test_add_conflict_resolution_method_exists(self):
        """MemoryStore 有 add_conflict_resolution"""
        from app.services.memory_store import MemoryStore
        assert hasattr(MemoryStore, "add_conflict_resolution")
        assert callable(getattr(MemoryStore, "add_conflict_resolution"))

    def test_conflict_writes_decision_and_learn(self):
        """冲突写入 decision + learn 两层"""
        from app.services.memory_store import MemoryStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(tmpdir)
            store.initialize()

            store.add_conflict_resolution(
                wp_id="wp1",
                actor_a="chatgpt",
                actor_b="claude",
                conflict_desc="Owner completed but reviewer rejected",
                resolution="Entering fix cycle",
                arbiter="system",
            )

            data = store.load()
            assert len(data.decisions) == 1
            assert "chatgpt" in data.decisions[0].symptom
            assert "claude" in data.decisions[0].symptom
            assert len(data.corrections) == 1
            assert data.corrections[0].domain == "conflict"

    def test_conflict_resolution_content(self):
        """写入内容包含 actor_a/actor_b"""
        from app.services.memory_store import MemoryStore

        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(tmpdir)
            store.initialize()

            store.add_conflict_resolution(
                wp_id="wp2",
                actor_a="gate_system",
                actor_b="chatgpt",
                conflict_desc="Gate PASS but RA BLOCK",
                resolution="Human override needed",
                arbiter="chatgpt",
            )

            data = store.load()
            decision = data.decisions[0]
            assert "gate_system" in decision.symptom
            assert "chatgpt" in decision.symptom
            assert decision.source_actor == "chatgpt"
            assert decision.wp_id == "wp2"

            learn = data.corrections[0]
            assert "gate_system" in learn.lesson
            assert "chatgpt" in learn.lesson


# ---------------------------------------------------------------------------
# §2.2.2 last_writer
# ---------------------------------------------------------------------------

class TestLastWriter:
    """§2.2.2: last_writer 填充"""

    def test_last_writer_populated_after_update(self):
        """state_store.update() 后 last_writer 非 None"""
        from app.services.state_store import StateStore
        from app.models.work_package import ExecutionState

        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(projects_path=tmpdir)
            proj_id = "test_proj"
            proj_dir = Path(tmpdir) / proj_id
            proj_dir.mkdir()

            initial = ExecutionState(project_id=proj_id, state_version=1)
            store.save_atomic(proj_id, initial)
            assert initial.last_writer is None

            updated = store.update(proj_id, lambda s: s)
            assert updated.last_writer is not None

    def test_last_writer_has_required_fields(self):
        """包含 host/pid/worker_id"""
        from app.services.state_store import StateStore
        from app.models.work_package import ExecutionState

        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(projects_path=tmpdir)
            proj_id = "test_proj"
            proj_dir = Path(tmpdir) / proj_id
            proj_dir.mkdir()

            initial = ExecutionState(project_id=proj_id, state_version=1)
            store.save_atomic(proj_id, initial)

            updated = store.update(proj_id, lambda s: s)
            lw = updated.last_writer
            assert "host" in lw
            assert "pid" in lw
            assert "worker_id" in lw
            assert isinstance(lw["pid"], int)
            assert lw["worker_id"].startswith("backend-")

    def test_last_writer_persisted_to_disk(self):
        """last_writer 持久化到 state.json"""
        from app.services.state_store import StateStore
        from app.models.work_package import ExecutionState

        with tempfile.TemporaryDirectory() as tmpdir:
            store = StateStore(projects_path=tmpdir)
            proj_id = "test_proj"
            proj_dir = Path(tmpdir) / proj_id
            proj_dir.mkdir()

            initial = ExecutionState(project_id=proj_id, state_version=1)
            store.save_atomic(proj_id, initial)
            store.update(proj_id, lambda s: s)

            loaded = store.load(proj_id)
            assert loaded.last_writer is not None
            assert "host" in loaded.last_writer
            assert "pid" in loaded.last_writer

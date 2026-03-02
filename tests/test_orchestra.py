"""
Orchestra 实现规格测试
v1.2 DevSpec §12 - Orchestra Implementation Spec

测试内容:
- O1: StorageBackend 抽象接口和 LocalBackend 实现
- O2: generate_agents_md_dynamic_section 函数签名
- O3: Orchestra 触发时机（部分）
- O4: 模块结构（验证文件存在）
"""
import pytest
import json
import tempfile
from pathlib import Path
from app.services.storage_backend import StorageBackend, LocalBackend, BoxBackend, GitBackend
from app.services.snapshot_generator import SnapshotGenerator


class TestV12_O_OrchestraCompliance:
    """v1.2 §12 Orchestra 实现规格合规性测试"""

    def test_storage_backend_interface(self):
        """O1: StorageBackend 抽象接口定义正确"""
        # 验证抽象方法存在
        assert hasattr(StorageBackend, 'push_state')
        assert hasattr(StorageBackend, 'pull_state')
        assert hasattr(StorageBackend, 'push_snapshot')
        assert hasattr(StorageBackend, 'push_artifact')
        assert hasattr(StorageBackend, 'pull_artifact')

        # 验证是抽象类
        with pytest.raises(TypeError):
            StorageBackend()

    def test_local_backend_push_pull_state(self):
        """O1: LocalBackend push_state + pull_state"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalBackend(tmpdir)

            # Push state
            test_state = {
                "project_id": "test_proj",
                "state_version": 1,
                "wp_states": {"wp1": {"status": "frozen"}}
            }
            backend.push_state(test_state)

            # Verify file exists
            state_file = Path(tmpdir) / "state.json"
            assert state_file.exists()

            # Pull state
            pulled = backend.pull_state()
            assert pulled["project_id"] == "test_proj"
            assert pulled["state_version"] == 1

    def test_local_backend_push_snapshot(self):
        """O1: LocalBackend push_snapshot"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalBackend(tmpdir)

            # Push snapshot
            snapshot_md = "# AGENTS.md\n## Current Status\n- Phase: E0"
            backend.push_snapshot(snapshot_md)

            # Verify file exists
            agents_file = Path(tmpdir) / "AGENTS.md"
            assert agents_file.exists()
            assert "Current Status" in agents_file.read_text()

    def test_local_backend_push_pull_artifact(self):
        """O1: LocalBackend push_artifact + pull_artifact"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = LocalBackend(tmpdir)

            # Create source artifact
            src_file = Path(tmpdir) / "source.txt"
            src_file.write_text("test artifact content")

            # Push artifact
            backend.push_artifact(str(src_file), "wp1/output.txt")

            # Verify artifact exists
            artifact_file = Path(tmpdir) / "artifacts" / "wp1" / "output.txt"
            assert artifact_file.exists()
            assert artifact_file.read_text() == "test artifact content"

            # Pull artifact
            dst_file = Path(tmpdir) / "pulled.txt"
            backend.pull_artifact("wp1/output.txt", str(dst_file))
            assert dst_file.exists()
            assert dst_file.read_text() == "test artifact content"

    def test_box_backend_fallback(self):
        """O1: BoxBackend 使用 LocalBackend fallback"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = BoxBackend(tmpdir)

            # Should use LocalBackend fallback
            test_state = {"project_id": "test"}
            backend.push_state(test_state)

            state_file = Path(tmpdir) / "state.json"
            assert state_file.exists()

    def test_git_backend_fallback(self):
        """O1: GitBackend 使用 LocalBackend fallback"""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = GitBackend(tmpdir)

            # Should use LocalBackend fallback
            test_state = {"project_id": "test"}
            backend.push_state(test_state)

            state_file = Path(tmpdir) / "state.json"
            assert state_file.exists()

    def test_generate_agents_md_dynamic_section_signature(self):
        """O2: generate_agents_md_dynamic_section 函数签名符合 §12.3"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = SnapshotGenerator(tmpdir)

            # 验证函数存在
            assert hasattr(sg, 'generate_agents_md_dynamic_section')

            # 验证函数签名（4 个参数）
            import inspect
            sig = inspect.signature(sg.generate_agents_md_dynamic_section)
            params = list(sig.parameters.keys())
            assert 'state' in params
            assert 'active_wp_results' in params
            assert 'next_task' in params
            assert 'ra_pending' in params

    def test_generate_agents_md_dynamic_section_output(self):
        """O2: generate_agents_md_dynamic_section 输出格式正确"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = SnapshotGenerator(tmpdir)

            state = {
                "current_phase": "step_3",
                "wp_states": {
                    "wp1": {"status": "executing"},
                    "wp2": {"status": "frozen", "frozen_at": "2025-01-01T00:00:00"}
                }
            }
            active_wp_results = [
                {"wp_id": "wp1", "summary": "In progress", "metrics": {}, "open_issues": []}
            ]
            next_task = {"wp_id": "wp1", "subtask_id": "st1", "description": "Test task"}

            dynamic = sg.generate_agents_md_dynamic_section(
                state=state,
                active_wp_results=active_wp_results,
                next_task=next_task,
                ra_pending=None
            )

            # 验证输出包含必要字段
            assert "Phase" in dynamic
            assert "Active WPs" in dynamic
            assert "Last completed" in dynamic
            assert "Blockers" in dynamic
            assert "Next action" in dynamic
            assert "Cross-model need" in dynamic
            assert "RA pending" in dynamic

    def test_generate_agents_md_dynamic_section_token_budget(self):
        """O2: generate_agents_md_dynamic_section 遵守 < 2000 tokens 约束"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = SnapshotGenerator(tmpdir)

            # 构造大量数据
            state = {
                "current_phase": "step_3",
                "wp_states": {f"wp{i}": {"status": "executing"} for i in range(50)}
            }
            active_wp_results = [
                {
                    "wp_id": f"wp{i}",
                    "summary": "x" * 500,  # 长摘要
                    "metrics": {f"m{j}": {"value": j} for j in range(20)},
                    "open_issues": [f"issue{k}" for k in range(10)]
                }
                for i in range(20)
            ]

            dynamic = sg.generate_agents_md_dynamic_section(
                state=state,
                active_wp_results=active_wp_results,
                next_task=None,
                ra_pending=None
            )

            # 验证长度 < 6000 chars (约 2000 tokens)
            assert len(dynamic) <= 6000

    def test_update_agents_md_replaces_auto_generated_section(self):
        """O2: update_agents_md 正确替换 AUTO-GENERATED 区间"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = SnapshotGenerator(tmpdir)

            # 初始化 AGENTS.md
            sg.initialize_agents_md("Test Project")

            # 更新动态 section
            new_dynamic = "- **Phase**: E1_EXECUTING\n- **Active WPs**: wp1"
            sg.update_agents_md(new_dynamic)

            # 验证更新
            content = sg.get_agents_md_content()
            assert "E1_EXECUTING" in content
            assert "<!-- AUTO-GENERATED:" in content
            assert "<!-- END AUTO-GENERATED -->" in content

            # 验证静态部分未改变
            assert "Project Overview" in content
            assert "Red Lines" in content

    def test_backward_compat_generate_dynamic_section(self):
        """O2: generate_dynamic_section 向后兼容别名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            sg = SnapshotGenerator(tmpdir)

            # 验证旧函数名仍然可用
            assert hasattr(sg, 'generate_dynamic_section')

            state = {"current_phase": "step_3", "wp_states": {}}
            dynamic = sg.generate_dynamic_section(state=state)

            # 验证输出格式相同
            assert "Phase" in dynamic
            assert "Active WPs" in dynamic

    def test_storage_backend_module_exists(self):
        """O4: storage_backend.py 模块存在"""
        try:
            from app.services import storage_backend
            assert hasattr(storage_backend, 'StorageBackend')
            assert hasattr(storage_backend, 'LocalBackend')
            assert hasattr(storage_backend, 'BoxBackend')
            assert hasattr(storage_backend, 'GitBackend')
        except ImportError:
            pytest.fail("storage_backend module not found")

    def test_snapshot_generator_module_exists(self):
        """O4: snapshot_generator.py 模块存在"""
        try:
            from app.services import snapshot_generator
            assert hasattr(snapshot_generator, 'SnapshotGenerator')
        except ImportError:
            pytest.fail("snapshot_generator module not found")

    def test_state_store_module_exists(self):
        """O4: state_store.py 模块存在"""
        try:
            from app.services import state_store
            assert hasattr(state_store, 'StateStore')
        except ImportError:
            pytest.fail("state_store module not found")

    def test_memory_store_module_exists(self):
        """O4: memory_store.py 模块存在"""
        try:
            from app.services import memory_store
            assert hasattr(memory_store, 'MemoryStore')
        except ImportError:
            pytest.fail("memory_store module not found")

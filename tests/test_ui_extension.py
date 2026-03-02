"""
UI 扩展测试
v1.2 DevSpec §14 - UI 扩展

测试内容:
- U1: Memory Browser 组件存在
- U2: Session Log Viewer 组件存在
- U3: RA Dashboard 组件存在
- U4: RA Override 按钮功能（ChatGPT BLOCK 时可 override）
"""
import pytest


class TestV12_U_UIExtensionCompliance:
    """v1.2 §14 UI 扩展合规性测试"""

    def test_memory_browser_component_exists(self):
        """U1: Memory Browser 组件存在"""
        # 验证前端组件文件存在
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        memory_browser = frontend_path / "components" / "Memory" / "MemoryBrowser.tsx"

        assert memory_browser.exists(), "MemoryBrowser.tsx 组件不存在"

    def test_session_log_viewer_component_exists(self):
        """U2: Session Log Viewer 组件存在"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        session_log_viewer = frontend_path / "components" / "SessionLog" / "SessionLogViewer.tsx"

        assert session_log_viewer.exists(), "SessionLogViewer.tsx 组件不存在"

    def test_ra_dashboard_component_exists(self):
        """U3: RA Dashboard 组件存在"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        ra_dashboard = frontend_path / "components" / "RA" / "RADashboard.tsx"

        assert ra_dashboard.exists(), "RADashboard.tsx 组件不存在"

    def test_ra_dashboard_has_override_button(self):
        """U4: RA Dashboard 包含 Override 按钮"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        ra_dashboard = frontend_path / "components" / "RA" / "RADashboard.tsx"

        content = ra_dashboard.read_text(encoding='utf-8')

        # 验证包含 Override 按钮
        assert "Override" in content, "RADashboard 缺少 Override 按钮"
        assert "BLOCK" in content, "RADashboard 未检查 BLOCK 状态"
        assert "override" in content.lower(), "RADashboard 缺少 override 功能"

    def test_ra_override_backend_endpoint_exists(self):
        """U4: RA Override 后端接口存在"""
        from pathlib import Path
        backend_path = Path(__file__).parent.parent
        readiness_api = backend_path / "app" / "api" / "readiness.py"

        content = readiness_api.read_text(encoding='utf-8')

        # 验证包含 override 端点
        assert "/override" in content, "readiness.py 缺少 /override 端点"
        assert "override_ra" in content or "override" in content, "readiness.py 缺少 override 函数"

    def test_memory_browser_integrated_in_project_detail(self):
        """U1: Memory Browser 已集成到 ProjectDetail 页面"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        project_detail = frontend_path / "pages" / "ProjectDetail.tsx"

        content = project_detail.read_text(encoding='utf-8')

        assert "MemoryBrowser" in content, "ProjectDetail 未导入 MemoryBrowser"
        assert "<MemoryBrowser" in content, "ProjectDetail 未使用 MemoryBrowser 组件"

    def test_session_log_viewer_integrated_in_project_detail(self):
        """U2: Session Log Viewer 已集成到 ProjectDetail 页面"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        project_detail = frontend_path / "pages" / "ProjectDetail.tsx"

        content = project_detail.read_text(encoding='utf-8')

        assert "SessionLogViewer" in content, "ProjectDetail 未导入 SessionLogViewer"
        assert "<SessionLogViewer" in content, "ProjectDetail 未使用 SessionLogViewer 组件"

    def test_ra_dashboard_integrated_in_project_detail(self):
        """U3: RA Dashboard 已集成到 ProjectDetail 页面"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        project_detail = frontend_path / "pages" / "ProjectDetail.tsx"

        content = project_detail.read_text(encoding='utf-8')

        assert "RADashboard" in content, "ProjectDetail 未导入 RADashboard"
        assert "<RADashboard" in content, "ProjectDetail 未使用 RADashboard 组件"

    def test_ra_override_modal_exists(self):
        """U4: RA Override Modal 存在"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        ra_dashboard = frontend_path / "components" / "RA" / "RADashboard.tsx"

        content = ra_dashboard.read_text(encoding='utf-8')

        # 验证包含 Modal 组件
        assert "Modal" in content, "RADashboard 缺少 Modal 组件"
        assert "Override BLOCK" in content, "RADashboard Modal 标题不正确"
        assert "overrideReason" in content or "reason" in content, "RADashboard 缺少 override 原因输入"

    def test_ra_override_only_for_block_verdict(self):
        """U4: RA Override 按钮仅在 BLOCK 判定时显示"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"
        ra_dashboard = frontend_path / "components" / "RA" / "RADashboard.tsx"

        content = ra_dashboard.read_text(encoding='utf-8')

        # 验证 Override 按钮条件渲染
        assert "verdict === 'BLOCK'" in content or 'verdict === "BLOCK"' in content, \
            "RADashboard Override 按钮未检查 BLOCK 条件"

    def test_all_ui_components_exported(self):
        """验证所有 UI 组件正确导出"""
        from pathlib import Path
        frontend_path = Path(__file__).parent.parent.parent / "frontend" / "src"

        # 检查 index.ts 导出
        memory_index = frontend_path / "components" / "Memory" / "index.ts"
        if memory_index.exists():
            content = memory_index.read_text(encoding='utf-8')
            assert "MemoryBrowser" in content, "Memory/index.ts 未导出 MemoryBrowser"

        sessionlog_index = frontend_path / "components" / "SessionLog" / "index.ts"
        if sessionlog_index.exists():
            content = sessionlog_index.read_text(encoding='utf-8')
            assert "SessionLogViewer" in content, "SessionLog/index.ts 未导出 SessionLogViewer"

        ra_index = frontend_path / "components" / "RA" / "index.ts"
        if ra_index.exists():
            content = ra_index.read_text(encoding='utf-8')
            assert "RADashboard" in content, "RA/index.ts 未导出 RADashboard"

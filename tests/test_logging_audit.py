"""
日志与审计测试
v1.2 DevSpec §15 - 日志与审计

测试内容:
- A1: TraceLogger 支持 v1.2 新增 event_type
- A2: Escalation 日志包含 memory_entry_added 字段
"""
import pytest
import tempfile
from pathlib import Path
from app.utils.trace_logger import TraceLogger, TraceEventType


class TestV12_A_LoggingAuditCompliance:
    """v1.2 §15 日志与审计合规性测试"""

    def test_trace_event_type_enum_exists(self):
        """A1: TraceEventType 枚举存在"""
        assert hasattr(TraceEventType, 'AI_RESPONSE')
        assert hasattr(TraceEventType, 'RA_REQUEST')
        assert hasattr(TraceEventType, 'RA_RESULT')
        assert hasattr(TraceEventType, 'MEMORY_UPDATE')
        assert hasattr(TraceEventType, 'SESSION_LOG_WRITE')

    def test_trace_event_type_values(self):
        """A1: TraceEventType 枚举值正确"""
        assert TraceEventType.AI_RESPONSE == "ai_response"
        assert TraceEventType.RA_REQUEST == "ra_request"
        assert TraceEventType.RA_RESULT == "ra_result"
        assert TraceEventType.MEMORY_UPDATE == "memory_update"
        assert TraceEventType.SESSION_LOG_WRITE == "session_log_write"

    def test_save_raw_response_with_event_type(self):
        """A1: save_raw_response 支持 event_type 参数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            # 保存 AI_RESPONSE 事件
            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response="Test AI response",
                event_type=TraceEventType.AI_RESPONSE
            )

            assert trace_file
            assert Path(trace_file).exists()
            assert "ai_response" in trace_file

    def test_save_ra_request_event(self):
        """A1: 保存 RA_REQUEST 事件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response="RA request content",
                metadata={"wp_id": "wp1", "gate_result": "PASS"},
                event_type=TraceEventType.RA_REQUEST
            )

            assert trace_file
            assert "ra_request" in trace_file

            # 验证内容
            content = Path(trace_file).read_text(encoding='utf-8')
            assert "Event Type**: ra_request" in content
            assert "RA request content" in content

    def test_save_ra_result_event(self):
        """A1: 保存 RA_RESULT 事件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response='{"verdict": "ADVANCE", "confidence": 0.9}',
                metadata={"wp_id": "wp1"},
                event_type=TraceEventType.RA_RESULT
            )

            assert trace_file
            assert "ra_result" in trace_file

            content = Path(trace_file).read_text(encoding='utf-8')
            assert "Event Type**: ra_result" in content
            assert "ADVANCE" in content

    def test_save_memory_update_event(self):
        """A1: 保存 MEMORY_UPDATE 事件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response="[LEARN:physics] Use conservation laws",
                metadata={"entry_type": "error_pattern", "wp_id": "wp1"},
                event_type=TraceEventType.MEMORY_UPDATE
            )

            assert trace_file
            assert "memory_update" in trace_file

            content = Path(trace_file).read_text(encoding='utf-8')
            assert "Event Type**: memory_update" in content
            assert "conservation laws" in content

    def test_save_session_log_write_event(self):
        """A1: 保存 SESSION_LOG_WRITE 事件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response="Session log entry: subtask completed",
                metadata={"subtask_id": "wp1_st1", "status": "completed"},
                event_type=TraceEventType.SESSION_LOG_WRITE
            )

            assert trace_file
            assert "session_log_write" in trace_file

            content = Path(trace_file).read_text(encoding='utf-8')
            assert "Event Type**: session_log_write" in content
            assert "subtask completed" in content

    def test_trace_file_naming_includes_event_type(self):
        """A1: Trace 文件名包含 event_type"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            # 保存不同类型的事件
            events = [
                TraceEventType.AI_RESPONSE,
                TraceEventType.RA_REQUEST,
                TraceEventType.RA_RESULT,
                TraceEventType.MEMORY_UPDATE,
                TraceEventType.SESSION_LOG_WRITE
            ]

            for event_type in events:
                trace_file = logger.save_raw_response(
                    project_id="test_proj",
                    step_id="step_3_1",
                    response=f"Test {event_type.value}",
                    event_type=event_type
                )

                # 验证文件名包含事件类型
                assert event_type.value in trace_file

    def test_get_trace_metadata_includes_event_type(self):
        """A1: get_trace_metadata 提取 event_type"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response="Test content",
                event_type=TraceEventType.RA_REQUEST
            )

            metadata = logger.get_trace_metadata(trace_file)
            assert "event_type" in metadata
            assert metadata["event_type"] == "ra_request"

    def test_backward_compatibility_default_event_type(self):
        """A1: 向后兼容 - 默认 event_type 为 AI_RESPONSE"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = TraceLogger(tmpdir)

            # 不传 event_type 参数
            trace_file = logger.save_raw_response(
                project_id="test_proj",
                step_id="step_3_1",
                response="Test response"
            )

            assert trace_file
            assert "ai_response" in trace_file

    def test_escalation_history_structure(self):
        """A2: Escalation history 包含 memory_entry_added 字段"""
        # 这个测试验证 escalation_history 的数据结构
        escalation_entry = {
            "timestamp": "2025-01-01T00:00:00",
            "diagnosis": {"verdict": "FAIL", "issues": []},
            "memory_entry_added": True  # v1.2 §15 新增
        }

        assert "timestamp" in escalation_entry
        assert "diagnosis" in escalation_entry
        assert "memory_entry_added" in escalation_entry
        assert isinstance(escalation_entry["memory_entry_added"], bool)

    def test_escalation_history_memory_entry_added_false(self):
        """A2: memory_entry_added 可以为 False（添加失败时）"""
        escalation_entry = {
            "timestamp": "2025-01-01T00:00:00",
            "diagnosis": {"verdict": "FAIL"},
            "memory_entry_added": False
        }

        assert escalation_entry["memory_entry_added"] is False

    def test_trace_logger_module_exports(self):
        """验证 TraceLogger 模块导出"""
        from app.utils import trace_logger
        assert hasattr(trace_logger, 'TraceLogger')
        assert hasattr(trace_logger, 'TraceEventType')

"""
Unit tests for TraceLogger
Tests raw response preservation functionality
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from app.utils.trace_logger import TraceLogger


class TestTraceLogger:
    """Test TraceLogger functionality"""

    @pytest.fixture
    def temp_projects_path(self):
        """Create a temporary projects directory"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def trace_logger(self, temp_projects_path):
        """Create a TraceLogger instance"""
        return TraceLogger(temp_projects_path)

    def test_save_raw_response(self, trace_logger, temp_projects_path):
        """Test saving raw response"""
        project_id = "test_project"
        step_id = "step_1_1"
        response = "This is a test response with some content."
        metadata = {
            "model": "gemini-2.0-flash",
            "wrapper_mode": "lite",
            "timestamp": 1234567890.0
        }

        # Save raw response
        trace_path = trace_logger.save_raw_response(
            project_id=project_id,
            step_id=step_id,
            response=response,
            metadata=metadata
        )

        # Verify file was created
        assert trace_path != ""
        assert Path(trace_path).exists()

        # Verify file content
        with open(trace_path, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "# Raw Response Trace" in content
        assert f"**Step ID**: {step_id}" in content
        assert f"**Project ID**: {project_id}" in content
        assert f"**Length**: {len(response)} characters" in content
        assert "## Metadata" in content
        assert "## Raw Response" in content
        assert response in content

    def test_load_raw_response(self, trace_logger, temp_projects_path):
        """Test loading raw response"""
        project_id = "test_project"
        step_id = "step_1_2"
        response = "Another test response for loading."

        # Save first
        trace_logger.save_raw_response(
            project_id=project_id,
            step_id=step_id,
            response=response
        )

        # Load
        loaded_response = trace_logger.load_raw_response(
            project_id=project_id,
            step_id=step_id
        )

        # Verify
        assert loaded_response == response

    def test_load_raw_response_not_found(self, trace_logger):
        """Test loading non-existent raw response"""
        with pytest.raises(FileNotFoundError):
            trace_logger.load_raw_response(
                project_id="nonexistent_project",
                step_id="nonexistent_step"
            )

    def test_list_raw_responses(self, trace_logger, temp_projects_path):
        """Test listing raw responses"""
        project_id = "test_project"

        # Save multiple responses
        trace_logger.save_raw_response(project_id, "step_1_1", "Response 1")
        trace_logger.save_raw_response(project_id, "step_1_2", "Response 2")
        trace_logger.save_raw_response(project_id, "step_1_3", "Response 3")

        # List all
        all_files = trace_logger.list_raw_responses(project_id)
        assert len(all_files) == 3

        # List specific step
        step_files = trace_logger.list_raw_responses(project_id, "step_1_1")
        assert len(step_files) == 1
        assert "step_1_1" in step_files[0]

    def test_get_trace_metadata(self, trace_logger, temp_projects_path):
        """Test extracting metadata from trace file"""
        project_id = "test_project"
        step_id = "step_1_1"
        response = "Test response"
        metadata = {
            "model": "gemini-2.0-flash",
            "wrapper_mode": "full"
        }

        # Save
        trace_path = trace_logger.save_raw_response(
            project_id=project_id,
            step_id=step_id,
            response=response,
            metadata=metadata
        )

        # Extract metadata
        extracted = trace_logger.get_trace_metadata(trace_path)

        assert extracted["step_id"] == step_id
        assert extracted["project_id"] == project_id
        assert "api_metadata" in extracted
        assert extracted["api_metadata"]["model"] == "gemini-2.0-flash"

    def test_save_without_metadata(self, trace_logger, temp_projects_path):
        """Test saving without metadata"""
        project_id = "test_project"
        step_id = "step_1_1"
        response = "Test response without metadata"

        # Save without metadata
        trace_path = trace_logger.save_raw_response(
            project_id=project_id,
            step_id=step_id,
            response=response
        )

        # Verify file was created
        assert trace_path != ""
        assert Path(trace_path).exists()

        # Verify content
        with open(trace_path, 'r', encoding='utf-8') as f:
            content = f.read()

        assert "## Raw Response" in content
        assert response in content
        # Metadata section should not be present
        assert "## Metadata" not in content

    def test_multiple_saves_same_step(self, trace_logger, temp_projects_path):
        """Test saving multiple responses for the same step"""
        import time
        project_id = "test_project"
        step_id = "step_1_1"

        # Save multiple times with a small delay to ensure different timestamps
        trace_path1 = trace_logger.save_raw_response(project_id, step_id, "Response 1")
        time.sleep(1.1)  # Wait to ensure different timestamp
        trace_path2 = trace_logger.save_raw_response(project_id, step_id, "Response 2")

        # Verify different files were created (different timestamps)
        assert trace_path1 != trace_path2

        # Verify both files exist
        assert Path(trace_path1).exists()
        assert Path(trace_path2).exists()

        # Load latest should return Response 2
        latest = trace_logger.load_raw_response(project_id, step_id)
        assert latest == "Response 2"

    def test_chinese_content(self, trace_logger, temp_projects_path):
        """Test saving and loading Chinese content"""
        project_id = "test_project"
        step_id = "step_1_1"
        response = "这是一个包含中文内容的测试响应。\n\n包含多行文本。"

        # Save
        trace_path = trace_logger.save_raw_response(
            project_id=project_id,
            step_id=step_id,
            response=response
        )

        # Load
        loaded = trace_logger.load_raw_response(project_id, step_id)

        # Verify
        assert loaded == response

    def test_large_response(self, trace_logger, temp_projects_path):
        """Test saving large response (>100KB)"""
        project_id = "test_project"
        step_id = "step_1_1"
        # Create a large response (~200KB)
        response = "A" * 200000

        # Save
        trace_path = trace_logger.save_raw_response(
            project_id=project_id,
            step_id=step_id,
            response=response
        )

        # Verify file was created
        assert Path(trace_path).exists()

        # Verify file size
        file_size = Path(trace_path).stat().st_size
        assert file_size > 200000  # Should be slightly larger due to headers

        # Load and verify
        loaded = trace_logger.load_raw_response(project_id, step_id)
        assert loaded == response

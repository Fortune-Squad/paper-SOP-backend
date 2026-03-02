"""
Unit tests for Sidecar Meta Mode (v4.1)
Tests the sidecar_meta wrapper mode and extraction
"""
import pytest
import json
from pathlib import Path
from app.services.agentic_wrapper import AgenticWrapper


class TestSidecarMetaMode:
    """Test suite for sidecar meta mode"""

    @pytest.fixture
    def wrapper(self, tmp_path):
        """Create AgenticWrapper instance for testing"""
        # Create a temporary config file
        config_path = tmp_path / "test_config.yaml"
        config_path.write_text("""
agentic_wrapper:
  enabled: true
  validation:
    require_plan: true
    require_evidence: true
    min_confidence: 0.7
""")
        return AgenticWrapper(str(config_path), mode="sidecar_meta")

    def test_wrap_sidecar_meta_basic(self, wrapper):
        """Test basic sidecar_meta wrapping"""
        prompt = "Generate a literature review"
        wrapped = wrapper.wrap_prompt(prompt, mode="sidecar_meta")

        # Check that wrapped prompt contains sidecar meta instructions
        assert "<<<SIDECAR_META>>>" in wrapped
        assert "<<<END_SIDECAR_META>>>" in wrapped
        assert "TWO-PART OUTPUT FORMAT" in wrapped
        assert "Sidecar Meta Mode" in wrapped
        assert prompt in wrapped

    def test_extract_sidecar_meta_valid(self, wrapper):
        """Test extraction of valid sidecar meta format"""
        response = """---
doc_type: literature_review
---

# Literature Review

This is a complete literature review with YAML front-matter.

## Section 1
Content here.

## Section 2
More content.

<<<SIDECAR_META>>>
{
  "evidence": [
    {"title": "Paper 1", "venue": "ICML 2024", "doi": "10.1234/icml.2024.1", "finding": "Key finding 1"},
    {"title": "Paper 2", "venue": "NeurIPS 2024", "doi": "10.5678/neurips.2024.2", "finding": "Key finding 2"}
  ],
  "confidence_score": 0.85,
  "confidence_justification": "High confidence based on multiple sources",
  "plan": ["Step 1", "Step 2", "Step 3"],
  "risks": ["Risk 1", "Risk 2"],
  "verification": ["Check 1", "Check 2"]
}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Check extraction success
        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta"
        assert result["warnings"] == []

        # Check deliverable content (should not include sidecar meta)
        assert "<<<SIDECAR_META>>>" not in result["content"]
        assert "<<<END_SIDECAR_META>>>" not in result["content"]
        assert "# Literature Review" in result["content"]
        assert "doc_type: literature_review" in result["content"]

        # Check meta extraction
        assert result["meta"] is not None
        assert "evidence" in result["meta"]
        assert "confidence_score" in result["meta"]
        assert "confidence_justification" in result["meta"]
        assert "plan" in result["meta"]
        assert "risks" in result["meta"]
        assert "verification" in result["meta"]

        # Validate meta content
        assert len(result["meta"]["evidence"]) == 2
        assert result["meta"]["confidence_score"] == 0.85
        assert len(result["meta"]["plan"]) == 3
        assert len(result["meta"]["risks"]) == 2
        assert len(result["meta"]["verification"]) == 2

    def test_extract_sidecar_meta_minimal(self, wrapper):
        """Test extraction with minimal meta (only required fields)"""
        response = """Complete deliverable content here.

<<<SIDECAR_META>>>
{
  "evidence": [{"title": "Paper 1", "venue": "ICML 2024", "doi": "10.1234/icml.2024.1", "finding": "Finding"}],
  "confidence_score": 0.75,
  "confidence_justification": "Moderate confidence"
}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta"
        assert result["meta"] is not None
        assert len(result["meta"]["evidence"]) == 1
        assert result["meta"]["confidence_score"] == 0.75

    def test_extract_sidecar_meta_invalid_json(self, wrapper):
        """Test extraction with invalid JSON in sidecar meta"""
        response = """Complete deliverable content.

<<<SIDECAR_META>>>
{
  "evidence": [invalid json here],
  "confidence_score": 0.85
}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Should still extract deliverable even if meta JSON is invalid
        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta_partial"
        assert "Complete deliverable content." in result["content"]
        assert result["meta"] is None
        assert len(result["warnings"]) > 0
        assert any("parse" in w.lower() for w in result["warnings"])

    def test_extract_sidecar_meta_missing_delimiters(self, wrapper):
        """Test extraction when sidecar meta delimiters are missing"""
        response = """Complete deliverable without sidecar meta."""

        result = wrapper.extract_deliverables(response)

        # Should fallback to full response
        assert result["extraction_method"] == "fallback_full_response"
        assert result["content"] == response
        assert result["meta"] is None

    def test_extract_sidecar_meta_with_yaml_frontmatter(self, wrapper):
        """Test extraction with YAML front-matter in deliverable"""
        response = """---
doc_type: reference_qa_report
version: 1.0
---

# Reference QA Report

Complete report content with YAML front-matter.

<<<SIDECAR_META>>>
{
  "evidence": [{"title": "Paper", "venue": "Venue", "doi": "10.1234/test", "finding": "Finding"}],
  "confidence_score": 0.9,
  "confidence_justification": "High confidence"
}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta"
        assert "doc_type: reference_qa_report" in result["content"]
        assert "<<<SIDECAR_META>>>" not in result["content"]
        assert result["meta"]["confidence_score"] == 0.9

    def test_extract_sidecar_meta_with_bibtex(self, wrapper):
        """Test extraction with BibTeX entries in deliverable"""
        response = """@article{smith2024,
  title={Test Paper},
  author={Smith, John},
  journal={Test Journal},
  year={2024}
}

@inproceedings{jones2024,
  title={Another Paper},
  author={Jones, Jane},
  booktitle={Test Conference},
  year={2024}
}

<<<SIDECAR_META>>>
{
  "evidence": [{"title": "Paper", "venue": "Venue", "doi": "10.1234/test", "finding": "Finding"}],
  "confidence_score": 0.88,
  "confidence_justification": "Good confidence"
}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta"
        assert "@article{smith2024" in result["content"]
        assert "@inproceedings{jones2024" in result["content"]
        assert "<<<SIDECAR_META>>>" not in result["content"]

    def test_save_sidecar_meta(self, tmp_path):
        """Test saving sidecar meta to file"""
        meta = {
            "evidence": [
                {"title": "Paper 1", "venue": "ICML 2024", "doi": "10.1234/test", "finding": "Finding 1"}
            ],
            "confidence_score": 0.85,
            "confidence_justification": "High confidence",
            "plan": ["Step 1", "Step 2"],
            "risks": ["Risk 1", "Risk 2"],
            "verification": ["Check 1", "Check 2"]
        }

        project_path = tmp_path / "test_project"
        project_path.mkdir()
        step_id = "step_1_1"

        # Save sidecar meta
        meta_path = AgenticWrapper.save_sidecar_meta(meta, project_path, step_id)

        # Verify file was created
        assert Path(meta_path).exists()
        assert Path(meta_path).name == f"{step_id}_meta.json"

        # Verify content
        with open(meta_path, 'r', encoding='utf-8') as f:
            saved_meta = json.load(f)

        assert saved_meta == meta
        assert saved_meta["confidence_score"] == 0.85
        assert len(saved_meta["evidence"]) == 1
        assert len(saved_meta["plan"]) == 2

    def test_get_sidecar_meta_path(self, tmp_path):
        """Test getting sidecar meta file path"""
        project_path = tmp_path / "test_project"
        step_id = "step_1_2"

        meta_path = AgenticWrapper.get_sidecar_meta_path(project_path, step_id)

        assert meta_path.name == f"{step_id}_meta.json"
        assert meta_path.parent.name == "logs"
        assert str(project_path) in str(meta_path)

    def test_sidecar_meta_mode_priority(self, wrapper):
        """Test that sidecar_meta has higher priority than meta_tail"""
        response = """Deliverable content.

<<<SIDECAR_META>>>
{"evidence": [], "confidence_score": 0.9, "confidence_justification": "Sidecar"}
<<<END_SIDECAR_META>>>

<<<META_JSON>>>
{"evidence": [], "confidence_score": 0.8, "confidence_justification": "Meta tail"}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Should use sidecar_meta (higher priority)
        assert result["extraction_method"] == "sidecar_meta"
        assert result["meta"]["confidence_score"] == 0.9
        assert result["meta"]["confidence_justification"] == "Sidecar"

    def test_sidecar_meta_with_chinese_content(self, wrapper):
        """Test sidecar meta with Chinese content"""
        response = """---
doc_type: 文献综述
---

# 文献综述

这是一个包含中文内容的完整文献综述。

## 第一部分
中文内容。

<<<SIDECAR_META>>>
{
  "evidence": [{"title": "论文标题", "venue": "会议名称 2024", "doi": "10.1234/test", "finding": "关键发现"}],
  "confidence_score": 0.85,
  "confidence_justification": "基于多个来源的高置信度"
}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta"
        assert "文献综述" in result["content"]
        assert "中文内容" in result["content"]
        assert result["meta"]["evidence"][0]["title"] == "论文标题"

    def test_sidecar_meta_large_content(self, wrapper):
        """Test sidecar meta with large deliverable content"""
        # Generate large content (>10k chars)
        large_content = "# Large Document\n\n" + ("This is a paragraph. " * 500)

        response = f"""{large_content}

<<<SIDECAR_META>>>
{{
  "evidence": [{{"title": "Paper", "venue": "Venue", "doi": "10.1234/test", "finding": "Finding"}}],
  "confidence_score": 0.85,
  "confidence_justification": "Good confidence"
}}
<<<END_SIDECAR_META>>>
"""

        result = wrapper.extract_deliverables(response)

        assert result["success"] is True
        assert result["extraction_method"] == "sidecar_meta"
        assert len(result["content"]) > 10000
        assert "<<<SIDECAR_META>>>" not in result["content"]
        assert result["meta"]["confidence_score"] == 0.85


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

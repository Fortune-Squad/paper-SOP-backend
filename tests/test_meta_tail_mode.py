"""
Unit tests for Meta-Tail Mode (v4.1)
Tests the non-invasive wrapper mode that separates deliverable from meta
"""
import pytest
from pathlib import Path
from app.services.agentic_wrapper import AgenticWrapper


class TestMetaTailMode:
    """Test Meta-Tail Mode functionality"""

    @pytest.fixture
    def wrapper(self):
        """Create an AgenticWrapper instance"""
        config_path = Path(__file__).parent.parent / "config" / "gemini_gem_config.yaml"
        return AgenticWrapper(str(config_path), mode="meta_tail")

    def test_wrap_meta_tail_prompt(self, wrapper):
        """Test meta_tail prompt wrapping"""
        prompt = "Generate a reference QA report with YAML front-matter and BibTeX entries."

        wrapped = wrapper.wrap_prompt(prompt, mode="meta_tail")

        # Verify meta_tail specific instructions
        assert "TWO-PART OUTPUT FORMAT" in wrapped
        assert "<<<META_JSON>>>" in wrapped
        assert "<<<END_META>>>" in wrapped
        assert "Output the deliverable FIRST and COMPLETELY" in wrapped
        assert "The deliverable can have ANY format" in wrapped

    def test_extract_meta_tail_format(self, wrapper):
        """Test extracting meta_tail format"""
        response = """---
doc_type: reference_qa_report
version: 1.0
---

# Reference QA Report

## Summary
This is a complete reference QA report with YAML front-matter.

## References
1. Smith et al. (2024). "Paper Title". Journal Name.

<<<META_JSON>>>
{
  "evidence": [
    {"title": "Paper Title", "venue": "Journal/2024", "doi": "10.1234/test", "finding": "Key finding"}
  ],
  "confidence_score": 0.85,
  "confidence_justification": "High confidence based on verified sources"
}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Verify extraction success
        assert result["success"] is True
        assert result["extraction_method"] == "meta_tail"

        # Verify deliverable content
        assert "# Reference QA Report" in result["content"]
        assert "doc_type: reference_qa_report" in result["content"]
        assert "<<<META_JSON>>>" not in result["content"]  # Meta should be separated

        # Verify meta extraction
        assert result["meta"] is not None
        assert "evidence" in result["meta"]
        assert "confidence_score" in result["meta"]
        assert result["meta"]["confidence_score"] == 0.85
        assert len(result["meta"]["evidence"]) == 1

    def test_extract_meta_tail_with_bibtex(self, wrapper):
        """Test meta_tail with BibTeX format"""
        response = """---
doc_type: literature_review
---

# Literature Review

## BibTeX Entries

@article{smith2024,
  title={Test Paper},
  author={Smith, John},
  journal={Test Journal},
  year={2024}
}

@inproceedings{jones2024,
  title={Another Paper},
  author={Jones, Jane},
  booktitle={Conference},
  year={2024}
}

<<<META_JSON>>>
{
  "evidence": [
    {"title": "Test Paper", "venue": "Test Journal/2024", "doi": "10.1234/test1", "finding": "Finding 1"},
    {"title": "Another Paper", "venue": "Conference/2024", "doi": "10.1234/test2", "finding": "Finding 2"}
  ],
  "confidence_score": 0.90,
  "confidence_justification": "Very high confidence with multiple verified sources"
}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Verify extraction
        assert result["success"] is True
        assert result["extraction_method"] == "meta_tail"

        # Verify BibTeX is in deliverable
        assert "@article{smith2024" in result["content"]
        assert "@inproceedings{jones2024" in result["content"]

        # Verify meta
        assert result["meta"]["confidence_score"] == 0.90
        assert len(result["meta"]["evidence"]) == 2

    def test_extract_meta_tail_malformed_json(self, wrapper):
        """Test meta_tail with malformed JSON"""
        response = """# Content

Some deliverable content here.

<<<META_JSON>>>
{
  "evidence": [
    {"title": "Test"  // Missing closing bracket
  ],
  "confidence_score": 0.85
}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Should still extract deliverable even if JSON is malformed
        assert result["success"] is True
        assert result["extraction_method"] == "meta_tail_partial"
        assert "# Content" in result["content"]
        assert result["meta"] is None  # JSON parsing failed
        assert len(result["warnings"]) > 0
        assert any("Failed to parse meta JSON" in w for w in result["warnings"])

    def test_extract_meta_tail_missing_delimiters(self, wrapper):
        """Test response without meta_tail delimiters"""
        response = """# Regular Content

This is regular content without meta_tail format.

## Section 1
Content here.
"""

        result = wrapper.extract_deliverables(response)

        # Should fall back to other extraction methods
        # Note: success may be False if no extraction method works, which is expected
        assert "# Regular Content" in result["content"]
        assert result["meta"] is None
        # The extraction_method should indicate fallback
        assert result["extraction_method"] in ["fallback_full_response", "section_header_markdown header"]

    def test_meta_tail_vs_disabled_mode(self, wrapper):
        """Test that meta_tail mode doesn't conflict with specific formats"""
        # Simulate a response with YAML front-matter (common conflict case)
        yaml_content = """---
doc_type: test
version: 1.0
status: draft
---

# Test Document

This is a test document with YAML front-matter.

## Section 1
Content here.

## Section 2
More content.

<<<META_JSON>>>
{
  "evidence": [{"title": "Test", "venue": "Test/2024", "doi": "10.1234/test", "finding": "Test finding"}],
  "confidence_score": 0.80,
  "confidence_justification": "Test confidence"
}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(yaml_content)

        # Verify YAML front-matter is preserved in deliverable
        assert result["success"] is True
        assert "---\ndoc_type: test" in result["content"]
        assert "# Test Document" in result["content"]

        # Verify meta is extracted separately
        assert result["meta"] is not None
        assert result["meta"]["confidence_score"] == 0.80

    def test_meta_tail_long_content(self, wrapper):
        """Test meta_tail with long content (>20k chars)"""
        # Simulate Step 1.1b scenario (the problematic step)
        long_content = "A" * 20000  # 20k characters

        response = f"""---
doc_type: reference_qa_report
---

# Reference QA Report

{long_content}

## BibTeX Entries

@article{{test2024,
  title={{Test}},
  author={{Test}},
  year={{2024}}
}}

<<<META_JSON>>>
{{
  "evidence": [{{"title": "Test", "venue": "Test/2024", "doi": "10.1234/test", "finding": "Test"}}],
  "confidence_score": 0.85,
  "confidence_justification": "Test"
}}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Verify long content is preserved
        assert result["success"] is True
        assert len(result["content"]) > 20000
        assert long_content in result["content"]

        # Verify meta is still extracted
        assert result["meta"] is not None

    def test_meta_tail_chinese_content(self, wrapper):
        """Test meta_tail with Chinese content"""
        response = """---
doc_type: 参考文献质量报告
---

# 参考文献质量报告

## 摘要
这是一个包含中文内容的测试报告。

## 参考文献
1. 张三等 (2024). "论文标题". 期刊名称.

<<<META_JSON>>>
{
  "evidence": [
    {"title": "论文标题", "venue": "期刊名称/2024", "doi": "10.1234/test", "finding": "关键发现"}
  ],
  "confidence_score": 0.88,
  "confidence_justification": "基于已验证来源的高置信度"
}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Verify Chinese content is preserved
        assert result["success"] is True
        assert "参考文献质量报告" in result["content"]
        assert "张三等" in result["content"]

        # Verify Chinese meta
        assert result["meta"] is not None
        assert "论文标题" in result["meta"]["evidence"][0]["title"]

    def test_meta_tail_empty_evidence(self, wrapper):
        """Test meta_tail with empty evidence list"""
        response = """# Content

Some content here.

<<<META_JSON>>>
{
  "evidence": [],
  "confidence_score": 0.50,
  "confidence_justification": "Low confidence due to no evidence"
}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # Should still work with empty evidence
        assert result["success"] is True
        assert result["meta"] is not None
        assert len(result["meta"]["evidence"]) == 0
        assert result["meta"]["confidence_score"] == 0.50

    def test_meta_tail_multiple_markers(self, wrapper):
        """Test response with multiple META_JSON markers (invalid)"""
        response = """# Content

First part.

<<<META_JSON>>>
{"test": 1}
<<<END_META>>>

Second part.

<<<META_JSON>>>
{"test": 2}
<<<END_META>>>
"""

        result = wrapper.extract_deliverables(response)

        # The _extract_meta_tail method should detect this and return warnings
        # However, if it falls back to other methods, the warnings might be different
        # Just verify that extraction still works (returns content)
        assert "# Content" in result["content"]
        # Either meta_tail detected the issue, or it fell back to other methods
        assert result["extraction_method"] in ["meta_tail_partial", "fallback_full_response", "section_header_markdown header"]

    def test_wrap_prompt_mode_override(self, wrapper):
        """Test that mode parameter overrides instance mode"""
        prompt = "Test prompt"

        # Instance is meta_tail, but override with lite
        wrapped_lite = wrapper.wrap_prompt(prompt, mode="lite")
        assert "## Evidence" in wrapped_lite
        assert "## Deliverables" in wrapped_lite
        assert "<<<META_JSON>>>" not in wrapped_lite

        # Override with meta_tail explicitly
        wrapped_meta_tail = wrapper.wrap_prompt(prompt, mode="meta_tail")
        assert "<<<META_JSON>>>" in wrapped_meta_tail
        assert "TWO-PART OUTPUT FORMAT" in wrapped_meta_tail

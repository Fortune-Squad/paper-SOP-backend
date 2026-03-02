"""
Test improved extract_deliverables() method
测试改进的 extract_deliverables() 方法
"""
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.agentic_wrapper import AgenticWrapper


def test_extract_deliverables():
    """测试 extract_deliverables() 的各种场景"""

    print("=" * 80)
    print("Testing Improved extract_deliverables() Method")
    print("=" * 80)

    # 初始化 Agentic Wrapper
    wrapper = AgenticWrapper("./config/gemini_gem_config.yaml", mode="lite")

    # 测试用例 1: 包裹在代码块中的响应（Step 1.1b 的实际情况）
    print("\n[Test 1] Response wrapped in markdown code block")
    print("-" * 80)

    response_1 = """```yaml
---
doc_type: "00_Reference_QA_Report"
version: "0.1"
status: "draft"
---

### A) Literature Matrix (Enhanced)

| Venue/Year | Title | DOI |
|---|---|---|
| IEEE TAP, 2011 | Near-Field Scanning | 10.1109/TAP.2011.2163722 |

### B) Reference Quality Report
- Total references: 30
- References with DOI: 27 (90%)

### C) Verified References (BibTeX)
```bibtex
@article{test_2011,
  title={Test Article},
  year={2011}
}
```

### D) Action Items
- Add DOI for 3 references
```"""

    extracted_1 = wrapper.extract_deliverables(response_1)
    print(f"Original length: {len(response_1)} chars")
    print(f"Extracted length: {len(extracted_1['content'])} chars")
    print(f"Extraction method: {extracted_1['extraction_method']}")
    print(f"Success: {len(extracted_1['content']) > 500}")
    print(f"\nExtracted preview (first 200 chars):")
    print(extracted_1['content'][:200])

    # 测试用例 2: 标准 Agentic 格式（带 ## Deliverables）
    print("\n\n[Test 2] Standard Agentic format with ## Deliverables")
    print("-" * 80)

    response_2 = """## Plan
- Step 1: Do something
- Step 2: Do something else

## Actions Taken
- Searched databases
- Analyzed results

## Evidence
- Source 1: DOI 10.1234/test
- Source 2: DOI 10.5678/test

## Deliverables

### Literature Matrix

| Title | DOI |
|---|---|
| Test Paper 1 | 10.1234/test1 |
| Test Paper 2 | 10.1234/test2 |

### Quality Report
- Total: 20 papers
- DOI coverage: 95%

## Risks
- Risk 1: Data quality
- Risk 2: Time constraints

## Verification Checklist
- [ ] Verify DOIs
- [ ] Check duplicates

## Confidence Score
0.85 - High confidence based on comprehensive search
"""

    extracted_2 = wrapper.extract_deliverables(response_2)
    print(f"Original length: {len(response_2)} chars")
    print(f"Extracted length: {len(extracted_2['content'])} chars")
    print(f"Extraction method: {extracted_2['extraction_method']}")
    print(f"Success: {'Literature Matrix' in extracted_2['content']}")
    print(f"\nExtracted preview (first 200 chars):")
    print(extracted_2['content'][:200])

    # 测试用例 3: 只有 YAML front-matter 后的内容（无 ## Deliverables）
    print("\n\n[Test 3] YAML front-matter followed by content (no ## Deliverables)")
    print("-" * 80)

    response_3 = """---
doc_type: "00_Deep_Research_Summary"
version: "0.1"
status: "draft"
---

# Deep Research Summary

## Literature Review

This is a comprehensive literature review covering 30 papers
in the field of compressed sensing and antenna measurements.

### Key Findings

1. Compressed sensing reduces measurement time
2. Characteristic modes provide incoherence
3. Physics-driven approaches improve accuracy

## Gap Analysis

Several gaps were identified in the current literature...
"""

    extracted_3 = wrapper.extract_deliverables(response_3)
    print(f"Original length: {len(response_3)} chars")
    print(f"Extracted length: {len(extracted_3['content'])} chars")
    print(f"Extraction method: {extracted_3['extraction_method']}")
    print(f"Success: {'Deep Research Summary' in extracted_3['content']}")
    print(f"\nExtracted preview (first 200 chars):")
    print(extracted_3['content'][:200])

    # 测试用例 4: 嵌套代码块（代码块中包含代码块）
    print("\n\n[Test 4] Nested code blocks")
    print("-" * 80)

    response_4 = """```markdown
---
doc_type: "test"
---

## Content

Here is some code:

```python
def test():
    return "hello"
```

And more content here.
```"""

    extracted_4 = wrapper.extract_deliverables(response_4)
    print(f"Original length: {len(response_4)} chars")
    print(f"Extracted length: {len(extracted_4['content'])} chars")
    print(f"Extraction method: {extracted_4['extraction_method']}")
    print(f"Success: {'def test()' in extracted_4['content']}")
    print(f"\nExtracted preview (first 200 chars):")
    print(extracted_4['content'][:200])

    # 总结
    print("\n\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)

    tests = [
        ("Wrapped in code block", len(extracted_1['content']) > 500),
        ("Standard Agentic format", "Literature Matrix" in extracted_2['content']),
        ("YAML + content", "Deep Research Summary" in extracted_3['content']),
        ("Nested code blocks", "def test()" in extracted_4['content']),
    ]

    passed = sum(1 for _, result in tests if result)
    total = len(tests)

    for test_name, result in tests:
        status = "[OK]" if result else "[X]"
        print(f"  {status} {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n[OK] All tests passed!")
    else:
        print(f"\n[X] {total - passed} test(s) failed")


if __name__ == "__main__":
    test_extract_deliverables()

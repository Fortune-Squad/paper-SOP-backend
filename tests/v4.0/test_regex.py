import re

response = """```yaml
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

print(f"Original length: {len(response)}")

# Test code block removal
code_block_pattern = r'^```(?:yaml|markdown|md)?\s*\n(.*?)\n```\s*$'
match = re.search(code_block_pattern, response, re.DOTALL | re.MULTILINE)

if match:
    extracted = match.group(1)
    print(f"Extracted length: {len(extracted)}")
    print(f"\nContent preview:")
    print(extracted[:300])
    print(f"\n...Success: {len(extracted) > 100}")
else:
    print("No match found")

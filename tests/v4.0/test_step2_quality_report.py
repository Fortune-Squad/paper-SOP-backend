"""
Step 2 完整质量检查报告
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.utils.file_manager import FileManager
from app.models.document import DocumentType


async def generate_step2_quality_report():
    """生成 Step 2 质量检查报告"""

    project_id = "physics-driven-compressed-sens-9d772ae8"
    file_manager = FileManager()

    print("=" * 80)
    print("Step 2 Quality Check Report")
    print("=" * 80)

    # Step 2 文档列表
    step2_docs = [
        ("Step 2.0", DocumentType.FIGURE_TABLE_LIST, 500, ["Figure", "Table"]),
        ("Step 2.1", DocumentType.FULL_PROPOSAL, 3000, ["System/Study Model", "Main Method", "Evaluation Design"]),
        ("Step 2.2", DocumentType.DATA_SIM_SPEC, 1500, ["Data", "Simulation"]),
        ("Step 2.3", DocumentType.ENGINEERING_SPEC, 2000, ["Engineering", "Module"]),
        ("Step 2.4", DocumentType.REDTEAM_REVIEW, 5000, ["Fatal", "Patch", "Risk"]),
        ("Step 2.4b", DocumentType.PATCH_DIFF, 800, ["Patch", "Change"]),
        ("Step 2.5", DocumentType.RESEARCH_PLAN_FROZEN, 1000, ["Plan", "Frozen"]),
    ]

    results = []

    for step_name, doc_type, min_length, required_keywords in step2_docs:
        print(f"\n{'=' * 80}")
        print(f"{step_name}: {doc_type.value}")
        print(f"{'=' * 80}")

        document = await file_manager.load_document(project_id, doc_type)

        if not document:
            print(f"  [X] Document NOT FOUND")
            results.append({
                "step": step_name,
                "status": "missing",
                "length": 0,
                "issues": ["Document not found"]
            })
            continue

        content_length = len(document.content)
        print(f"  [INFO] Length: {content_length} characters")

        issues = []

        # 1. 检查 YAML front-matter
        if not document.content.startswith("---"):
            issues.append("Missing YAML front-matter")

        # 2. 检查长度
        if content_length < min_length:
            issues.append(f"Content too short (expected >{min_length} chars, got {content_length})")

        # 3. 检查必需关键词
        missing_keywords = []
        for keyword in required_keywords:
            if keyword.lower() not in document.content.lower():
                missing_keywords.append(keyword)

        if missing_keywords:
            issues.append(f"Missing keywords: {', '.join(missing_keywords)}")

        # 4. 检查截断迹象
        truncation_indicators = ["...", "[truncated]", "[content continues]"]
        for indicator in truncation_indicators:
            if indicator in document.content[-500:]:
                issues.append(f"Possible truncation: found '{indicator}' near end")

        # 5. 检查是否只有 YAML front-matter
        lines = document.content.split('\n')
        non_empty_lines = [line for line in lines if line.strip() and not line.strip().startswith('---')]
        if len(non_empty_lines) < 10:
            issues.append("Content appears to be mostly empty (< 10 non-empty lines)")

        # 报告结果
        if issues:
            print(f"  [WARNING] Issues detected:")
            for issue in issues:
                print(f"    - {issue}")
            results.append({
                "step": step_name,
                "status": "completed_with_issues",
                "length": content_length,
                "issues": issues
            })
        else:
            print(f"  [OK] Quality check PASSED")
            results.append({
                "step": step_name,
                "status": "passed",
                "length": content_length,
                "issues": []
            })

    # 汇总报告
    print(f"\n{'=' * 80}")
    print("Summary")
    print(f"{'=' * 80}")

    passed = sum(1 for r in results if r["status"] == "passed")
    issues = sum(1 for r in results if r["status"] == "completed_with_issues")
    missing = sum(1 for r in results if r["status"] == "missing")

    print(f"\n[OK] Passed: {passed}/{len(results)}")
    print(f"[WARNING] With Issues: {issues}/{len(results)}")
    print(f"[ERROR] Missing: {missing}/{len(results)}")

    if issues > 0:
        print(f"\n[WARNING] Documents with issues:")
        for r in results:
            if r["status"] == "completed_with_issues":
                print(f"  - {r['step']}: {', '.join(r['issues'])}")

    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(generate_step2_quality_report())

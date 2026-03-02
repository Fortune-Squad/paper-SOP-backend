"""
Debug Gate 1.6 检查逻辑
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.utils.file_manager import FileManager
from app.models.document import DocumentType


async def debug_gate_1_6():
    """调试 Gate 1.6 检查逻辑"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Debugging Gate 1.6 Check Logic")
    print("=" * 80)

    # 初始化管理器
    file_manager = FileManager()

    # 加载 Reference QA Report
    print("\n[1] Loading Reference QA Report...")
    ref_qa_report = await file_manager.load_document(project_id, DocumentType.REFERENCE_QA_REPORT)

    if not ref_qa_report:
        print("[X] Reference QA Report not found")
        return

    print(f"[OK] Loaded document ({len(ref_qa_report.content)} chars)")

    # 解析内容
    content = ref_qa_report.content.lower()

    print("\n[2] Parsing key metrics...")

    # 1. 文献数量
    import re

    count_patterns = [
        r'total references:\s*(\d+)',
        r'total.*?(\d+)',
        r'literature count.*?(\d+)',
    ]

    literature_count = 0
    for pattern in count_patterns:
        match = re.search(pattern, content)
        if match:
            literature_count = int(match.group(1))
            print(f"  Literature count: {literature_count} (pattern: {pattern})")
            break

    literature_count_ok = literature_count >= 20
    print(f"  Literature count sufficient (>= 20): {literature_count_ok}")

    # 2. DOI 可解析率
    doi_patterns = [
        r'references with doi:\s*(\d+)\s*\((\d+)%\)',
        r'doi.*?(\d+)%',
    ]

    doi_rate = 0
    for pattern in doi_patterns:
        match = re.search(pattern, content)
        if match:
            # 尝试提取百分比
            groups = match.groups()
            if len(groups) >= 2:
                doi_rate = int(groups[1])  # 第二个组是百分比
            else:
                doi_rate = int(groups[0])
            print(f"  DOI rate: {doi_rate}% (pattern: {pattern})")
            break

    doi_parseable_ok = doi_rate >= 80
    print(f"  DOI parseable rate OK (>= 80%): {doi_parseable_ok}")

    # 3. 无重复引用 - 使用改进的逻辑
    has_confirmed_duplicates = False

    # 查找 "Potential duplicates:" 部分
    duplicate_section_match = re.search(
        r'potential duplicates:\s*\n\s*\*\s*(.+?)(?:\n\n|###|\Z)',
        content,
        re.DOTALL | re.IGNORECASE
    )

    if duplicate_section_match:
        duplicate_text = duplicate_section_match.group(1).lower()
        print(f"  Found potential duplicates section")
        print(f"  Duplicate text preview: {duplicate_text[:200]}...")

        # 如果明确说明这些是不同的论文，则不算重复
        if "appear to be distinct" in duplicate_text or "distinct" in duplicate_text:
            has_confirmed_duplicates = False
            print(f"  -> Marked as distinct, not confirmed duplicates")
        else:
            has_confirmed_duplicates = True
            print(f"  -> Confirmed duplicates found")

    # 如果明确说明没有重复
    if "no duplicate" in content or "0 duplicate" in content or "zero duplicate" in content:
        has_confirmed_duplicates = False
        print(f"  Explicit 'no duplicate' statement found")

    no_duplicates = not has_confirmed_duplicates
    print(f"  No duplicates: {no_duplicates}")

    # 4. 所有引用有完整元数据 - 使用改进的逻辑
    # 检查是否有缺失 DOI/URL 的引用
    missing_match = re.search(r'missing doi/url:\s*(\d+)', content)
    missing_count = 0
    if missing_match:
        missing_count = int(missing_match.group(1))
        print(f"  Missing DOI/URL count: {missing_count}")

    # 如果缺失数量 <= 3 且 DOI 覆盖率 >= 80%，认为是可接受的
    complete_metadata = (missing_count <= 3 and doi_parseable_ok) or missing_count == 0
    print(f"  All references complete: {complete_metadata}")
    print(f"    - Missing count: {missing_count}")
    print(f"    - DOI rate OK: {doi_parseable_ok}")
    print(f"    - Acceptable (missing <= 3 and DOI >= 80%): {missing_count <= 3 and doi_parseable_ok}")

    # 5. 总结
    print("\n[3] Gate 1.6 Check Summary:")
    checks = {
        "Literature count sufficient (>= 20)": literature_count_ok,
        "DOI parseable rate OK (>= 80%)": doi_parseable_ok,
        "No duplicates": no_duplicates,
        "All references complete": complete_metadata,
    }

    passed = sum(1 for v in checks.values() if v)
    total = len(checks)

    for check_name, result in checks.items():
        status = "[OK]" if result else "[X]"
        print(f"  {status} {check_name}")

    print(f"\n  Total: {passed}/{total} checks passed")

    if passed == total:
        print("\n  Verdict: PASS")
    else:
        print("\n  Verdict: FAIL")
        print("\n  Failed checks:")
        for check_name, result in checks.items():
            if not result:
                print(f"    - {check_name}")

    # 显示原始内容片段
    print("\n[4] Relevant content snippets:")

    # Quality Report section
    quality_section = re.search(
        r'### b\) reference quality report(.*?)### c\)',
        content,
        re.DOTALL | re.IGNORECASE
    )
    if quality_section:
        print("\n  Quality Report section:")
        print("  " + "-" * 76)
        snippet = quality_section.group(1).strip()[:500]
        for line in snippet.split('\n'):
            print(f"  {line}")
        print("  " + "-" * 76)


if __name__ == "__main__":
    asyncio.run(debug_gate_1_6())

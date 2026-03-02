"""
Test Gate 1.5 (Killer Prior Check) and analyze failure reasons
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager


async def test_gate_1_5_check():
    """测试 Gate 1.5 检查并分析失败原因"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Gate 1.5 Check (Killer Prior Check)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 执行 Gate 1.5 检查
    print("\n[2] Checking Gate 1.5 (Killer Prior Check)...")
    result = await project_manager.check_gate(project, "gate_1_5")

    # 显示结果
    print(f"\n[3] Gate 1.5 Check Result:")
    print(f"  Verdict: {result['verdict']}")
    print(f"  Checks passed: {result['passed_count']}/{result['total_count']}")

    if result['verdict'] == "PASS":
        print("\n  [OK] Gate 1.5 PASSED!")
    else:
        print("\n  [X] Gate 1.5 FAILED")

    # 显示检查项
    print(f"\n[4] Check Items:")
    for item in result['check_items']:
        status = "[OK]" if item['passed'] else "[X]"
        print(f"  {status} {item['item_name']}: {item['details']}")

    # 显示建议
    if result['suggestions']:
        print(f"\n[5] Suggestions:")
        for suggestion in result['suggestions']:
            print(f"  - {suggestion}")

    # 读取 Killer Prior Check 文档
    print(f"\n[6] Analyzing Killer Prior Check Document...")
    from app.utils.file_manager import FileManager
    from app.models.document import DocumentType

    file_manager = FileManager()
    killer_prior = await file_manager.load_document(project_id, DocumentType.KILLER_PRIOR_CHECK)

    if killer_prior:
        import re
        content = killer_prior.content

        # 提取 Verdict
        verdict_match = re.search(r'Verdict:\s*(PASS|FAIL)', content, re.IGNORECASE)
        if verdict_match:
            doc_verdict = verdict_match.group(1)
            print(f"  Document Verdict: {doc_verdict}")

        # 统计 Direct Collision
        direct_collision_section = re.search(
            r'##\s*(?:3\)|A\))\s*Deliverables.*?###\s*A\)\s*"?Direct Collision"?\s*List(.*?)(?:###\s*B\)|##\s*(?:4\)|B\))|$)',
            content,
            re.DOTALL | re.IGNORECASE
        )

        if direct_collision_section:
            collision_text = direct_collision_section.group(1)
            # 统计列表项（以 - 或 * 开头）
            collision_items = re.findall(r'^\s*[-*]\s*\*\*Title\*\*:', collision_text, re.MULTILINE)
            collision_count = len(collision_items)
            print(f"  Direct Collisions Found: {collision_count}")

            if collision_count > 0:
                print(f"\n  [!] CRITICAL: Found {collision_count} direct collision(s)")
                print(f"      This means prior work already covers our main claims")
        else:
            print(f"  Could not parse Direct Collision section")

        # 提取 Partial Overlap
        partial_overlap_section = re.search(
            r'###\s*B\)\s*"?Partial Overlap"?\s*List(.*?)(?:###\s*C\)|##\s*(?:4\)|C\))|$)',
            content,
            re.DOTALL | re.IGNORECASE
        )

        if partial_overlap_section:
            overlap_text = partial_overlap_section.group(1)
            overlap_items = re.findall(r'^\s*[-*]\s*\*\*Title\*\*:', overlap_text, re.MULTILINE)
            overlap_count = len(overlap_items)
            print(f"  Partial Overlaps Found: {overlap_count}")

        # 提取 Recommended Changes
        changes_section = re.search(
            r'###\s*C\)\s*Recommended Changes.*?\n(.*?)(?:###\s*D\)|##\s*(?:4\)|D\))|$)',
            content,
            re.DOTALL | re.IGNORECASE
        )

        if changes_section:
            changes_text = changes_section.group(1)
            changes = re.findall(r'^\s*\d+\.\s*(.+?)$', changes_text, re.MULTILINE)
            if changes:
                print(f"\n[7] Recommended Changes ({len(changes)}):")
                for i, change in enumerate(changes, 1):
                    print(f"  {i}. {change.strip()}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_gate_1_5_check())

"""
Test Step 1.3 re-execution with fixed configuration (disabled wrapper mode + max_tokens)
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.models.project import StepStatus


async def test_step_1_3_rerun():
    """测试重新执行 Step 1.3 (Killer Prior Check)"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 1.3 Re-execution (Killer Prior Check)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 显示当前 Killer Prior Check 状态
    print("\n[2] Current Killer Prior Check Status:")
    from app.utils.file_manager import FileManager
    from app.models.document import DocumentType
    import re

    file_manager = FileManager()
    current_kpc = await file_manager.load_document(project_id, DocumentType.KILLER_PRIOR_CHECK)

    if current_kpc:
        content_lines = len(current_kpc.content.split('\n'))
        content_chars = len(current_kpc.content)
        print(f"  Lines: {content_lines}")
        print(f"  Characters: {content_chars}")

        # 检查是否有 Verdict
        has_verdict = "verdict:" in current_kpc.content.lower()
        print(f"  Has Verdict: {has_verdict}")

        # 统计各个部分
        has_direct_collision = "direct collision" in current_kpc.content.lower()
        has_partial_overlap = "partial overlap" in current_kpc.content.lower()
        has_recommended_changes = "recommended changes" in current_kpc.content.lower()

        print(f"  Has Direct Collision section: {has_direct_collision}")
        print(f"  Has Partial Overlap section: {has_partial_overlap}")
        print(f"  Has Recommended Changes section: {has_recommended_changes}")

    # 重置 Step 1.3 状态
    print("\n[3] Resetting Step 1.3 status to PENDING...")
    if "step_1_3" in project.steps:
        project.update_step_status("step_1_3", StepStatus.PENDING)
        project.steps["step_1_3"].error_message = None
        print("  [OK] Reset step status to PENDING")

    # 重新执行 Step 1.3
    print("\n[4] Re-executing Step 1.3 (Killer Prior Check)...")
    print("  This may take 2-5 minutes due to extensive literature search...")

    try:
        result = await project_manager.execute_step(project, "step_1_3")
        print(f"[OK] Step 1.3 completed")

        # 重新加载项目
        project = await project_manager._load_project(project_id)

        # 检查新生成的文档
        print("\n[5] New Killer Prior Check Status:")
        new_kpc = await file_manager.load_document(project_id, DocumentType.KILLER_PRIOR_CHECK)

        if new_kpc:
            new_content_lines = len(new_kpc.content.split('\n'))
            new_content_chars = len(new_kpc.content)
            print(f"  Lines: {new_content_lines} (was {content_lines})")
            print(f"  Characters: {new_content_chars} (was {content_chars})")

            # 检查是否有 Verdict
            has_verdict = re.search(r'verdict:\s*(PASS|FAIL)', new_kpc.content, re.IGNORECASE)
            if has_verdict:
                print(f"  Verdict: {has_verdict.group(1)}")
            else:
                print(f"  Verdict: NOT FOUND (document may be incomplete)")

            # 统计各个部分
            has_direct_collision = "direct collision" in new_kpc.content.lower()
            has_partial_overlap = "partial overlap" in new_kpc.content.lower()
            has_recommended_changes = "recommended changes" in new_kpc.content.lower()

            print(f"  Has Direct Collision section: {has_direct_collision}")
            print(f"  Has Partial Overlap section: {has_partial_overlap}")
            print(f"  Has Recommended Changes section: {has_recommended_changes}")

            # 统计 Direct Collision 数量
            direct_collision_section = re.search(
                r'###?\s*A\)\s*"?Direct Collision"?\s*List(.*?)(?:###?\s*B\)|$)',
                new_kpc.content,
                re.DOTALL | re.IGNORECASE
            )

            if direct_collision_section:
                collision_text = direct_collision_section.group(1)
                collision_items = re.findall(r'^\s*[-*]\s*\*\*Title\*\*:', collision_text, re.MULTILINE)
                print(f"  Direct Collisions: {len(collision_items)}")

            # 统计 Partial Overlap 数量
            partial_overlap_section = re.search(
                r'###?\s*B\)\s*"?Partial Overlap"?\s*List(.*?)(?:###?\s*C\)|$)',
                new_kpc.content,
                re.DOTALL | re.IGNORECASE
            )

            if partial_overlap_section:
                overlap_text = partial_overlap_section.group(1)
                overlap_items = re.findall(r'^\s*[-*]\s*\*\*Title\*\*:', overlap_text, re.MULTILINE)
                print(f"  Partial Overlaps: {len(overlap_items)}")

        # 检查 Gate 1.5
        print("\n[6] Checking Gate 1.5...")
        gate_result = await project_manager.check_gate(project, "gate_1_5")

        print(f"\n[7] Gate 1.5 Result:")
        print(f"  Verdict: {gate_result['verdict']}")
        print(f"  Checks passed: {gate_result['passed_count']}/{gate_result['total_count']}")

        if gate_result['verdict'] == "PASS":
            print("\n  [OK] Gate 1.5 PASSED!")
        else:
            print("\n  [X] Gate 1.5 FAILED")

        # 显示检查项
        print(f"\n[8] Check Items:")
        for item in gate_result['check_items']:
            status = "[OK]" if item['passed'] else "[X]"
            print(f"  {status} {item['item_name']}: {item['details']}")

        # 显示建议
        if gate_result['suggestions']:
            print(f"\n[9] Suggestions:")
            for suggestion in gate_result['suggestions']:
                print(f"  - {suggestion}")

        # 提取 Recommended Changes
        if new_kpc and "recommended changes" in new_kpc.content.lower():
            print(f"\n[10] Recommended Changes from Killer Prior Check:")
            changes_section = re.search(
                r'###?\s*C\)\s*Recommended Changes.*?\n(.*?)(?:###?\s*D\)|##\s*(?:4\)|D\)|Risks|Verification)|$)',
                new_kpc.content,
                re.DOTALL | re.IGNORECASE
            )

            if changes_section:
                changes_text = changes_section.group(1)
                changes = re.findall(r'^\s*\d+\.\s*(.+?)$', changes_text, re.MULTILINE)
                if changes:
                    for i, change in enumerate(changes[:5], 1):  # 只显示前 5 个
                        print(f"  {i}. {change.strip()}")

    except Exception as e:
        print(f"[ERROR] Step 1.3 failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_step_1_3_rerun())

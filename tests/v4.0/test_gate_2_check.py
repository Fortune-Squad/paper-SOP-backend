"""
执行 Gate 2 检查 - 验证 Plan Freeze 是否符合 SOP v4.0 要求
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.gate_checker import GateChecker
from app.utils.file_manager import FileManager
from app.models.document import DocumentType


async def test_gate_2_check():
    """测试 Gate 2 检查"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Gate 2 Check - Plan Freeze Validation")
    print("=" * 80)

    # 初始化检查器和项目管理器
    gate_checker = GateChecker()
    file_manager = FileManager()

    from app.services.project_manager import ProjectManager
    project_manager = ProjectManager()

    # 加载项目
    print("\n[0] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 1. 检查所有必需文档是否存在
    print("\n[1] Checking required documents...")

    required_docs = [
        ("Claims and NonClaims", DocumentType.CLAIMS_AND_NONCLAIMS),
        ("Full Proposal", DocumentType.FULL_PROPOSAL),
        ("Engineering Spec", DocumentType.ENGINEERING_SPEC),
        ("Test Plan", DocumentType.TEST_PLAN),
        ("Red Team Review", DocumentType.REDTEAM_REVIEW),
        ("Research Plan FROZEN", DocumentType.RESEARCH_PLAN_FROZEN)
    ]

    all_docs_present = True
    for doc_name, doc_type in required_docs:
        doc = await file_manager.load_document(project_id, doc_type)
        if doc:
            print(f"  [OK] {doc_name}: {len(doc.content)} chars")
        else:
            print(f"  [X] {doc_name}: NOT FOUND")
            all_docs_present = False

    if not all_docs_present:
        print("\n[ERROR] Some required documents are missing. Cannot proceed with Gate 2 check.")
        return

    # 2. 执行 Gate 2 检查
    print("\n[2] Executing Gate 2 check...")

    try:
        gate_result = await gate_checker.check_gate_2(project)

        print(f"\n{'=' * 80}")
        print(f"Gate 2 Result: {gate_result.verdict}")
        print(f"{'=' * 80}")
        print(f"\nChecks passed: {gate_result.passed_count}/{gate_result.total_count}")
        print(f"Pass rate: {gate_result.pass_rate:.1f}%")

        # 显示每个检查项的结果
        print(f"\n[3] Detailed check results:")
        for i, item in enumerate(gate_result.check_items, 1):
            status_icon = "[OK]" if item.passed else "[X]"
            print(f"\n  {status_icon} Check {i}: {item.item_name}")
            print(f"      {item.description}")
            if item.details:
                # details is a string, not a dict
                print(f"      Details: {item.details}")

        # 显示建议
        if gate_result.suggestions:
            print(f"\n[4] Suggestions for improvement:")
            for i, suggestion in enumerate(gate_result.suggestions, 1):
                print(f"  {i}. {suggestion}")

        # 显示元数据
        print(f"\n[5] Gate check metadata:")
        print(f"  - Checked at: {gate_result.checked_at}")
        print(f"  - Project ID: {gate_result.project_id}")
        print(f"  - Gate type: {gate_result.gate_type}")

        # 最终判定
        print(f"\n{'=' * 80}")
        if gate_result.verdict == "PASS":
            print("[PASS] Gate 2 PASSED - Plan is frozen and ready for execution!")
            print("  You can now proceed to implement the research plan.")
        else:
            print("[FAIL] Gate 2 FAILED - Plan needs revision before proceeding.")
            print("  Please address the issues identified above.")
        print(f"{'=' * 80}")

    except Exception as e:
        print(f"\n[ERROR] Gate 2 check failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_gate_2_check())

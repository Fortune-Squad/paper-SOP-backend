"""
重新执行 Step 2.4 (Red Team Review) - 修复 wrapper_mode 配置
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.models.project import StepStatus
from app.models.document import DocumentType


async def test_step_2_4_rerun():
    """测试重新执行 Step 2.4 (Red Team Review)"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 2.4 Re-execution (Red Team Review)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 检查前置条件
    print("\n[2] Checking prerequisites...")
    from app.utils.file_manager import FileManager
    file_manager = FileManager()

    # 检查 Full Proposal
    full_proposal = await file_manager.load_document(project_id, DocumentType.FULL_PROPOSAL)
    if full_proposal:
        print(f"  [OK] Full Proposal exists ({len(full_proposal.content)} chars)")
    else:
        print(f"  [X] Full Proposal NOT FOUND - Step 2.1 must be run first")
        return

    # 检查 Engineering Spec
    engineering_spec = await file_manager.load_document(project_id, DocumentType.ENGINEERING_SPEC)
    if engineering_spec:
        print(f"  [OK] Engineering Spec exists ({len(engineering_spec.content)} chars)")
    else:
        print(f"  [X] Engineering Spec NOT FOUND - Step 2.3 must be run first")
        return

    # 重置 Step 2.4 状态
    print("\n[3] Resetting Step 2.4 status to PENDING...")
    if "step_2_4" in project.steps:
        project.update_step_status("step_2_4", StepStatus.PENDING)
        project.steps["step_2_4"].error_message = None
        print("  [OK] Reset step status to PENDING")

    # 重新执行 Step 2.4
    print("\n[4] Re-executing Step 2.4 (Red Team Review)...")
    print("  This may take 1-3 minutes...")

    try:
        result = await project_manager.execute_step(project, "step_2_4")
        print(f"[OK] Step 2.4 completed")

        # 重新加载项目
        project = await project_manager._load_project(project_id)

        # 检查生成的文档
        print("\n[5] Checking generated document...")

        # 检查 Red Team Review
        redteam_review = await file_manager.load_document(project_id, DocumentType.REDTEAM_REVIEW)
        if redteam_review:
            content_length = len(redteam_review.content)
            print(f"  [OK] Red Team Review generated ({content_length} chars)")

            # 检查是否包含关键部分
            import re

            # 检查必需的部分
            has_plan = "## 0) plan" in redteam_review.content.lower()
            has_actions = "## 1) actions" in redteam_review.content.lower()
            has_evidence = "## 2) evidence" in redteam_review.content.lower()
            has_deliverables = "## 3) deliverables" in redteam_review.content.lower()
            has_fatal_issues = "fatal" in redteam_review.content.lower()
            has_patches = "patch" in redteam_review.content.lower()
            has_risks = "## 4) risks" in redteam_review.content.lower()
            has_verification = "## 5) verification" in redteam_review.content.lower()
            has_confidence = "## 6) confidence" in redteam_review.content.lower()

            print(f"\n  Content Analysis:")
            print(f"    Has Plan section: {has_plan}")
            print(f"    Has Actions section: {has_actions}")
            print(f"    Has Evidence section: {has_evidence}")
            print(f"    Has Deliverables section: {has_deliverables}")
            print(f"    Has Fatal Issues: {has_fatal_issues}")
            print(f"    Has Patches: {has_patches}")
            print(f"    Has Risks section: {has_risks}")
            print(f"    Has Verification section: {has_verification}")
            print(f"    Has Confidence section: {has_confidence}")

            # 统计 fatal issues 数量
            fatal_count = redteam_review.content.lower().count("fatal-")
            print(f"\n    Fatal issues found: {fatal_count}")

            # 统计 patches 数量
            patch_pattern = r'\*\*Patch \d+:\*\*'
            patch_matches = re.findall(patch_pattern, redteam_review.content, re.IGNORECASE)
            print(f"    Patches found: {len(patch_matches)}")

            # 检查长度是否合理（应该 > 5000 chars）
            if content_length < 5000:
                print(f"\n  [WARNING] Content seems too short (expected >5000 chars)")
            else:
                print(f"\n  [OK] Content length is reasonable")

            # 显示前 500 字符
            print(f"\n[6] Content Preview (first 500 chars):")
            print(redteam_review.content[:500])
            print("...")

        else:
            print(f"  [X] Red Team Review NOT FOUND")

    except Exception as e:
        print(f"[ERROR] Step 2.4 failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_step_2_4_rerun())

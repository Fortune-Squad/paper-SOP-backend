"""
Test Step 1.5 re-execution with fixed configuration (disabled wrapper mode)
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.models.project import StepStatus


async def test_step_1_5_rerun():
    """测试重新执行 Step 1.5 (Figure-First Story)"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 1.5 Re-execution (Figure-First Story)")
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
    from app.models.document import DocumentType

    file_manager = FileManager()

    # 检查 Claims and NonClaims
    claims = await file_manager.load_document(project_id, DocumentType.CLAIMS_AND_NONCLAIMS)
    if claims:
        print(f"  [OK] Claims and NonClaims exists ({len(claims.content)} chars)")
    else:
        print(f"  [X] Claims and NonClaims NOT FOUND - Step 1.4 must be run first")
        return

    # 重置 Step 1.5 状态
    print("\n[3] Resetting Step 1.5 status to PENDING...")
    if "step_1_5" in project.steps:
        project.update_step_status("step_1_5", StepStatus.PENDING)
        project.steps["step_1_5"].error_message = None
        print("  [OK] Reset step status to PENDING")

    # 重新执行 Step 1.5
    print("\n[4] Re-executing Step 1.5 (Figure-First Story)...")
    print("  This may take 1-3 minutes...")

    try:
        result = await project_manager.execute_step(project, "step_1_5")
        print(f"[OK] Step 1.5 completed")

        # 重新加载项目
        project = await project_manager._load_project(project_id)

        # 检查生成的文档
        print("\n[5] Checking generated documents...")

        # 检查 Figure First Story
        figure_story = await file_manager.load_document(project_id, DocumentType.FIGURE_FIRST_STORY)
        if figure_story:
            print(f"  [OK] Figure First Story generated ({len(figure_story.content)} chars)")

            # 检查是否包含关键部分
            import re
            has_plan = "## 0) plan" in figure_story.content.lower()
            has_evidence = "## 2) evidence" in figure_story.content.lower()
            has_figures = "figure" in figure_story.content.lower()
            has_risks = "## 4) risks" in figure_story.content.lower()

            print(f"    Has Plan section: {has_plan}")
            print(f"    Has Evidence section: {has_evidence}")
            print(f"    Has Figure descriptions: {has_figures}")
            print(f"    Has Risks section: {has_risks}")
        else:
            print(f"  [X] Figure First Story NOT FOUND")

        # 检查 Title Abstract Candidates
        title_abstract = await file_manager.load_document(project_id, DocumentType.TITLE_ABSTRACT_CANDIDATES)
        if title_abstract:
            print(f"  [OK] Title Abstract Candidates generated ({len(title_abstract.content)} chars)")

            # 统计候选数量
            candidate_count = title_abstract.content.lower().count("candidate")
            print(f"    Candidate mentions: {candidate_count}")

            # 检查是否有推荐
            has_recommendation = "recommendation" in title_abstract.content.lower()
            print(f"    Has Recommendation: {has_recommendation}")
        else:
            print(f"  [X] Title Abstract Candidates NOT FOUND")

        # 显示第一个标题候选
        if title_abstract:
            print("\n[6] Title Candidates Preview:")
            # 提取第一个候选标题
            title_pattern = r'\*\*Candidate 1:\*\*.*?\*\*Title\*\*:\s*(.+?)(?:\n|$)'
            title_match = re.search(title_pattern, title_abstract.content, re.IGNORECASE)
            if title_match:
                print(f"  Candidate 1: {title_match.group(1).strip()}")

    except Exception as e:
        print(f"[ERROR] Step 1.5 failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_step_1_5_rerun())

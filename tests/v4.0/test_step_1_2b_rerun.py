"""
Test Step 1.2b re-execution to validate new topic alignment
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.models.project import StepStatus


async def test_step_1_2b_rerun():
    """测试重新执行 Step 1.2b"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 1.2b Re-execution (Topic Alignment Check)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 显示新选题
    print("\n[2] Current Selected Topic:")
    from app.utils.file_manager import FileManager
    from app.models.document import DocumentType
    import re

    file_manager = FileManager()
    current_topic = await file_manager.load_document(project_id, DocumentType.SELECTED_TOPIC)
    if current_topic:
        topic_match = re.search(r'topic:\s*"([^"]+)"', current_topic.content)
        if topic_match:
            print(f"  {topic_match.group(1)}")

    # 显示核心关键词
    print("\n[3] Core Keywords from Intake Card:")
    intake_card = await file_manager.load_document(project_id, DocumentType.PROJECT_INTAKE_CARD)
    if intake_card:
        keywords_pattern = r'\*\*English Keywords:\*\*\s*([^\n]+)'
        match = re.search(keywords_pattern, intake_card.content)
        if match:
            keywords = match.group(1).strip()
            print(f"  {keywords}")

    # 重置 Step 1.2b 状态
    print("\n[4] Resetting Step 1.2b status to PENDING...")
    if "step_1_2b" in project.steps:
        project.update_step_status("step_1_2b", StepStatus.PENDING)
        project.steps["step_1_2b"].error_message = None
        print("  [OK] Reset step status to PENDING")

    # 重新执行 Step 1.2b
    print("\n[5] Re-executing Step 1.2b (Topic Alignment Check)...")
    try:
        result = await project_manager.execute_step(project, "step_1_2b")
        print(f"[OK] Step 1.2b completed")

        # 重新加载项目
        project = await project_manager._load_project(project_id)

        # 检查 Gate 1.25
        print("\n[6] Checking Gate 1.25...")
        gate_result = await project_manager.check_gate(project, "gate_1_25")

        print(f"\n[7] Gate 1.25 Result:")
        print(f"  Verdict: {gate_result['verdict']}")
        print(f"  Checks passed: {gate_result['passed_count']}/{gate_result['total_count']}")

        if gate_result['verdict'] == "PASS":
            print("\n  [OK] Gate 1.25 PASSED! ✅")
        else:
            print("\n  [X] Gate 1.25 FAILED")

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

    except Exception as e:
        print(f"[ERROR] Step 1.2b failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_step_1_2b_rerun())

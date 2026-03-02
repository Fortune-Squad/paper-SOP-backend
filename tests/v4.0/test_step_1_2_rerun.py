"""
Test Step 1.2 re-execution with improved prompt (core keywords requirement)
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager


async def test_step_1_2_rerun():
    """测试重新执行 Step 1.2"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 1.2 Re-execution (With Core Keywords Requirement)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 显示当前选题
    print("\n[2] Current Selected Topic:")
    from app.utils.file_manager import FileManager
    from app.models.document import DocumentType
    file_manager = FileManager()
    current_topic = await file_manager.load_document(project_id, DocumentType.SELECTED_TOPIC)
    if current_topic:
        # 提取 topic 字段
        import re
        topic_match = re.search(r'topic:\s*"([^"]+)"', current_topic.content)
        if topic_match:
            print(f"  Current: {topic_match.group(1)}")

    # 显示核心关键词
    print("\n[3] Core Keywords from Intake Card:")
    intake_card = await file_manager.load_document(project_id, DocumentType.PROJECT_INTAKE_CARD)
    if intake_card:
        keywords_pattern = r'\*\*English Keywords:\*\*\s*([^\n]+)'
        match = re.search(keywords_pattern, intake_card.content)
        if match:
            keywords = match.group(1).strip()
            print(f"  {keywords}")
            # 统计关键词数量
            keyword_list = [k.strip() for k in keywords.split(',')]
            print(f"  Total: {len(keyword_list)} keywords")

    # 确认是否继续
    print("\n[4] Ready to re-execute Step 1.2")
    print("  This will:")
    print("  - Call ChatGPT with improved prompt (core keywords requirement)")
    print("  - Generate new Selected Topic with 3-5 core keywords")
    print("  - Overwrite existing 01_Selected_Topic.md")
    print("  - Create new Git commit")

    # 检查是否有 --yes 参数
    if "--yes" not in sys.argv:
        response = input("\n  Continue? (yes/no): ")
        if response.lower() != "yes":
            print("\n[CANCELLED] Step 1.2 re-execution cancelled by user")
            return
    else:
        print("\n  [--yes flag detected, proceeding automatically]")

    # 重新执行 Step 1.2
    print("\n[5] Re-executing Step 1.2...")
    try:
        # 将步骤状态重置为 PENDING 以强制重新执行
        from app.models.project import StepStatus
        if "step_1_2" in project.steps:
            project.update_step_status("step_1_2", StepStatus.PENDING)
            project.steps["step_1_2"].error_message = None
            print("  [OK] Reset step status to PENDING")

        result = await project_manager.execute_step(project, "step_1_2")
        print(f"[OK] Step 1.2 completed")

        # 重新加载项目以获取最新状态
        project = await project_manager._load_project(project_id)

        # 显示新选题
        print("\n[6] New Selected Topic:")
        new_topic = await file_manager.load_document(project_id, DocumentType.SELECTED_TOPIC)
        if new_topic:
            topic_match = re.search(r'topic:\s*"([^"]+)"', new_topic.content)
            if topic_match:
                new_topic_title = topic_match.group(1)
                print(f"  New: {new_topic_title}")

                # 统计新选题中包含的核心关键词
                print("\n[7] Keyword Analysis:")
                if intake_card:
                    keywords_pattern = r'\*\*English Keywords:\*\*\s*([^\n]+)'
                    match = re.search(keywords_pattern, intake_card.content)
                    if match:
                        keywords = match.group(1).strip()
                        keyword_list = [k.strip() for k in keywords.split(',')]

                        # 检查每个关键词是否在新选题中
                        found_keywords = []
                        for keyword in keyword_list:
                            # 检查关键词的各种形式
                            keyword_lower = keyword.lower()
                            topic_lower = new_topic_title.lower()

                            # 处理复合词（如 "Near-Field Measurement" -> "near-field" 或 "near field"）
                            keyword_variants = [
                                keyword_lower,
                                keyword_lower.replace('-', ' '),
                                keyword_lower.replace(' ', '-')
                            ]

                            if any(variant in topic_lower for variant in keyword_variants):
                                found_keywords.append(keyword)

                        print(f"  Keywords found in topic: {len(found_keywords)}/{len(keyword_list)}")
                        print(f"  Found: {', '.join(found_keywords)}")

                        missing_keywords = [k for k in keyword_list if k not in found_keywords]
                        if missing_keywords:
                            print(f"  Missing: {', '.join(missing_keywords)}")

        # 检查 Gate 1.25
        print("\n[8] Checking Gate 1.25...")
        # 需要先执行 Step 1.2b (Topic Alignment Check)
        print("  Note: Need to run Step 1.2b first to update Topic Alignment Check")

    except Exception as e:
        print(f"[ERROR] Step 1.2 failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_step_1_2_rerun())

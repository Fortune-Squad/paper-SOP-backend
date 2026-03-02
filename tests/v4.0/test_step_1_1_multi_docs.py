"""
测试 Step 1.1 多文档生成功能
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.project import Project
from app.services.project_manager import ProjectManager
from app.config import settings

async def test_step_1_1():
    """测试 Step 1.1 多文档生成"""
    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 60)
    print("Test Step 1.1: Broad Deep Research (Multi-Document Generation)")
    print("=" * 60)
    print()

    # 初始化 ProjectManager
    manager = ProjectManager()

    try:
        # 加载项目
        print(f"[1/4] Loading project: {project_id}")
        project = await manager._load_project(project_id)
        print(f"  OK Project name: {project.project_name}")
        print(f"  OK Current step: {project.current_step}")
        print()

        # 执行 Step 1.1
        print("[2/4] Executing Step 1.1...")
        print("  - Calling Gemini to generate Deep Research Summary")
        print("  - Extracting Search Query Log")
        print("  - Extracting Literature Matrix")
        print("  - Extracting Verified References")
        print()

        result = await manager.execute_step(project, "step_1_1")

        print(f"  OK Step 1.1 executed successfully")
        print(f"  OK Project updated: {result.project_id}")
        print()

        # 检查生成的文档
        print("[3/4] Checking generated documents...")
        from app.utils.file_manager import FileManager
        file_manager = FileManager(settings.projects_path)

        expected_docs = [
            "00_Deep_Research_Summary",
            "00_Search_Query_Log",
            "00_Literature_Matrix",
            "00_Verified_References"
        ]

        for doc_type in expected_docs:
            try:
                from app.models.document import DocumentType
                doc = await file_manager.load_document(project_id, DocumentType(doc_type))
                if doc:
                    print(f"  OK {doc_type}.md (Generated, {len(doc.content)} chars)")
                else:
                    print(f"  FAIL {doc_type}.md (Not found)")
            except Exception as e:
                print(f"  FAIL {doc_type}.md (Error: {e})")

        print()

        # 显示统计信息
        print("[4/4] Statistics")
        print(f"  - Project ID: {project_id}")
        print(f"  - Executed step: step_1_1")
        print(f"  - Expected documents: 4")
        print(f"  - Status: {result.status}")
        print()

        print("=" * 60)
        print("Test completed!")
        print("=" * 60)

    except Exception as e:
        print(f"\nFAIL Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = asyncio.run(test_step_1_1())
    sys.exit(0 if success else 1)

"""
Test Step 1.1b: Reference QA
测试 Step 1.1b 生成 Reference QA Report
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.utils.file_manager import FileManager
from app.models.document import DocumentType
from app.models.project import StepStatus


async def test_step_1_1b():
    """测试 Step 1.1b: Reference QA"""

    # 使用现有项目
    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 1.1b: Reference QA")
    print("=" * 80)
    print(f"\nProject ID: {project_id}")

    # 初始化管理器
    project_manager = ProjectManager()
    file_manager = FileManager()

    try:
        # 1. 加载项目
        print("\n[1/5] Loading project...")
        project = await project_manager._load_project(project_id)
        if not project:
            print(f"[X] Project not found: {project_id}")
            return
        print(f"[OK] Project loaded: {project.project_name}")

        # 2. 检查前置文档
        print("\n[2/5] Checking prerequisites...")
        lit_matrix = await file_manager.load_document(project_id, DocumentType.LITERATURE_MATRIX)
        if not lit_matrix:
            print("[X] Literature Matrix not found. Please run Step 1.1 first.")
            return
        print(f"[OK] Literature Matrix found ({len(lit_matrix.content)} chars)")

        # 3. 检查 Step 1.1b 状态
        print("\n[3/5] Checking Step 1.1b status...")
        step_info = project.steps.get("step_1_1b")
        if step_info:
            print(f"  Status: {step_info.status}")
            if step_info.completed_at:
                print(f"  Completed at: {step_info.completed_at}")

            # 强制重新执行
            if step_info.status == StepStatus.COMPLETED:
                print("  [!] Step already completed. Forcing re-execution...")
                from app.models.project import StepStatus as PS
                project.steps["step_1_1b"].status = PS.PENDING
                await project_manager._save_project(project)
        else:
            print("  Status: Not started")

        # 4. 执行 Step 1.1b
        print("\n[4/5] Executing Step 1.1b: Reference QA...")
        print("  (This may take 1-2 minutes...)")

        updated_project = await project_manager.execute_step(project, "step_1_1b")

        # 检查步骤状态
        step_info = updated_project.steps.get("step_1_1b")
        if step_info and step_info.status == StepStatus.COMPLETED:
            print("[OK] Step 1.1b completed successfully")
        elif step_info and step_info.status == StepStatus.FAILED:
            print(f"[X] Step 1.1b failed: {step_info.error_message}")
            return
        else:
            print(f"[?] Step 1.1b status: {step_info.status if step_info else 'Unknown'}")

        # 5. 验证生成的文档
        print("\n[5/5] Verifying generated document...")
        ref_qa_report = await file_manager.load_document(project_id, DocumentType.REFERENCE_QA_REPORT)

        if ref_qa_report:
            print(f"[OK] Reference QA Report generated")
            print(f"  File: 00_Reference_QA_Report.md")
            print(f"  Size: {len(ref_qa_report.content)} chars")
            print(f"  Status: {ref_qa_report.metadata.status}")

            # 分析内容
            content = ref_qa_report.content.lower()

            # 检查关键部分
            has_quality_report = "reference quality report" in content or "quality report" in content
            has_bibtex = "bibtex" in content or "@article" in content or "@inproceedings" in content
            has_action_items = "action items" in content or "action item" in content

            print(f"\n  Content analysis:")
            print(f"    Quality Report section: {'[OK]' if has_quality_report else '[X]'}")
            print(f"    BibTeX entries: {'[OK]' if has_bibtex else '[X]'}")
            print(f"    Action Items section: {'[OK]' if has_action_items else '[X]'}")

            # 提取关键指标
            import re

            # 尝试提取文献数量
            total_match = re.search(r'total.*?(\d+)', content)
            if total_match:
                total_refs = total_match.group(1)
                print(f"    Total references: {total_refs}")

            # 尝试提取 DOI 百分比
            doi_match = re.search(r'doi.*?(\d+)%', content)
            if doi_match:
                doi_percent = doi_match.group(1)
                print(f"    DOI coverage: {doi_percent}%")

            # 显示前 500 字符预览
            print(f"\n  Content preview (first 500 chars):")
            print("  " + "-" * 76)
            preview = ref_qa_report.content[:500].replace('\n', '\n  ')
            print(f"  {preview}")
            print("  " + "-" * 76)

        else:
            print("[X] Reference QA Report not found after execution")
            return

        # 6. 检查 Gate 1.6 状态
        print("\n[6/6] Checking Gate 1.6 status...")
        # 重新加载项目以获取最新的 gate 结果
        updated_project = await project_manager._load_project(project_id)
        gate_1_6_result = updated_project.gate_results.get("gate_1_6")
        if gate_1_6_result:
            verdict = gate_1_6_result.get("verdict")
            passed_count = gate_1_6_result.get("passed_count", 0)
            total_count = gate_1_6_result.get("total_count", 0)

            print(f"  Verdict: {verdict}")
            print(f"  Checks passed: {passed_count}/{total_count}")

            if verdict == "PASS":
                print("  [OK] Gate 1.6 PASSED")
            else:
                print("  [X] Gate 1.6 FAILED")
                suggestions = gate_1_6_result.get("suggestions", [])
                if suggestions:
                    print("\n  Suggestions:")
                    for suggestion in suggestions:
                        print(f"    - {suggestion}")
        else:
            print("  Gate 1.6 not checked yet (will be auto-checked after Step 1.1b)")

        print("\n" + "=" * 80)
        print("Test completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\n[X] Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_step_1_1b())

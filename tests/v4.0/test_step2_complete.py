"""
测试 Step 2 完整流程（Blueprint & Engineering）
检查每个步骤的输出质量、完整性和格式
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager
from app.models.project import StepStatus
from app.models.document import DocumentType


async def test_step2_complete():
    """测试 Step 2 完整流程"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Step 2 Complete Flow (Blueprint & Engineering)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")
    print(f"    Current step: {project.current_step}")

    # Step 2 步骤列表
    step2_steps = [
        ("step_2_0", "Figure/Table List", DocumentType.FIGURE_TABLE_LIST),
        ("step_2_1", "Full Proposal", DocumentType.FULL_PROPOSAL),
        ("step_2_2", "Data/Sim Spec", DocumentType.DATA_SIM_SPEC),
        ("step_2_3", "Engineering Spec", DocumentType.ENGINEERING_SPEC),
        ("step_2_4", "Red Team Review", DocumentType.REDTEAM_REVIEW),
        ("step_2_4b", "Patch Propagation", DocumentType.PATCH_DIFF),
        ("step_2_5", "Plan Freeze", DocumentType.RESEARCH_PLAN_FROZEN)
    ]

    results = {}

    # 执行每个步骤
    for step_id, step_name, doc_type in step2_steps:
        print(f"\n{'=' * 80}")
        print(f"[{step_id}] Executing: {step_name}")
        print(f"{'=' * 80}")

        try:
            # 重新加载项目以获取最新状态
            project = await project_manager._load_project(project_id)

            # 检查步骤状态
            if step_id in project.steps:
                step_status = project.steps[step_id].status
                if step_status == StepStatus.COMPLETED:
                    print(f"  [SKIP] Step already completed")
                    results[step_id] = {"status": "skipped", "reason": "already_completed"}
                    continue

            # 执行步骤
            print(f"  [RUN] Executing {step_name}...")
            result = await project_manager.execute_step(project, step_id)

            # 重新加载项目
            project = await project_manager._load_project(project_id)

            # 检查生成的文档
            from app.utils.file_manager import FileManager
            file_manager = FileManager()

            document = await file_manager.load_document(project_id, doc_type)

            if document:
                content_length = len(document.content)
                print(f"  [OK] Document generated: {doc_type.value}")
                print(f"       Length: {content_length} characters")

                # 检查文档完整性
                issues = []

                # 1. 检查是否有 YAML front-matter
                if not document.content.startswith("---"):
                    issues.append("Missing YAML front-matter")

                # 2. 检查是否有截断迹象
                truncation_indicators = [
                    "...",  # 省略号
                    "[truncated]",
                    "[content continues]",
                    "## [Incomplete",
                ]
                for indicator in truncation_indicators:
                    if indicator in document.content[-500:]:  # 检查最后500字符
                        issues.append(f"Possible truncation: found '{indicator}' near end")

                # 3. 检查是否有必需的部分（根据步骤类型）
                required_sections = {
                    "step_2_0": ["Figure", "Table"],
                    "step_2_1": ["## ", "Abstract", "Introduction"],
                    "step_2_2": ["Data", "Simulation"],
                    "step_2_3": ["Engineering", "Implementation"],
                    "step_2_4": ["Risk", "Concern", "Weakness"],
                    "step_2_4b": ["Patch", "Change"],
                    "step_2_5": ["Plan", "Frozen"]
                }

                if step_id in required_sections:
                    missing_sections = []
                    for section in required_sections[step_id]:
                        if section.lower() not in document.content.lower():
                            missing_sections.append(section)
                    if missing_sections:
                        issues.append(f"Missing sections: {', '.join(missing_sections)}")

                # 4. 检查长度是否合理
                min_lengths = {
                    "step_2_0": 500,    # Figure/Table List
                    "step_2_1": 3000,   # Full Proposal (应该很长)
                    "step_2_2": 1500,   # Data/Sim Spec
                    "step_2_3": 2000,   # Engineering Spec
                    "step_2_4": 1500,   # Red Team Review
                    "step_2_4b": 800,   # Patch Propagation
                    "step_2_5": 1000    # Plan Freeze
                }

                if step_id in min_lengths and content_length < min_lengths[step_id]:
                    issues.append(f"Content too short (expected >{min_lengths[step_id]} chars)")

                # 报告问题
                if issues:
                    print(f"  [WARNING] Quality issues detected:")
                    for issue in issues:
                        print(f"    - {issue}")
                    results[step_id] = {
                        "status": "completed_with_issues",
                        "length": content_length,
                        "issues": issues
                    }
                else:
                    print(f"  [OK] Document quality check passed")
                    results[step_id] = {
                        "status": "completed",
                        "length": content_length,
                        "issues": []
                    }

            else:
                print(f"  [ERROR] Document not found: {doc_type.value}")
                results[step_id] = {"status": "failed", "reason": "document_not_found"}

        except Exception as e:
            print(f"  [ERROR] Step failed: {e}")
            import traceback
            traceback.print_exc()
            results[step_id] = {"status": "failed", "reason": str(e)}

    # 汇总报告
    print(f"\n{'=' * 80}")
    print("Step 2 Execution Summary")
    print(f"{'=' * 80}")

    for step_id, step_name, doc_type in step2_steps:
        if step_id in results:
            result = results[step_id]
            status = result["status"]

            if status == "completed":
                print(f"✅ {step_id} ({step_name}): PASSED ({result['length']} chars)")
            elif status == "completed_with_issues":
                print(f"⚠️  {step_id} ({step_name}): COMPLETED WITH ISSUES ({result['length']} chars)")
                for issue in result["issues"]:
                    print(f"     - {issue}")
            elif status == "skipped":
                print(f"⏭️  {step_id} ({step_name}): SKIPPED ({result['reason']})")
            elif status == "failed":
                print(f"❌ {step_id} ({step_name}): FAILED ({result['reason']})")

    # 检查 Gate 2
    print(f"\n{'=' * 80}")
    print("Checking Gate 2 (Plan Freeze)")
    print(f"{'=' * 80}")

    try:
        from app.services.gate_checker import GateChecker
        gate_checker = GateChecker()

        gate_result = await gate_checker.check_gate_2(project_id)

        print(f"\nGate 2 Result: {gate_result.verdict}")
        print(f"Checks passed: {gate_result.checks_passed}/{gate_result.total_checks}")

        for item in gate_result.check_items:
            status_icon = "✅" if item.passed else "❌"
            print(f"  {status_icon} {item.name}: {item.message}")

        if gate_result.suggestions:
            print(f"\nSuggestions:")
            for suggestion in gate_result.suggestions:
                print(f"  - {suggestion}")

    except Exception as e:
        print(f"[ERROR] Gate 2 check failed: {e}")

    print(f"\n{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(test_step2_complete())

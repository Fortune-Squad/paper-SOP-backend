"""
Test Gate 1.25 check after fix
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager


async def test_gate_1_25_check():
    """测试 Gate 1.25 检查"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Gate 1.25 Check (After Fix)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 执行 Gate 1.25 检查
    print("\n[2] Checking Gate 1.25...")
    result = await project_manager.check_gate(project, "gate_1_25")

    # 显示结果
    print(f"\n[3] Gate 1.25 Check Result:")
    print(f"  Verdict: {result['verdict']}")
    print(f"  Checks passed: {result['passed_count']}/{result['total_count']}")

    if result['verdict'] == "PASS":
        print("\n  [OK] Gate 1.25 PASSED!")
    else:
        print("\n  [X] Gate 1.25 FAILED")

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

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_gate_1_25_check())

"""
Test Gate 1.25 check (v7.0: deprecated, redirects to Gate 1)
"""
import asyncio
import sys
from pathlib import Path

backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.services.project_manager import ProjectManager


async def test_gate_1_25_check():
    """测试 Gate 1.25 检查（v7.0: 已合并进 Gate 1，此处验证向后兼容重定向）"""

    project_id = "physics-driven-compressed-sens-9d772ae8"

    print("=" * 80)
    print("Testing Gate 1.25 Check (v7.0: Redirects to Gate 1)")
    print("=" * 80)

    # 初始化管理器
    project_manager = ProjectManager()

    # 加载项目
    print("\n[1] Loading project...")
    project = await project_manager._load_project(project_id)
    print(f"[OK] Project loaded: {project.project_name}")

    # 执行 Gate 1.25 检查（应重定向到 Gate 1）
    print("\n[2] Checking Gate 1.25 (should redirect to Gate 1)...")
    result = await project_manager.check_gate(project, "gate_1_25")

    # 显示结果
    print(f"\n[3] Gate Check Result:")
    print(f"  Verdict: {result['verdict']}")
    print(f"  Checks passed: {result['passed_count']}/{result['total_count']}")

    if result['verdict'] == "PASS":
        print("\n  [OK] Gate PASSED!")
    else:
        print("\n  [X] Gate FAILED")

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

    # 验证 gate_1_passed 也被更新
    print(f"\n[6] Backward compat check:")
    print(f"  gate_1_passed: {project.gate_1_passed}")
    print(f"  gate_1_25_passed: {project.gate_1_25_passed}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(test_gate_1_25_check())

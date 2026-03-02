"""
Hook Runner — §2.2.8 Hook 级检查
command-based 自动检查，不依赖 LLM，每次 subtask 完成后运行。

4 个 hook:
  1. frozen_guard: frozen 文件是否被修改
  2. state_lock: state.json 版本连续性
  3. log_reminder: session log 是否过期
  4. boundary_check: 输出文件是否超出 allowed_paths
"""
import logging
import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from app.services.boundary_checker import ArtifactBoundaryChecker

logger = logging.getLogger(__name__)


class HookResult(BaseModel):
    """Hook 检查结果"""
    hook_name: str = Field(..., description="Hook 名称")
    passed: bool = Field(..., description="是否通过")
    message: str = Field(default="", description="详细信息")


class HookRunner:
    """§2.2.8: Hook 级检查 — command-based, 不依赖 LLM"""

    @staticmethod
    def check_frozen_guard(project_path: str) -> HookResult:
        """
        frozen 文件是否被修改 → 检查 FROZEN_MANIFEST 中的文件 SHA 一致性

        如果 FROZEN_MANIFEST 存在，验证其中记录的 artifact SHA256 是否仍然匹配。
        """
        import hashlib
        pp = Path(project_path)
        exec_dir = pp / "execution"
        if not exec_dir.exists():
            return HookResult(hook_name="frozen_guard", passed=True, message="No execution dir")

        manifests = list(exec_dir.glob("FROZEN_MANIFEST_*.json"))
        if not manifests:
            return HookResult(hook_name="frozen_guard", passed=True, message="No frozen manifests")

        violations = []
        for manifest_path in manifests:
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                for art_path, art_info in data.get("artifacts", {}).items():
                    full_path = pp / art_path
                    if full_path.exists():
                        current_sha = hashlib.sha256(full_path.read_bytes()).hexdigest()
                        expected_sha = art_info.get("sha256", "")
                        if expected_sha and current_sha != expected_sha:
                            violations.append(art_path)
            except Exception as e:
                logger.debug(f"frozen_guard: error reading {manifest_path}: {e}")

        if violations:
            return HookResult(
                hook_name="frozen_guard",
                passed=False,
                message=f"Frozen files modified: {', '.join(violations)}"
            )
        return HookResult(hook_name="frozen_guard", passed=True, message="All frozen files intact")

    @staticmethod
    def check_state_lock(project_path: str) -> HookResult:
        """
        state.json 版本连续性检查 — state_version 应为正整数
        """
        state_file = Path(project_path) / "state.json"
        if not state_file.exists():
            return HookResult(hook_name="state_lock", passed=True, message="No state.json")

        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            version = data.get("state_version", 0)
            if not isinstance(version, int) or version < 1:
                return HookResult(
                    hook_name="state_lock",
                    passed=False,
                    message=f"Invalid state_version: {version}"
                )
            return HookResult(hook_name="state_lock", passed=True, message=f"state_version={version}")
        except Exception as e:
            return HookResult(hook_name="state_lock", passed=False, message=f"state.json read error: {e}")

    @staticmethod
    def check_log_reminder(project_path: str, step_count: int) -> HookResult:
        """
        session log 超过 N 步没更新 → 警告

        如果 step_count >= 5 且 session_log 不存在或为空，发出警告。
        """
        log_dir = Path(project_path) / "logs" / "sessions"
        if step_count < 5:
            return HookResult(hook_name="log_reminder", passed=True, message="Too early for reminder")

        if not log_dir.exists():
            return HookResult(
                hook_name="log_reminder",
                passed=False,
                message=f"No session logs after {step_count} steps"
            )

        session_files = list(log_dir.glob("*.md")) + list(log_dir.glob("*.json"))
        if not session_files:
            return HookResult(
                hook_name="log_reminder",
                passed=False,
                message=f"No session log files after {step_count} steps"
            )

        return HookResult(hook_name="log_reminder", passed=True, message="Session logs present")

    @staticmethod
    def check_boundary(
        changed_files: List[str],
        allowed_paths: List[str],
        forbidden_paths: List[str],
    ) -> HookResult:
        """输出文件是否超出 allowed_paths → 复用 ArtifactBoundaryChecker"""
        if not changed_files:
            return HookResult(hook_name="boundary_check", passed=True, message="No changed files")

        bc_result = ArtifactBoundaryChecker.check(
            changed_files=changed_files,
            allowed_paths=allowed_paths,
            forbidden_paths=forbidden_paths,
        )
        return HookResult(
            hook_name="boundary_check",
            passed=bc_result.passed,
            message=bc_result.details,
        )

    @staticmethod
    def run_all_post_subtask(
        project_path: str,
        changed_files: List[str],
        allowed_paths: List[str],
        forbidden_paths: List[str],
        step_count: int,
    ) -> List[HookResult]:
        """每个 subtask 完成后跑全部 hook"""
        results = [
            HookRunner.check_frozen_guard(project_path),
            HookRunner.check_state_lock(project_path),
            HookRunner.check_log_reminder(project_path, step_count),
            HookRunner.check_boundary(changed_files, allowed_paths, forbidden_paths),
        ]
        for r in results:
            if not r.passed:
                logger.warning(f"Hook {r.hook_name} FAIL: {r.message}")
            else:
                logger.debug(f"Hook {r.hook_name} PASS: {r.message}")
        return results
